"""Concept sample for the Pile vs Dolma faithfulness test (rows F2, F3). CPU only.

Usage: python s06c_faith_sample.py [--per-class 80]
Counts each concept's firing docs in Pile-CC, Dolma web T1 and Dolma web V (s05b `accumulate`), keeps the testable
ones (F2: at least 40, 40 and 50), and draws --per-class concepts uniformly from each of over, under and middle
(web-only classes, R8) with default_rng([0, 6000, class index]). Saves DATA/full/faith_sample.parquet and
results/faith_sample_summary.json (counts and concept ids only).
"""
import argparse
import json

import config
import numpy as np
import pandas as pd

from s05b_vs_pile import accumulate

CLASSES = ["over", "under", "middle"]  # F3
MIN_NAMING, MIN_QUIZ = 40, 50  # F2 (E2, E3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-class", type=int, default=80)
    args = parser.parse_args()
    web = {"source": "common_crawl"}
    _, d_fires, d_n = accumulate(config.DATA / "full", {"T1": {**web, "subset": "T1"}, "V": {**web, "subset": "V"}})
    _, p_fires, p_n = accumulate(config.DATA / "pile", {"PileCC": {"source": "Pile-CC"}})
    cls = pd.read_parquet(config.DATA / "full" / "coverage_vs_pile_web.parquet", columns=["class_web"])["class_web"]
    table = pd.DataFrame({"concept": np.arange(len(cls)), "class_web": cls.to_numpy(), "n_PileCC": p_fires["PileCC"],
                          "n_T1_web": d_fires["T1"], "n_V_web": d_fires["V"]})
    table["testable"] = ((table["n_PileCC"] >= MIN_NAMING) & (table["n_T1_web"] >= MIN_NAMING)
                         & (table["n_V_web"] >= MIN_QUIZ))
    chosen = []
    for k, c in enumerate(CLASSES):
        pool = table.index[(table["class_web"] == c) & table["testable"]].to_numpy()
        pick = np.random.default_rng([config.SEED, 6000, k]).choice(pool, size=args.per_class, replace=False)
        chosen.append(table.loc[np.sort(pick), ["concept", "class_web"]])
    sample = pd.concat(chosen, ignore_index=True)
    sample.to_parquet(config.DATA / "full" / "faith_sample.parquet", index=False)
    table.to_parquet(config.DATA / "full" / "firing_counts_web.parquet", index=False)
    summary = {"docs": {**d_n, **p_n}, "per_class": args.per_class,
               "testable_by_class": table[table["testable"]]["class_web"].value_counts().to_dict(),
               "sample": {c: sample.loc[sample["class_web"] == c, "concept"].tolist() for c in CLASSES}}
    (config.RESULTS / "faith_sample_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "sample"}, indent=2))


if __name__ == "__main__":
    main()
