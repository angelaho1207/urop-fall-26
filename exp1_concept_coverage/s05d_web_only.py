"""Web-only classes: Dolma train common_crawl vs Pile-CC, with their own noise floor (rows R7, R8). CPU only.

The main result for detailed concepts (R8). Usage: python s05d_web_only.py --dolma full --pile pile
Reads DATA/<dolma>/ and DATA/<pile>/ (docs.parquet, acts/) and DATA/<dolma>/coverage_vs_pile.parquet (R4).
Saves DATA/<dolma>/coverage_vs_pile_web.parquet (R4 columns + web-only columns) and
results/<dolma>_vs_<pile>_web_only.json.
"""
import argparse
import json

import config
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from s05_coverage import chi
from s05b_vs_pile import TIERS, accumulate, ratio_classes

CLASSES = ["over", "under", "middle", "rare_in_dolma_present_in_pile", "rare_in_pile_present_in_dolma",
           "too_rare_to_compare"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dolma", required=True)
    parser.add_argument("--pile", required=True)
    args = parser.parse_args()
    dolma_dir, pile_dir = config.DATA / args.dolma, config.DATA / args.pile

    web = {"split": "train", "source": "common_crawl"}
    d_sums, d_fires, d_n = accumulate(dolma_dir, {"web": web, "T1": {**web, "subset": "T1"}, "T2": {**web, "subset": "T2"}})
    p_sums, p_fires, p_n = accumulate(pile_dir, {"web": {"source": "Pile-CC"}, "A": {"source": "Pile-CC", "subset": "A"},
                                                 "B": {"source": "Pile-CC", "subset": "B"}})

    def classes(dg, pg):
        return ratio_classes(chi(d_sums[dg]), chi(p_sums[pg]), d_fires[dg], p_fires[pg], d_n[dg], p_n[pg])

    r, cls = classes("web", "web")
    r1, cls1 = classes("T1", "A")  # R8 noise floor, built like R5
    r2, cls2 = classes("T2", "B")
    eligible = np.isfinite(r1) & np.isfinite(r2)

    table = pd.read_parquet(dolma_dir / "coverage_vs_pile.parquet")
    table["n_fire_train_web"], table["n_fire_pile_web"] = d_fires["web"], p_fires["web"]
    table["log_ratio_web"], table["class_web"] = r, cls
    table["log_ratio_web_half1"], table["class_web_half1"] = r1, cls1
    table["log_ratio_web_half2"], table["class_web_half2"] = r2, cls2
    table.to_parquet(dolma_dir / "coverage_vs_pile_web.parquet", index=False)

    both = table["log_ratio"].notna() & table["log_ratio_web"].notna()
    summary = {
        "dolma_run": args.dolma, "pile_run": args.pile,
        "sample_sizes": {"dolma_web": d_n, "pile_cc": p_n},
        "classes_web": table["class_web"].value_counts().to_dict(),
        "tier_share_by_web_class": pd.crosstab(table["class_web"], TIERS.astype(str), normalize="index").round(3).to_dict("index"),
        "noise_floor_web_half1_vs_half2": {
            "concepts_eligible_in_both": int(eligible.sum()),
            "spearman_log_ratio": round(float(spearmanr(r1[eligible], r2[eligible]).statistic), 4),
            "same_class_share_eligible": round(float((cls1[eligible] == cls2[eligible]).mean()), 4),
            "same_class_share_all_concepts": round(float((cls1 == cls2).mean()), 4),
        },
        "vs_whole_dataset_r4": {
            "concepts_eligible_in_both": int(both.sum()),
            "spearman_log_ratio": round(float(spearmanr(table.loc[both, "log_ratio"], table.loc[both, "log_ratio_web"]).statistic), 4),
            "same_class_by_r4_class": {
                k: {"concepts": int((table["class_vs_pile"] == k).sum()),
                    "same_class_share": round(float((table.loc[table["class_vs_pile"] == k, "class_web"] == k).mean()), 4),
                    "web_class_counts": table.loc[table["class_vs_pile"] == k, "class_web"].value_counts().to_dict()}
                for k in CLASSES},
        },
    }
    out = config.RESULTS / f"{args.dolma}_vs_{args.pile}_web_only.json"
    out.write_text(json.dumps(summary, indent=2, default=int))
    print(json.dumps(summary, indent=2, default=int))


if __name__ == "__main__":
    main()
