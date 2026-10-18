"""Over/under classes relative to the Pile, with a noise floor (rows R4, R5). CPU only.

Usage: python s05b_vs_pile.py --dolma full --pile pile
Reads DATA/<dolma>/ and DATA/<pile>/ (docs.parquet and acts/ from s02/s02b and s04), and
DATA/<dolma>/coverage.parquet (the paper's classes, row 14) to report alongside.
Saves DATA/<dolma>/coverage_vs_pile.parquet and results/<dolma>_vs_<pile>_summary.json.
"""
import argparse
import json

import config
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from s05_coverage import D_SAE, chi

MIN_DOCS = 40  # R4: enough firing docs to name a concept (row 17)
TIERS = pd.cut(np.arange(D_SAE), [-1, 2047, 16383, D_SAE - 1], labels=["0-2047", "2048-16383", "16384-65535"])


def accumulate(run_dir, groups):
    """Per group: Eq. 2 numerator (sum of per-doc means) and the number of docs where each concept fires.

    groups maps a name to (docs.parquet column, value); value None means every doc.
    """
    docs = pd.read_parquet(run_dir / "docs.parquet", columns=["doc_id", "split", "subset"]).set_index("doc_id")
    sums = {g: np.zeros(D_SAE) for g in groups}
    fires = {g: np.zeros(D_SAE, dtype=np.int64) for g in groups}
    for path in sorted(run_dir.glob("acts/part_?????.npz")):
        with np.load(path, allow_pickle=True) as z:
            rows = docs.loc[z["doc_id"]]
            doc_of_entry = np.repeat(np.arange(len(rows)), z["doc_active"])
            ids = z["doc_latent_ids"].astype(np.int64)
            means = z["doc_mean"].astype(np.float64)
        for g, (column, value) in groups.items():
            mask = np.ones(len(rows), dtype=bool) if value is None else (rows[column] == value).to_numpy()
            keep = mask[doc_of_entry]
            sums[g] += np.bincount(ids[keep], weights=means[keep], minlength=D_SAE)
            fires[g] += np.bincount(ids[keep], minlength=D_SAE)  # a doc lists each active concept once
    return sums, fires


def ratio_classes(chi_dolma, chi_pile, n_dolma, n_pile):
    """R4: r = log(chi_dolma / chi_pile) where both have >= 40 firing docs; percentile classes; one-sided lists."""
    both = (n_dolma >= MIN_DOCS) & (n_pile >= MIN_DOCS)
    r = np.full(D_SAE, np.nan)
    r[both] = np.log(chi_dolma[both] / chi_pile[both])
    low, high = np.quantile(r[both], [0.1, 0.9])
    rr = np.where(both, r, 0.0)  # 0 stands in for NaN; those concepts are excluded by `both` anyway
    cls = np.full(D_SAE, "too_rare_to_compare", dtype=object)
    cls[both] = "middle"
    cls[both & (rr <= low)] = "under"
    cls[both & (rr >= high)] = "over"
    cls[(n_pile >= MIN_DOCS) & (n_dolma < MIN_DOCS)] = "rare_in_dolma_present_in_pile"
    cls[(n_dolma >= MIN_DOCS) & (n_pile < MIN_DOCS)] = "rare_in_pile_present_in_dolma"
    return r, cls


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dolma", required=True)
    parser.add_argument("--pile", required=True)
    args = parser.parse_args()
    dolma_dir, pile_dir = config.DATA / args.dolma, config.DATA / args.pile

    d_sums, d_fires = accumulate(dolma_dir, {"train": ("split", "train"), "T1": ("subset", "T1"), "T2": ("subset", "T2")})
    p_sums, p_fires = accumulate(pile_dir, {"all": ("subset", None), "A": ("subset", "A"), "B": ("subset", "B")})

    r, cls = ratio_classes(chi(d_sums["train"]), chi(p_sums["all"]), d_fires["train"], p_fires["all"])
    # R5: the same rules on two disjoint half pairs
    r1, cls1 = ratio_classes(chi(d_sums["T1"]), chi(p_sums["A"]), d_fires["T1"], p_fires["A"])
    r2, cls2 = ratio_classes(chi(d_sums["T2"]), chi(p_sums["B"]), d_fires["T2"], p_fires["B"])
    eligible = np.isfinite(r1) & np.isfinite(r2)

    paper = pd.read_parquet(dolma_dir / "coverage.parquet", columns=["class_train"])["class_train"].to_numpy()
    table = pd.DataFrame({
        "concept": np.arange(D_SAE), "tier": TIERS.astype(str),
        "chi_train": chi(d_sums["train"]), "chi_pile": chi(p_sums["all"]),
        "n_fire_train": d_fires["train"], "n_fire_pile": p_fires["all"],
        "log_ratio": r, "class_vs_pile": cls, "class_paper": paper,
        "log_ratio_half1": r1, "class_half1": cls1, "log_ratio_half2": r2, "class_half2": cls2,
    })
    table.to_parquet(dolma_dir / "coverage_vs_pile.parquet", index=False)

    tier_mix = pd.crosstab(table["class_vs_pile"], table["tier"], normalize="index").round(3)
    summary = {
        "dolma_run": args.dolma, "pile_run": args.pile, "min_docs": MIN_DOCS,
        "classes_vs_pile": table["class_vs_pile"].value_counts().to_dict(),
        "tier_share_by_class": tier_mix.to_dict("index"),
        "noise_floor_half1_vs_half2": {
            "concepts_eligible_in_both": int(eligible.sum()),
            "spearman_log_ratio": round(float(spearmanr(r1[eligible], r2[eligible]).statistic), 4),
            "same_class_share_eligible": round(float((cls1[eligible] == cls2[eligible]).mean()), 4),
            "same_class_share_all_concepts": round(float((cls1 == cls2).mean()), 4),
        },
        "paper_class_vs_new_class": pd.crosstab(table["class_paper"], table["class_vs_pile"]).to_dict("index"),
    }
    out = config.RESULTS / f"{args.dolma}_vs_{args.pile}_summary.json"
    out.write_text(json.dumps(summary, indent=2, default=int))
    print(json.dumps(summary, indent=2, default=int))


if __name__ == "__main__":
    main()
