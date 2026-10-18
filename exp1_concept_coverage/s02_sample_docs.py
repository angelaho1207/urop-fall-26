"""Sample docs from the stage 1 mix and split them by shard (rows 4-8, P2-P6).

Usage: python s02_sample_docs.py --run pilot
Defaults are the pilot settings (P2, P3). Saves DATA/<run>/docs.parquet and
results/<run>_sample_summary.json. Shards are downloaded to SCRATCH and deleted after reading.
"""
import argparse
import hashlib
import io
import json
import math
import time
from pathlib import Path

import config  # first: sets HF_HOME
import numpy as np
import pandas as pd
import tiktoken
import zstandard
from datasketch import MinHash, MinHashLSH
from huggingface_hub import hf_hub_download

SPARE_SHARDS = 20  # P5: extra candidate shards per source for refills; the run stops if they run out


def allocate(n_docs, shares, min_one):
    """Row 4: split n_docs across sources by token share, rounding by largest remainder."""
    total = sum(shares.values())
    exact = {s: n_docs * w / total for s, w in shares.items()}
    counts = {s: math.floor(x) for s, x in exact.items()}
    # Rounding down loses a few docs; give them to the sources with the largest remainders
    leftover = n_docs - sum(counts.values())
    for s in sorted(exact, key=lambda s: exact[s] - counts[s], reverse=True)[:leftover]:
        counts[s] += 1
    if min_one:
        # P2: in the pilot every source gets at least one doc, taken from the largest source
        for s in counts:
            if counts[s] == 0:
                counts[s] = 1
                counts[max(counts, key=counts.get)] -= 1
    return counts


def read_docs(path):
    """Yield one parsed doc per line of a .jsonl.zst shard, decompressing as it goes."""
    with open(path, "rb") as f:
        reader = io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(f), encoding="utf-8")
        for line in reader:
            yield json.loads(line)


def source_id(doc):
    """The id the dataset gives a doc. Most shards use 'id'; some stack_edu shards use 'blob_id' (P21)."""
    return doc.get("id", doc.get("blob_id"))


def sample_shard(path, repo_path, quota, rng, source):
    """P5, P19: read a shard twice. Pass 1 counts docs and finds usable ones; pass 2 keeps the chosen ones."""
    usable, ids = [], set()
    n_docs = n_whole = n_partial = n_empty = 0
    for i, doc in enumerate(read_docs(path)):
        text = doc["text"]
        n_docs += 1
        ids.add(source_id(doc))  # P22: distinct ids vs lines measures how often the mix repeats docs
        whole = text.strip() == config.REDACTION_MARK
        partial = not whole and config.REDACTION_MARK in text
        empty = text.strip() == ""
        n_whole += whole
        n_partial += partial
        n_empty += empty
        # Row 8: redaction only disqualifies olmocr docs. Row 11: keep every non-empty doc
        redacted = (whole or partial) and source == config.REDACTED_SOURCE
        if not redacted and not empty:
            usable.append(i)

    k = min(quota, len(usable))
    chosen = set(rng.choice(usable, size=k, replace=False).tolist()) if k else set()
    # Pass 2 holds only the chosen docs in memory; an arxiv shard is 1.4 GB compressed
    # P21: our doc id is shard path + line number, unique across sources (dataset ids differ in form and name)
    docs = [{"doc_id": f"{repo_path}:{i}", "source_id": str(source_id(doc)), "line": i, "text": doc["text"]}
            for i, doc in enumerate(read_docs(path)) if i in chosen]
    stats = {"n_docs": n_docs, "n_distinct_ids": len(ids), "n_usable": len(usable), "n_whole_removed": n_whole,
             "n_partial_removed": n_partial, "n_empty": n_empty}
    return docs, stats


def assign_splits(shard_paths_by_source, rng):
    """Row 6: per source, 20% of used shards go to V; T1 and T2 each take 25% of the train shards."""
    split_of = {}
    for source in sorted(shard_paths_by_source):
        paths = list(shard_paths_by_source[source])
        rng.shuffle(paths)
        n_val = int(config.VAL_FRACTION * len(paths) + 0.5)  # round half up
        train = paths[n_val:]
        n_sub = int(config.SUBSET_FRACTION_OF_TRAIN * len(train) + 0.5)
        for p in paths[:n_val]:
            split_of[p] = ("val", "V")
        for p in train[:n_sub]:
            split_of[p] = ("train", "T1")
        for p in train[n_sub:2 * n_sub]:
            split_of[p] = ("train", "T2")
        for p in train[2 * n_sub:]:
            split_of[p] = ("train", "train_rest")
    return split_of


def text_hash(text):
    """Row 7: hash of whitespace-normalized text, for exact duplicates."""
    return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()


def ngram_set(tokens, n):
    """Set of token n-grams, each as the bytes of n int32 ids. A doc shorter than n is one n-gram (T16)."""
    if len(tokens) <= n:
        return {tokens.tobytes()}
    windows = np.lib.stride_tricks.sliding_window_view(tokens, n)
    return {w.tobytes() for w in windows}


def near_duplicate_drops(docs):
    """Row 7: Olmo 3's MinHash settings. Returns masks of V docs near a train doc and T2 docs near a T1 doc."""
    enc = tiktoken.get_encoding(config.DEDUP_TOKENIZER)
    # disallowed_special=() treats a literal '<|endoftext|>' in a doc as ordinary text
    tokens = [np.array(enc.encode(t, disallowed_special=()), dtype=np.int32) for t in docs["text"]]
    num_perm = config.DEDUP_BANDS * config.DEDUP_ROWS
    signatures = []
    for toks in tokens:
        m = MinHash(num_perm=num_perm, seed=config.SEED)
        m.update_batch(list(ngram_set(toks, config.DEDUP_NGRAM)))
        signatures.append(m)

    def drops(query, reference):
        # Index the reference docs; each query doc is a candidate if it shares a band with one of them
        lsh = MinHashLSH(num_perm=num_perm, params=(config.DEDUP_BANDS, config.DEDUP_ROWS))
        for j in np.flatnonzero(reference):
            lsh.insert(int(j), signatures[j])
        dropped, n_candidates = np.zeros(len(docs), dtype=bool), 0
        for i in np.flatnonzero(query):
            for j in lsh.query(signatures[i]):
                n_candidates += 1
                # Verification on exact 3-gram Jaccard removes MinHash false positives
                a = ngram_set(tokens[i], config.DEDUP_VERIFY_NGRAM)
                b = ngram_set(tokens[j], config.DEDUP_VERIFY_NGRAM)
                if len(a & b) / len(a | b) >= config.DEDUP_JACCARD:
                    dropped[i] = True
                    break
        return dropped, n_candidates

    drop_val, cand_val = drops((docs["split"] == "val").to_numpy(), (docs["split"] == "train").to_numpy())
    drop_t2, cand_t2 = drops((docs["subset"] == "T2").to_numpy(), (docs["subset"] == "T1").to_numpy())
    return drop_val, drop_t2, {"candidate_pairs_val_vs_train": cand_val, "candidate_pairs_t2_vs_t1": cand_t2}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="name of the output folder, e.g. pilot")
    parser.add_argument("--n-docs", type=int, default=config.PILOT_N_DOCS)
    parser.add_argument("--docs-per-shard", type=int, default=config.PILOT_DOCS_PER_SHARD)
    parser.add_argument("--min-one-per-source", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    rng = np.random.default_rng(config.SEED)
    shards = pd.read_parquet(config.DATA / "shards.parquet")
    quotas = allocate(args.n_docs, config.TOKEN_SHARE, args.min_one_per_source)
    print("quotas:", quotas)

    scratch = config.SCRATCH / "shards"
    scratch.mkdir(parents=True, exist_ok=True)
    all_docs, shard_stats = [], []
    for source, quota in quotas.items():
        pool = shards[shards["source"] == source].reset_index(drop=True)
        weights = (pool["bytes"] / pool["bytes"].sum()).to_numpy()
        n_needed = math.ceil(quota / args.docs_per_shard)
        # P4: a size-weighted random order of shards without replacement; we walk it until the quota is met
        order = rng.choice(len(pool), size=min(len(pool), n_needed + SPARE_SHARDS), replace=False, p=weights)
        got = 0
        for idx in order:
            if got == quota:
                break
            shard = pool.loc[idx]
            t0 = time.time()
            local = hf_hub_download(config.DATASET_ID, shard["path"], repo_type="dataset",
                                    revision=config.DATASET_REVISION, local_dir=scratch)
            t1 = time.time()
            docs, stats = sample_shard(local, shard["path"], min(args.docs_per_shard, quota - got), rng, source)
            t2 = time.time()
            Path(local).unlink()
            for d in docs:
                d.update(source=source, folder=shard["folder"], shard=shard["path"])
            all_docs += docs
            got += len(docs)
            shard_stats.append({**stats, "path": shard["path"], "source": source, "folder": shard["folder"],
                                "bytes": int(shard["bytes"]), "download_s": round(t1 - t0, 2),
                                "read_s": round(t2 - t1, 2), "n_sampled": len(docs)})
            print(f"{source}: {got}/{quota} docs after {shard['path']} ({t1 - t0:.1f}s download, {t2 - t1:.1f}s read)")
        if got < quota:
            raise RuntimeError(f"{source}: only {got} of {quota} docs after {len(order)} shards")

    docs = pd.DataFrame(all_docs)
    stats = pd.DataFrame(shard_stats)
    used = stats[stats["n_sampled"] > 0]
    split_of = assign_splits(used.groupby("source")["path"].apply(list).to_dict(), rng)
    docs["split"] = docs["shard"].map(lambda p: split_of[p][0])
    docs["subset"] = docs["shard"].map(lambda p: split_of[p][1])

    # Row 7 (P6: exact hash only in the pilot). Drop V docs that match train and T2 docs that match T1
    docs["hash"] = docs["text"].map(text_hash)
    drop_val = (docs["split"] == "val") & docs["hash"].isin(set(docs.loc[docs["split"] == "train", "hash"]))
    drop_t2 = (docs["subset"] == "T2") & docs["hash"].isin(set(docs.loc[docs["subset"] == "T1", "hash"]))
    docs = docs[~(drop_val | drop_t2)].reset_index(drop=True)
    # Row 7: near-duplicates across the same split pairs, after exact copies are gone
    near_val, near_t2, near_counts = near_duplicate_drops(docs)
    docs = docs[~(near_val | near_t2)].reset_index(drop=True)
    # P22: the mix repeats docs, so the sample can hold two copies of one doc. Keep the first drawn copy
    drop_repeat = docs["hash"].duplicated(keep="first")
    docs = docs[~drop_repeat].reset_index(drop=True)
    docs["n_chars"] = docs["text"].str.len()

    out = config.DATA / args.run
    out.mkdir(parents=True, exist_ok=True)
    docs.to_parquet(out / "docs.parquet", index=False)

    olmocr = stats[stats["source"] == config.REDACTED_SOURCE]
    summary = {
        "run": args.run, "seed": config.SEED, "dataset_revision": config.DATASET_REVISION,
        "n_docs_requested": args.n_docs, "docs_per_shard": args.docs_per_shard, "quotas": quotas,
        "docs_by_source_and_subset": docs.groupby(["source", "subset"]).size().unstack(fill_value=0).to_dict("index"),
        "shards_by_source_and_subset": used.assign(subset=used["path"].map(lambda p: split_of[p][1]))
            .groupby(["source", "subset"]).size().unstack(fill_value=0).to_dict("index"),
        "duplicates": {"dropped_val_matching_train": int(drop_val.sum()), "dropped_t2_matching_t1": int(drop_t2.sum()),
                       "dropped_val_near_train": int(near_val.sum()), "dropped_t2_near_t1": int(near_t2.sum()),
                       **near_counts, "dropped_later_repeats_any_split": int(drop_repeat.sum())},
        "repetition_by_source": {  # P22: lines per distinct id in the shards read; 1.0 = no repeats
            s: round(float(g["n_docs"].sum() / g["n_distinct_ids"].sum()), 3) for s, g in stats.groupby("source")
        },
        "removed_by_olmocr_folder": olmocr.groupby("folder")[["n_docs", "n_whole_removed", "n_partial_removed"]].sum().to_dict("index"),
        "removed_and_empty_by_source": stats.groupby("source")[["n_docs", "n_whole_removed", "n_partial_removed", "n_empty"]].sum().to_dict("index"),
        "timing_by_source": {
            s: {"shards": int(len(g)), "median_download_s": float(g["download_s"].median()),
                "median_read_s": float(g["read_s"].median()), "median_mb": float(g["bytes"].median() / 1e6)}
            for s, g in stats.groupby("source")
        },
        "n_chars_quantiles": docs.groupby("source")["n_chars"].quantile([0.1, 0.5, 0.9]).unstack().to_dict("index"),
        "shards": shard_stats,
    }
    (config.RESULTS / f"{args.run}_sample_summary.json").write_text(json.dumps(summary, indent=2, default=int))
    print(json.dumps({k: v for k, v in summary.items() if k != "shards"}, indent=2, default=int))


if __name__ == "__main__":
    main()
