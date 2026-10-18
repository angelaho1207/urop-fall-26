"""Independent check of s06's windows against the s04 activations (rows E1-E6). CPU only.

Usage: python check_examples.py --run full [--key class_web]
Checks every window in DATA/<run>/examples (only files that have --key, if given): 10 rank groups of 4 (naming) or
5 (quiz), one window per doc, the doc is in the subset it is listed under, the activations match a token-by-token
rebuild from the CSR arrays, the token ids match the tokenizer, firing windows contain the doc's max token and reach
its max, non-firing windows are all zero. Prints counts of failures (all should be 0).
"""
import argparse
import json
import time
from collections import Counter, defaultdict

import config  # first: sets HF_HOME
import numpy as np
import pandas as pd
from transformers import AutoTokenizer

from s03_pilot import tokenize
from s06_examples import PART_SIZE, WINDOW


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--key", default=None, help="only check example files that contain this field")
    parser.add_argument("--dir", default="examples", help="examples folder under DATA/<run>/ (F run: examples_F)")
    parser.add_argument("--source", default=None, help="F2: every window's doc must have this source")
    args = parser.parse_args()
    t0 = time.time()
    run_dir = config.DATA / args.run
    docs = pd.read_parquet(run_dir / "docs.parquet", columns=["doc_id", "subset", "source", "text"])
    row = {d: i for i, d in enumerate(docs["doc_id"])}
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)

    by_part, bad, n = defaultdict(list), Counter(), Counter()
    for path in sorted((run_dir / args.dir).glob("*.json")):
        ex = json.loads(path.read_text())
        if args.key and args.key not in ex:
            continue
        c = ex["concept"]
        purposes = ["naming", "quiz_firing"] + sorted(k for k in ex if k.startswith("quiz_nonfiring"))  # incl. N15
        for purpose in purposes:
            for subset, wins in ex.get(purpose, {}).items():
                if wins is None:
                    continue
                if not purpose.startswith("quiz_nonfiring"):
                    groups, per = Counter(w["group"] for w in wins), 4 if purpose == "naming" else 5
                    bad["group_counts"] += len(groups) != 10 or any(v != per for v in groups.values())
                bad["one_window_per_doc"] += len({w["doc_id"] for w in wins}) != len(wins)
                for w in wins:
                    i = row[w["doc_id"]]
                    if subset != "PileCC":  # F2: the Pile run pools all Pile-CC docs under one name
                        bad["wrong_subset"] += docs.at[i, "subset"] != subset
                    if args.source:
                        bad["wrong_source"] += docs.at[i, "source"] != args.source
                    by_part[i // PART_SIZE].append((i, c, purpose, w))

    for k in sorted(by_part):
        with np.load(run_dir / "acts" / f"part_{k:05d}.npz", allow_pickle=True) as zf:
            z = {key: zf[key] for key in zf.files}  # read each array once
        tok_start = np.concatenate([[0], np.cumsum(z["doc_tokens"])])
        ent = np.concatenate([[0], np.cumsum(z["tok_counts"], dtype=np.int64)])
        off = np.concatenate([[0], np.cumsum(z["doc_active"])])
        for i, c, purpose, w in by_part[k]:
            j = i - k * PART_SIZE
            bad["doc_id_vs_part"] += z["doc_id"][j] != w["doc_id"]
            full = np.zeros(z["doc_tokens"][j], np.float32)  # rebuild the concept's activation token by token
            for t in range(z["doc_tokens"][j]):
                a, b = ent[tok_start[j] + t], ent[tok_start[j] + t + 1]
                hit = z["latent_ids"][a:b] == c
                if hit.any():
                    full[t] = z["values"][a:b][hit][0]
            n[purpose] += 1
            bad["acts_vs_rebuild"] += not np.allclose(full[w["start"]:w["start"] + WINDOW], w["acts"], atol=1e-3)
            bad["ids_vs_tokenizer"] += tokenize(tokenizer, docs.at[i, "text"])[0][w["start"]:w["start"] + WINDOW] != w["ids"]
            bad["texts_length"] += len(w["texts"]) != len(w["ids"])
            if purpose.startswith("quiz_nonfiring"):
                bad["nonfiring_not_zero"] += any(w["acts"])
            else:
                e = off[j] + int(np.flatnonzero(z["doc_latent_ids"][off[j]:off[j + 1]] == c)[0])
                bad["max_token_not_in_window"] += not (w["start"] <= z["doc_argmax"][e] < w["start"] + WINDOW)
                bad["window_max_vs_doc_max"] += not np.isclose(max(w["acts"]), z["doc_max"][e], rtol=2e-3)
    print(f"windows checked: {dict(n)} across {len(by_part)} parts in {time.time() - t0:.0f}s")
    print("failures:", dict(bad), "| total:", sum(bad.values()))


if __name__ == "__main__":
    main()
