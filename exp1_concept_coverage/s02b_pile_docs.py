"""Pile reference sample for the over/under classes (rows R1, R2). CPU only.

Usage: python s02b_pile_docs.py --run pile
Saves DATA/<run>/docs.parquet (doc_id, source, split, subset, text), the format s04 reads,
and results/<run>_sample_summary.json.
"""
import argparse
import io
import json

import config  # first: sets HF_HOME
import pandas as pd
import zstandard
from huggingface_hub import HfFileSystem

# R1: Pile files held out from the SAE, whose training data came from train/00 and train/01
FILES = [f"train/{i:02d}.jsonl.zst" for i in range(2, 12)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--per-file", type=int, default=4000)  # R1: 10 files x 4,000 = 40,000 docs
    args = parser.parse_args()

    fs = HfFileSystem()
    rows, per_file = [], {}
    for f in FILES:
        path = f"datasets/{config.PILE_ID}@{config.PILE_REVISION}/{f}"
        n = 0
        with fs.open(path, "rb") as handle:
            reader = io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(handle), encoding="utf-8")
            for line_no, line in enumerate(reader):
                doc = json.loads(line)
                if not doc["text"].strip():  # row 11: non-empty docs only, as for Dolma
                    continue
                rows.append({"doc_id": f"{f}:{line_no}", "source": doc["meta"]["pile_set_name"], "split": "pile",
                             "subset": "A" if int(f[6:8]) <= 6 else "B",  # R5: files 02-06 vs 07-11
                             "text": doc["text"]})
                n += 1
                if n == args.per_file:
                    break
        per_file[f] = n
        print(f"{f}: {n} docs", flush=True)

    docs = pd.DataFrame(rows)
    out = config.DATA / args.run
    out.mkdir(parents=True, exist_ok=True)
    docs.to_parquet(out / "docs.parquet", index=False)
    summary = {"run": args.run, "dataset": config.PILE_ID, "revision": config.PILE_REVISION,
               "docs": len(docs), "per_file": per_file, "by_subset": docs["subset"].value_counts().to_dict(),
               "by_pile_set": docs["source"].value_counts().to_dict()}
    (config.RESULTS / f"{args.run}_sample_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
