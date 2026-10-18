"""Firing-doc counts per concept in T1, T2 and V, and which concepts are testable (rows 16b, N14). CPU only.

Usage: python s06b_firing_counts.py --run full
Reads DATA/<run>/docs.parquet, acts/ and coverage_vs_pile_web.parquet (both comparisons' classes).
Saves DATA/<run>/firing_counts.parquet and results/<run>_testable_summary.json.
"""
import argparse
import json

import config
import numpy as np
import pandas as pd

from s05_coverage import D_SAE

MIN_NAMING, MIN_QUIZ = 40, 50  # rows 17, 18
SUBSETS = ["T1", "T2", "V"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    run_dir = config.DATA / args.run

    docs = pd.read_parquet(run_dir / "docs.parquet", columns=["doc_id", "subset"]).set_index("doc_id")
    counts = {s: np.zeros(D_SAE, dtype=np.int64) for s in SUBSETS}
    for path in sorted(run_dir.glob("acts/part_?????.npz")):
        with np.load(path, allow_pickle=True) as z:
            subset = docs.loc[z["doc_id"], "subset"].to_numpy()
            subset_of_entry = np.repeat(subset, z["doc_active"])
            ids = z["doc_latent_ids"].astype(np.int64)
        for s in SUBSETS:
            counts[s] += np.bincount(ids[subset_of_entry == s], minlength=D_SAE)  # one entry per (doc, concept)

    table = pd.DataFrame({"concept": np.arange(D_SAE), **{f"n_{s}": counts[s] for s in SUBSETS}})
    # Row 16b: names from T1, T2 and V need 40 each; the quiz needs 50 in T2 (pilot) and V (reported)
    table["tested"] = ((table[["n_T1", "n_T2", "n_V"]] >= MIN_NAMING).all(axis=1)
                       & (table[["n_T2", "n_V"]] >= MIN_QUIZ).all(axis=1))
    table.to_parquet(run_dir / "firing_counts.parquet", index=False)

    cls = pd.read_parquet(run_dir / "coverage_vs_pile_web.parquet", columns=["class_vs_pile", "class_web"])
    summary = {"run": args.run, "min_naming": MIN_NAMING, "min_quiz": MIN_QUIZ,
               "tested_all_concepts": int(table["tested"].sum())}
    for column, label in (("class_web", "web_only"), ("class_vs_pile", "whole_dataset")):
        summary[f"tested_by_{label}_class"] = {
            k: {"concepts": int(len(g)), "tested": int(table.loc[g.index, "tested"].sum()),
                "tested_share": round(float(table.loc[g.index, "tested"].mean()), 4)}
            for k, g in cls.groupby(column)}
    flagged = (cls["class_web"].isin(["over", "under", "rare_in_dolma_present_in_pile", "rare_in_pile_present_in_dolma"])
               | cls["class_vs_pile"].isin(["over", "under", "rare_in_dolma_present_in_pile", "rare_in_pile_present_in_dolma"]))
    prefix = table["concept"] < config.PREFIX_WIDTH
    named = flagged | prefix  # row 16b: every flagged concept plus the 2,048 prefix
    summary["to_name"] = {"concepts": int(named.sum()), "tested": int((named & table["tested"]).sum()),
                          "untested": int((named & ~table["tested"]).sum())}
    (config.RESULTS / f"{args.run}_testable_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
