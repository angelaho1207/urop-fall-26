"""Print the strongest and weakest windows for sampled concepts of one train class (E10). Display only.

Usage: python show_examples.py --run full --cls missing
Reads DATA/<run>/examples/*.json (from s06), coverage.parquet, and for concepts too rare to name,
docs.parquet and the s04 parts.
"""
import argparse
import json

import config  # first: sets HF_HOME
import numpy as np
import pandas as pd
from transformers import AutoTokenizer

from s03_pilot import tokenize
from s06_examples import PART_SIZE, WINDOW, window_start

N_SHOW = 4


def render(texts, acts):
    """Join token texts; firing tokens as <<token>>(activation); newlines shown as a visible mark."""
    out = []
    for t, a in zip(texts, acts):
        t = t.replace("\n", "⏎")
        out.append(f"<<{t}>>({a:.2f})" if a > 0 else t)
    return "".join(out)


def train_wide(run_dir, concept, tokenizer):
    """Rare concepts: strongest and weakest windows over all train docs, cut with s06's rule (E1)."""
    docs = pd.read_parquet(run_dir / "docs.parquet", columns=["doc_id", "split", "text"])
    hits = []  # (doc, max, argmax)
    for k, path in enumerate(sorted(run_dir.glob("acts/part_?????.npz"))):
        with np.load(path, allow_pickle=True) as z:
            # Each z[...] access reads the array from disk again, so read each one once
            ids, doc_max, doc_argmax = z["doc_latent_ids"], z["doc_max"], z["doc_argmax"]
            where = np.flatnonzero(ids == concept)
            # Entry e belongs to the doc whose cumulative doc_active count first exceeds e
            doc_of_entry = np.searchsorted(np.cumsum(z["doc_active"]), where, side="right")
            for e, j in zip(where, doc_of_entry):
                d = k * PART_SIZE + int(j)
                if docs.at[d, "split"] == "train":
                    hits.append((d, float(doc_max[e]), int(doc_argmax[e]), k, int(j)))
    hits.sort(key=lambda h: h[1])
    chosen = hits[-N_SHOW:][::-1] + hits[:N_SHOW] if len(hits) > 2 * N_SHOW else hits[::-1]
    windows = []
    for d, mx, arg, k, j in chosen:
        with np.load(run_dir / "acts" / f"part_{k:05d}.npz", allow_pickle=True) as z:
            tok_counts, lat, val = z["tok_counts"], z["latent_ids"], z["values"]
            ts = int(np.sum(z["doc_tokens"][:j]))
            length = int(z["doc_tokens"][j])
        start = window_start(arg, length)
        ent = np.concatenate([[0], np.cumsum(tok_counts[ts:ts + length], dtype=np.int64)]) + \
            int(np.sum(tok_counts[:ts], dtype=np.int64))
        acts = np.zeros(min(WINDOW, length - start), np.float32)
        for t in range(len(acts)):
            a, b = ent[start + t], ent[start + t + 1]
            m = lat[a:b] == concept
            if m.any():
                acts[t] = val[a:b][m][0]
        ids = tokenize(tokenizer, docs.at[d, "text"])[0][start:start + WINDOW]
        windows.append((mx, [tokenizer.decode([i]) for i in ids], acts))
    return len(hits), windows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--cls", required=True, choices=["missing", "under", "over", "middle"])
    args = parser.parse_args()
    run_dir = config.DATA / args.run
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    for path in sorted((run_dir / "examples").glob("*.json"), key=lambda p: int(p.stem)):
        ex = json.loads(path.read_text())
        if ex.get("class_train") != args.cls:
            continue
        nf = ex["n_firing"]
        print(f"\n=== concept {ex['concept']} | class {ex['class_train']} | chi_train {ex['chi_train']:.5f} | "
              f"firing docs T1/T2/V {nf['T1']}/{nf['T2']}/{nf['V']}")
        t1 = (ex.get("naming") or {}).get("T1")
        if t1:
            strongest = [w for w in t1 if w["group"] == 9][:N_SHOW]
            weakest = [w for w in t1 if w["group"] == 0][:N_SHOW]
            for label, ws in (("strongest (T1 group 9)", strongest), ("weakest (T1 group 0)", weakest)):
                print(f"  -- {label}")
                for w in sorted(ws, key=lambda w: -w["max"]):
                    print(f"  [max {w['max']:.2f}, {w['source']}] {render(w['texts'], w['acts'])}")
        else:
            n_train, windows = train_wide(run_dir, ex["concept"], tokenizer)
            print(f"  (too rare to name; {n_train} firing train docs; strongest then weakest over all train)")
            for mx, texts, acts in windows:
                print(f"  [max {mx:.2f}] {render(texts, acts)}")


if __name__ == "__main__":
    main()
