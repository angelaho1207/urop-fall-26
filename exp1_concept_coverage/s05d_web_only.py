"""Web-only check of the classes vs the Pile: Dolma train common_crawl vs Pile-CC (row R7). CPU only.

Usage: python s05d_web_only.py --dolma full --pile pile
Reads DATA/<dolma>/ and DATA/<pile>/ (docs.parquet, acts/) and DATA/<dolma>/coverage_vs_pile.parquet (R4).
Adds web-only columns to a copy saved as DATA/<dolma>/coverage_vs_pile_web.parquet and writes
results/<dolma>_vs_<pile>_web_only.json.
"""
import argparse
import json

import config
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from s05_coverage import chi
from s05b_vs_pile import accumulate, ratio_classes

CLASSES = ["over", "under", "middle", "rare_in_dolma_present_in_pile", "rare_in_pile_present_in_dolma",
           "too_rare_to_compare"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dolma", required=True)
    parser.add_argument("--pile", required=True)
    args = parser.parse_args()
    dolma_dir, pile_dir = config.DATA / args.dolma, config.DATA / args.pile

    # R7: same number of web docs on both sides, so the 40-doc minimum is equally easy to reach
    d_docs = pd.read_parquet(dolma_dir / "docs.parquet", columns=["doc_id", "split", "source"])
    p_docs = pd.read_parquet(pile_dir / "docs.parquet", columns=["source"])
    n_pile_cc = int((p_docs["source"] == "Pile-CC").sum())
    dolma_cc = d_docs.loc[(d_docs["split"] == "train") & (d_docs["source"] == "common_crawl"), "doc_id"].to_numpy()
    keep = set(np.random.default_rng([config.SEED, 3000]).choice(dolma_cc, size=n_pile_cc, replace=False))
    d_sums, d_fires = accumulate(dolma_dir, {"web": {"split": "train", "source": "common_crawl"}}, doc_filter=keep)
    p_sums, p_fires = accumulate(pile_dir, {"web": {"source": "Pile-CC"}})
    r_web, cls_web = ratio_classes(chi(d_sums["web"]), chi(p_sums["web"]), d_fires["web"], p_fires["web"])

    table = pd.read_parquet(dolma_dir / "coverage_vs_pile.parquet")
    table["n_fire_train_web"], table["n_fire_pile_web"] = d_fires["web"], p_fires["web"]
    table["log_ratio_web"], table["class_web"] = r_web, cls_web
    table.to_parquet(dolma_dir / "coverage_vs_pile_web.parquet", index=False)

    both = table["log_ratio"].notna() & table["log_ratio_web"].notna()
    summary = {
        "dolma_run": args.dolma, "pile_run": args.pile,
        "docs": {"dolma_train_common_crawl": None, "pile_cc": None},
        "classes_web": table["class_web"].value_counts().to_dict(),
        "spearman_log_ratio_full_vs_web": round(float(spearmanr(table.loc[both, "log_ratio"],
                                                                table.loc[both, "log_ratio_web"]).statistic), 4),
        "concepts_eligible_in_both": int(both.sum()),
        "same_class_in_web_only_by_r4_class": {
            k: {"concepts": int((table["class_vs_pile"] == k).sum()),
                "same_class_share": round(float((table.loc[table["class_vs_pile"] == k, "class_web"] == k).mean()), 4),
                "web_class_counts": table.loc[table["class_vs_pile"] == k, "class_web"].value_counts().to_dict()}
            for k in CLASSES},
    }
    summary["docs"] = {"dolma_train_common_crawl_available": int(len(dolma_cc)), "dolma_web_subsample": len(keep),
                       "pile_cc": n_pile_cc}
    out = config.RESULTS / f"{args.dolma}_vs_{args.pile}_web_only.json"
    out.write_text(json.dumps(summary, indent=2, default=int))
    print(json.dumps(summary, indent=2, default=int))


if __name__ == "__main__":
    main()
