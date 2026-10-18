"""Example windows per concept for naming (s07) and the quiz (s08) (rows 17, 18, E1-E9). CPU only.

Usage: python s06_examples.py --run pilot --concepts 0-19
       python s06_examples.py --run full --concepts classes:5   (or: prefix)
Reads DATA/<run>/docs.parquet, DATA/<run>/acts/part_?????.npz and, if present, DATA/<run>/coverage.parquet.
Saves DATA/<run>/examples/<concept>.json and results/<run>_examples_summary.json.
"""
import argparse
import json
import re
import time

import config  # first: sets HF_HOME
import numpy as np
import pandas as pd
from huggingface_hub import snapshot_download
from safetensors import safe_open
from transformers import AutoTokenizer

from s03_pilot import tokenize

D_SAE = 65_536
PART_SIZE = 1000  # s04 writes 1,000 docs per part (T12)
WINDOW, BEFORE = 32, 16  # E1
GROUPS, NAMING_PER_GROUP, QUIZ_PER_GROUP = 10, 4, 5  # E2
N_NAMING, N_QUIZ = GROUPS * NAMING_PER_GROUP, GROUPS * QUIZ_PER_GROUP
N_NONFIRING_CANDIDATES = 200  # E9
SUBSETS = ["T1", "T2", "V"]
QUIZ_SUBSETS = ["T2", "V"]  # E3: only the T1 name is quizzed
PURPOSES = {"naming": 0, "quiz_firing": 1, "quiz_nonfiring": 2}  # E6
CLASSES = ["missing", "under", "over", "middle"]  # E8
CLASSES_VS_PILE = ["over", "under", "rare_in_dolma_present_in_pile", "rare_in_pile_present_in_dolma"]  # E11, E12


def pick_concepts(spec, run_dir):
    """E8, E11, E12: 'a-b', 'prefix', 'classes:n' (paper), 'vs_pile:n' (R4) or 'web:n' (web-only, R8)."""
    if spec == "prefix":
        return np.arange(config.PREFIX_WIDTH)
    for prefix, file, column, offset in (("vs_pile:", "coverage_vs_pile.parquet", "class_vs_pile", 2000),
                                         ("web:", "coverage_vs_pile_web.parquet", "class_web", 4000)):
        if spec.startswith(prefix):
            n = int(spec.split(":")[1])
            cls = pd.read_parquet(run_dir / file, columns=[column])[column].to_numpy()
            chosen = [np.random.default_rng([config.SEED, offset + k]).choice(np.flatnonzero(cls == c), size=n,
                                                                             replace=False)
                      for k, c in enumerate(CLASSES_VS_PILE)]
            return np.sort(np.concatenate(chosen))
    if spec.startswith("pilot:"):  # N14: uniform draw from testable concepts in the web-only flagged classes
        n = int(spec.split(":")[1])
        tested = pd.read_parquet(run_dir / "firing_counts.parquet", columns=["tested"])["tested"].to_numpy()
        cls = pd.read_parquet(run_dir / "coverage_vs_pile_web.parquet", columns=["class_web"])["class_web"].to_numpy()
        pool = np.flatnonzero(tested & np.isin(cls, CLASSES_VS_PILE))
        return np.sort(np.random.default_rng([config.SEED, 5000]).choice(pool, size=n, replace=False))
    if spec.startswith("classes:"):
        n = int(spec.split(":")[1])
        cls = pd.read_parquet(run_dir / "coverage.parquet", columns=["class_train"])["class_train"].to_numpy()
        chosen = [np.random.default_rng([config.SEED, 1000 + k]).choice(np.flatnonzero(cls == c), size=n, replace=False)
                  for k, c in enumerate(CLASSES)]
        return np.sort(np.concatenate(chosen))
    lo, hi = map(int, spec.split("-"))
    return np.arange(lo, hi + 1)


def window_start(center, length):
    """E1: 16 tokens before the center, shifted to stay inside the doc; 0 for docs shorter than 32 tokens."""
    return int(min(max(center - BEFORE, 0), max(length - WINDOW, 0)))


def rank_groups(order, per_group, rng):
    """E2: split docs (sorted by max) into 10 equal-size rank groups and draw per_group from each."""
    picks = []
    for g, members in enumerate(np.array_split(order, GROUPS)):
        for d in rng.choice(members, size=per_group, replace=False):
            picks.append((int(d), g))
    return picks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--concepts", required=True, help="'0-19', 'prefix', 'classes:5', 'vs_pile:5', 'web:5', 'pilot:20'")
    parser.add_argument("--neighbours", action="store_true", help="N15: also build neighbour non-firing windows in T2")
    args = parser.parse_args()
    t_start = time.time()
    run_dir = config.DATA / args.run
    out_dir = run_dir / "examples"
    out_dir.mkdir(parents=True, exist_ok=True)

    concepts = pick_concepts(args.concepts, run_dir)
    selected = np.zeros(D_SAE, dtype=bool)
    selected[concepts] = True
    neighbour = {}
    if args.neighbours:  # N15: nearest other concept by cosine of SAE decoder directions
        root = snapshot_download(config.SAE_REPO, revision=config.SAE_REVISION, allow_patterns=[f"{config.SAE_ID}/*"])
        with safe_open(f"{root}/{config.SAE_ID}/sae_weights.safetensors", "np") as f:
            w_dec = f.get_tensor("W_dec")  # (65,536 concepts, 4,096)
        w_dec /= np.linalg.norm(w_dec, axis=1, keepdims=True)
        cos = w_dec[concepts] @ w_dec.T  # (n concepts, 65,536)
        cos[np.arange(len(concepts)), concepts] = -np.inf  # a concept is not its own neighbour
        for c, row in zip(concepts, cos):
            nb = int(np.argmax(row))
            neighbour[int(c)] = (nb, float(row[nb]))
            selected[nb] = True  # pass 1 must also collect the neighbour's doc-level entries
    docs = pd.read_parquet(run_dir / "docs.parquet", columns=["doc_id", "source", "subset", "text"])
    subset_code = docs["subset"].map({s: i for i, s in enumerate(SUBSETS)}).fillna(-1).to_numpy(dtype=np.int8)
    parts = sorted(run_dir.glob("acts/part_?????.npz"))

    # Pass 1 (doc level): every (doc, concept) entry for the selected concepts, with the doc's max and its position
    doc_len = np.zeros(len(docs), dtype=np.int32)
    e_doc, e_concept, e_max, e_argmax = [], [], [], []
    for k, path in enumerate(parts):
        with np.load(path, allow_pickle=True) as z:
            base = k * PART_SIZE
            doc_len[base:base + len(z["doc_id"])] = z["doc_tokens"]
            doc_of_entry = np.repeat(np.arange(len(z["doc_id"])), z["doc_active"]) + base
            keep = selected[z["doc_latent_ids"]]
            e_doc.append(doc_of_entry[keep].astype(np.int32))
            e_concept.append(z["doc_latent_ids"][keep])
            e_max.append(z["doc_max"][keep])
            e_argmax.append(z["doc_argmax"][keep].astype(np.int32))
    e_doc, e_concept = np.concatenate(e_doc), np.concatenate(e_concept)
    e_max, e_argmax = np.concatenate(e_max), np.concatenate(e_argmax)
    by_concept = np.argsort(e_concept, kind="stable")
    sorted_concepts = e_concept[by_concept]

    def entries_of(c):
        """Indices (into the e_* arrays) of every (doc, concept) entry for concept c."""
        return by_concept[np.searchsorted(sorted_concepts, c, "left"):np.searchsorted(sorted_concepts, c, "right")]

    # Selection (E2-E4, E6, E9): which doc and window each example uses; activations are filled in pass 2
    plan, n_firing, max_by_subset = {}, {}, {}
    requests = []  # (doc, concept, start, key into plan)
    for c in concepts:
        idx = entries_of(c)
        plan[c], n_firing[c], max_by_subset[c] = {}, {}, {}
        for s_i, s in enumerate(SUBSETS):
            mine = idx[subset_code[e_doc[idx]] == s_i]
            n_firing[c][s] = int(len(mine))
            # N4: the 0-10 activation scale divides by the concept's max over all of the subset's firing docs
            max_by_subset[c][s] = round(float(e_max[mine].max()), 4) if len(mine) else 0.0
            order = mine[np.lexsort((e_doc[mine], e_max[mine]))]  # sorted by max; ties by doc index
            jobs = [("naming", N_NAMING, NAMING_PER_GROUP)]
            if s in QUIZ_SUBSETS:
                jobs.append(("quiz_firing", N_QUIZ, QUIZ_PER_GROUP))
            for purpose, needed, per_group in jobs:
                key = (purpose, s)
                if len(order) < needed:
                    plan[c][key] = None  # short (rows 17, 18)
                    continue
                rng = np.random.default_rng([config.SEED, int(c), s_i, PURPOSES[purpose]])
                plan[c][key] = []
                for e, g in rank_groups(order, per_group, rng):
                    d = int(e_doc[e])
                    item = {"doc": d, "group": g, "max": float(e_max[e]),
                            "start": window_start(int(e_argmax[e]), int(doc_len[d]))}
                    plan[c][key].append(item)
                    requests.append((d, int(c), item))
            if s in QUIZ_SUBSETS:
                # E4, E9: random docs of the subset and a random window in each; kept later if all zero
                rng = np.random.default_rng([config.SEED, int(c), s_i, PURPOSES["quiz_nonfiring"]])
                pool = np.flatnonzero(subset_code == s_i)
                cands = rng.choice(pool, size=min(N_NONFIRING_CANDIDATES, len(pool)), replace=False)
                plan[c][("quiz_nonfiring", s)] = []
                for d in cands:
                    item = {"doc": int(d), "group": None, "max": 0.0,
                            "start": int(rng.integers(0, max(int(doc_len[d]) - WINDOW, 0) + 1))}
                    plan[c][("quiz_nonfiring", s)].append(item)
                    requests.append((int(d), int(c), item))
            if s == "T2" and args.neighbours:
                # N15: T2 docs where the neighbour fires, window on the neighbour's max token; kept later if all zero
                nb_idx = entries_of(neighbour[int(c)][0])
                nb_idx = nb_idx[subset_code[e_doc[nb_idx]] == s_i]
                rng = np.random.default_rng([config.SEED, int(c), s_i, 3])
                plan[c][("quiz_nonfiring_neighbour", s)] = []
                for e in rng.choice(nb_idx, size=min(N_NONFIRING_CANDIDATES, len(nb_idx)), replace=False):
                    d = int(e_doc[e])
                    item = {"doc": d, "group": None, "max": 0.0,
                            "start": window_start(int(e_argmax[e]), int(doc_len[d]))}
                    plan[c][("quiz_nonfiring_neighbour", s)].append(item)
                    requests.append((d, int(c), item))

    # Pass 2 (token level, per part): the concept's activation at each of the window's tokens (E5)
    requests.sort(key=lambda r: r[0])
    r = 0
    for k, path in enumerate(parts):
        base, end = k * PART_SIZE, (k + 1) * PART_SIZE
        if r >= len(requests) or requests[r][0] >= end:
            continue
        with np.load(path, allow_pickle=True) as z:
            tok_start = np.concatenate([[0], np.cumsum(z["doc_tokens"])])
            entry_start = np.concatenate([[0], np.cumsum(z["tok_counts"], dtype=np.int64)])
            latent_ids, values, tok_counts = z["latent_ids"], z["values"], z["tok_counts"]
            while r < len(requests) and requests[r][0] < end:
                d, c, item = requests[r]
                t0 = tok_start[d - base] + item["start"]
                t1 = min(t0 + WINDOW, tok_start[d - base + 1])
                e0, e1 = entry_start[t0], entry_start[t1]
                token_of_entry = np.repeat(np.arange(t1 - t0), tok_counts[t0:t1])
                hit = latent_ids[e0:e1] == c
                acts = np.zeros(t1 - t0, dtype=np.float32)
                acts[token_of_entry[hit]] = values[e0:e1][hit]
                item["acts"] = acts
                r += 1

    # Non-firing: keep the first 50 all-zero windows in candidate order (E4, E9)
    for c in concepts:
        for key in [k for k in plan[c] if k[0].startswith("quiz_nonfiring")]:
            kept = [it for it in plan[c][key] if not it["acts"].any()][:N_QUIZ]
            plan[c][key] = kept if len(kept) == N_QUIZ else None

    # Text (E5): re-tokenize only the docs used, the same way s04 did, and decode one token at a time
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    used = sorted({it["doc"] for c in concepts for v in plan[c].values() if v for it in v})
    ids_of = {}
    for d in used:
        ids = tokenize(tokenizer, docs.at[d, "text"])[0]
        if len(ids) != doc_len[d]:
            raise RuntimeError(f"doc {d}: {len(ids)} tokens now vs {doc_len[d]} in s04")
        ids_of[d] = ids
    piece = {}

    def text_of(i):
        if i not in piece:
            piece[i] = tokenizer.decode([i])
        return piece[i]

    coverage = pd.read_parquet(run_dir / "coverage.parquet") if (run_dir / "coverage.parquet").exists() else None
    vs_pile_path = run_dir / "coverage_vs_pile.parquet"
    vs_pile = pd.read_parquet(vs_pile_path, columns=["class_vs_pile", "log_ratio"]) if vs_pile_path.exists() else None
    web_path = run_dir / "coverage_vs_pile_web.parquet"
    web = pd.read_parquet(web_path, columns=["class_web", "log_ratio_web"]) if web_path.exists() else None
    summary = {"run": args.run, "concepts_spec": args.concepts, "concepts": int(len(concepts)),
               "short": {f"{p}_{s}": 0 for (p, s) in [("naming", s) for s in SUBSETS]
                         + [(p, s) for p in ("quiz_firing", "quiz_nonfiring") for s in QUIZ_SUBSETS]}}
    for c in concepts:
        out = {"concept": int(c), "run": args.run, "n_firing": n_firing[c], "max_by_subset": max_by_subset[c]}
        if int(c) in neighbour:
            out["neighbour"] = {"concept": neighbour[int(c)][0], "cosine": round(neighbour[int(c)][1], 4)}
        if coverage is not None:
            out["class_train"] = coverage.at[c, "class_train"]
            out["chi_train"] = float(coverage.at[c, "chi_train"])
        if vs_pile is not None:  # E11
            out["class_vs_pile"] = vs_pile.at[c, "class_vs_pile"]
            ratio = vs_pile.at[c, "log_ratio"]
            out["log_ratio_vs_pile"] = None if pd.isna(ratio) else round(float(ratio), 4)
        if web is not None:  # E12
            out["class_web"] = web.at[c, "class_web"]
            ratio = web.at[c, "log_ratio_web"]
            out["log_ratio_web"] = None if pd.isna(ratio) else round(float(ratio), 4)
        for (purpose, s), items in plan[c].items():
            if items is None:
                summary["short"][f"{purpose}_{s}"] = summary["short"].get(f"{purpose}_{s}", 0) + 1
                out.setdefault(purpose, {})[s] = None
                continue
            windows = []
            for it in items:
                ids = ids_of[it["doc"]][it["start"]:it["start"] + WINDOW]
                windows.append({"doc_id": docs.at[it["doc"], "doc_id"], "source": docs.at[it["doc"], "source"],
                                "start": it["start"], "group": it["group"], "max": round(it["max"], 4),
                                "ids": [int(i) for i in ids], "texts": [text_of(int(i)) for i in ids],
                                "acts": [round(float(a), 4) for a in it["acts"]]})
            out.setdefault(purpose, {})[s] = windows
        (out_dir / f"{int(c)}.json").write_text(json.dumps(out, ensure_ascii=False))

    summary["n_firing_quantiles_10_50_90"] = {
        s: np.quantile([n_firing[c][s] for c in concepts], [0.1, 0.5, 0.9]).round(0).tolist() for s in SUBSETS}
    summary["seconds"] = round(time.time() - t_start, 1)
    spec = re.sub(r"[^0-9a-zA-Z]+", "", args.concepts)  # E7: one summary per concept selection, e.g. vs_pile:5 -> vspile5
    (config.RESULTS / f"{args.run}_examples_summary_{spec}.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
