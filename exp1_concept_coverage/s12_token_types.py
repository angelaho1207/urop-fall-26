"""Token-type profile of every compared concept (rows P1-P5). CPU only, no API.

Usage: python s12_token_types.py
For each concept, the token at its peak in each Dolma web train doc and each Pile-CC doc where it fires (s04
`doc_argmax`) is sorted into one of the P2 types. Shares are computed per corpus and averaged (P1); the dominant type
is the largest averaged share (P3). Saves DATA/full/token_types.parquet and results/patterns_token_types.json.
"""
import json
import time
import unicodedata
from concurrent.futures import ProcessPoolExecutor

import config  # first: sets HF_HOME
import numpy as np
import pandas as pd
from transformers import AutoTokenizer

import prompts
from s03_pilot import tokenize

D_SAE = 65_536
TYPES = ["partial_char", "whitespace", "digits", "prose_punct", "symbols", "non_latin",
         "word_start_cap", "word_start_lower", "word_piece", "mixed"]  # P2, in matching order
PROSE = set(".,;:!?'\"()-") | set("‘’“”–—…")
CLASSES = ["over", "under", "middle"]
GROUPS = {"dolma": ("full", {"source": "common_crawl", "split": "train"}), "pile": ("pile", {"source": "Pile-CC"})}
_tok = None


def is_latin(ch):
    return unicodedata.name(ch, "").startswith("LATIN")


def token_type(byte_string):
    """P2: one type per vocabulary entry from its byte-level string; the first rule that matches wins."""
    if any(ch not in prompts._BYTE_OF for ch in byte_string):
        return "mixed"  # special tokens such as <|endoftext|>
    try:
        text = bytes(prompts._BYTE_OF[ch] for ch in byte_string).decode("utf-8")
    except UnicodeDecodeError:
        return "partial_char"
    if text.strip() == "":
        return "whitespace"
    core = text.strip()  # P2: leading and trailing whitespace (spaces, newlines) is ignored for rules 3-5
    if all(c in "0123456789" for c in core):
        return "digits"
    if all(c in PROSE for c in core):
        return "prose_punct"
    if not any(c.isalnum() for c in core):
        return "symbols"
    body = text[1:] if text.startswith(" ") else text
    if any(c.isalpha() and not is_latin(c) for c in body):
        return "non_latin"
    if body and all(c.isalpha() and is_latin(c) for c in body):
        if text.startswith(" "):
            return "word_start_cap" if body[0].isupper() else "word_start_lower"
        return "word_piece"
    return "mixed"


def vocab_types():
    tok = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    strings = tok.convert_ids_to_tokens(list(range(len(tok))))
    return np.array([TYPES.index(token_type(s)) if s is not None else TYPES.index("mixed") for s in strings], np.int8)


def _init():
    global _tok
    _tok = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)


def count_part(job):
    """Counts of (concept, peak-token type) over the part's docs that belong to the group."""
    path, texts_by_row, vtype = job
    counts = np.zeros(D_SAE * len(TYPES), np.int64)
    mismatches = 0
    with np.load(path, allow_pickle=True) as zf:
        z = {k: zf[k] for k in ("doc_tokens", "doc_active", "doc_latent_ids", "doc_argmax")}
    offsets = np.concatenate([[0], np.cumsum(z["doc_active"])])
    for j, text in texts_by_row.items():
        ids = tokenize(_tok, text)[0]
        if len(ids) != z["doc_tokens"][j]:  # same tokenization as s04, or the positions do not line up
            mismatches += 1
            continue
        lat = z["doc_latent_ids"][offsets[j]:offsets[j + 1]].astype(np.int64)
        pos = z["doc_argmax"][offsets[j]:offsets[j + 1]].astype(np.int64)
        types = vtype[np.asarray(ids)[pos]]
        counts += np.bincount(lat * len(TYPES) + types, minlength=len(counts))
    return counts, mismatches


def corpus_counts(run, conditions, vtype):
    run_dir = config.DATA / run
    docs = pd.read_parquet(run_dir / "docs.parquet", columns=["doc_id", "source", "split", "text"])
    mask = np.ones(len(docs), bool)
    for col, val in conditions.items():
        mask &= (docs[col] == val).to_numpy()
    parts = sorted(run_dir.glob("acts/part_?????.npz"))
    jobs = []
    for k, path in enumerate(parts):
        rows = np.flatnonzero(mask[k * 1000:(k + 1) * 1000])  # s04 writes 1,000 docs per part (T12)
        jobs.append((path, {int(j): docs.at[k * 1000 + int(j), "text"] for j in rows}, vtype))
    total, bad = np.zeros(D_SAE * len(TYPES), np.int64), 0
    with ProcessPoolExecutor(6, initializer=_init) as pool:
        for counts, mismatches in pool.map(count_part, jobs):
            total += counts
            bad += mismatches
    return total.reshape(D_SAE, len(TYPES)), int(mask.sum()), bad


def boot_share(flags, rng, n=10_000):
    idx = rng.integers(0, len(flags), (n, len(flags)))
    return flags[idx].mean(1)


def main():
    t0 = time.time()
    vtype = vocab_types()
    vocab_counts = {t: int((vtype == i).sum()) for i, t in enumerate(TYPES)}
    print("vocabulary by type:", vocab_counts, flush=True)
    counts, info = {}, {}
    for g, (run, cond) in GROUPS.items():
        counts[g], n_docs, bad = corpus_counts(run, cond, vtype)
        info[g] = {"docs": n_docs, "tokenization_mismatches": bad}
        print(g, info[g], f"{time.time() - t0:.0f}s", flush=True)

    web = pd.read_parquet(config.DATA / "full" / "coverage_vs_pile_web.parquet", columns=["class_web", "log_ratio_web"])
    keep = web["class_web"].isin(CLASSES).to_numpy()
    shares = {}
    for g in GROUPS:
        tot = counts[g].sum(1, keepdims=True)
        shares[g] = np.divide(counts[g], tot, out=np.zeros_like(counts[g], dtype=float), where=tot > 0)
    avg = (shares["dolma"] + shares["pile"]) / 2
    dominant = np.array(TYPES)[avg.argmax(1)]
    table = pd.DataFrame(avg, columns=TYPES)
    table.insert(0, "concept", np.arange(D_SAE))
    table["dominant"] = dominant
    table["class_web"] = web["class_web"]
    table["n_peaks_dolma"], table["n_peaks_pile"] = counts["dolma"].sum(1), counts["pile"].sum(1)
    table[keep].to_parquet(config.DATA / "full" / "token_types.parquet", index=False)

    rng = np.random.default_rng(config.SEED)
    t = table[keep]
    out = {"vocab_by_type": vocab_counts, "corpora": info, "concepts": t["class_web"].value_counts().to_dict(),
           "min_peaks_per_concept": {g: int(t[f"n_peaks_{g}"].min()) for g in GROUPS},
           "dominant_share": {}, "dominant_diff_vs_middle": {}, "mean_share": {}}
    boots = {}
    for cls in CLASSES:
        sub = t[t["class_web"] == cls]
        out["dominant_share"][cls], out["mean_share"][cls] = {}, {}
        for ty in TYPES:
            flags = (sub["dominant"] == ty).to_numpy(float)
            b = boot_share(flags, rng)
            boots[(cls, ty)] = b
            out["dominant_share"][cls][ty] = [round(flags.mean(), 4), round(np.percentile(b, 2.5), 4),
                                              round(np.percentile(b, 97.5), 4)]
            out["mean_share"][cls][ty] = round(float(sub[ty].mean()), 4)
    for cls in ("over", "under"):
        out["dominant_diff_vs_middle"][cls] = {}
        for ty in TYPES:
            d = boots[(cls, ty)] - boots[("middle", ty)]
            point = out["dominant_share"][cls][ty][0] - out["dominant_share"]["middle"][ty][0]
            out["dominant_diff_vs_middle"][cls][ty] = [round(point, 4), round(np.percentile(d, 2.5), 4),
                                                        round(np.percentile(d, 97.5), 4)]
    out["seconds"] = round(time.time() - t0)
    (config.RESULTS / "patterns_token_types.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("corpora", "concepts", "min_peaks_per_concept")}, indent=1))


if __name__ == "__main__":
    main()
