"""Share of each concept's coverage by source, in Dolma train and in the Pile, and per class (row R6). CPU only.

Usage: python s05c_source_shares.py --dolma full --pile pile
Reads DATA/<dolma>/coverage.parquet (Dolma train shares, C5), DATA/<dolma>/coverage_vs_pile.parquet (classes, R4),
and DATA/<pile>/ (docs.parquet, acts/). Saves DATA/<pile>/source_shares.parquet and
results/<dolma>_vs_<pile>_source_shares.json.
"""
import argparse
import json

import config
import numpy as np
import pandas as pd

from s05_coverage import D_SAE


def pile_sums_by_collection(pile_dir):
    """Eq. 2 numerator per concept, split by Pile collection (pile_set_name)."""
    docs = pd.read_parquet(pile_dir / "docs.parquet", columns=["doc_id", "source"]).set_index("doc_id")
    names = sorted(docs["source"].unique())
    code = {n: i for i, n in enumerate(names)}
    sums = np.zeros((len(names), D_SAE))
    for path in sorted(pile_dir.glob("acts/part_?????.npz")):
        with np.load(path, allow_pickle=True) as z:
            src = docs.loc[z["doc_id"], "source"].map(code).to_numpy()
            src_of_entry = np.repeat(src, z["doc_active"])
            ids = z["doc_latent_ids"].astype(np.int64)
            means = z["doc_mean"].astype(np.float64)
        for i in range(len(names)):
            keep = src_of_entry == i
            sums[i] += np.bincount(ids[keep], weights=means[keep], minlength=D_SAE)
    doc_share = docs["source"].value_counts(normalize=True).reindex(names).to_numpy()
    return names, sums, doc_share


def pooled(sums, members, doc_share, names):
    """R6: a class's pooled share by source and its enrichment over the source's share of docs."""
    by_source = sums[:, members].sum(axis=1)
    share = by_source / by_source.sum()
    return {n: {"share": round(float(s), 4), "doc_share": round(float(b), 4), "enrichment": round(float(s / b), 2)}
            for n, s, b in sorted(zip(names, share, doc_share), key=lambda x: -x[1])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dolma", required=True)
    parser.add_argument("--pile", required=True)
    args = parser.parse_args()
    dolma_dir, pile_dir = config.DATA / args.dolma, config.DATA / args.pile

    names, p_sums, p_doc_share = pile_sums_by_collection(pile_dir)
    per_concept = pd.DataFrame(p_sums.T / np.where(p_sums.sum(0) > 0, p_sums.sum(0), np.nan)[:, None],
                               columns=[f"pile_share_{n}" for n in names])
    per_concept.insert(0, "concept", np.arange(D_SAE))
    per_concept.to_parquet(pile_dir / "source_shares.parquet", index=False)

    # Dolma train: per-concept shares exist (C5); rebuild per-source sums as share x total for pooling
    cov = pd.read_parquet(dolma_dir / "coverage.parquet")
    share_cols = [c for c in cov.columns if c.startswith("share_")]
    d_names = [c[len("share_"):] for c in share_cols]
    d_total = cov["chi_train"].to_numpy()  # chi is the sum scaled by a constant, so pooled shares are unchanged
    d_sums = np.nan_to_num(cov[share_cols].to_numpy().T * d_total)
    d_docs = pd.read_parquet(dolma_dir / "docs.parquet", columns=["split", "source"])
    d_doc_share = d_docs.loc[d_docs["split"] == "train", "source"].value_counts(normalize=True).reindex(d_names).fillna(0).to_numpy()

    classes = pd.read_parquet(dolma_dir / "coverage_vs_pile.parquet", columns=["class_vs_pile"])["class_vs_pile"].to_numpy()
    summary = {"dolma_run": args.dolma, "pile_run": args.pile, "pile_doc_share": dict(zip(names, np.round(p_doc_share, 4))),
               "by_class": {}}
    for k in ["over", "under", "middle", "rare_in_dolma_present_in_pile", "rare_in_pile_present_in_dolma"]:
        members = np.flatnonzero(classes == k)
        summary["by_class"][k] = {"concepts": int(len(members)),
                                  "pile": pooled(p_sums, members, p_doc_share, names),
                                  "dolma_train": pooled(d_sums, members, d_doc_share, d_names)}
    out = config.RESULTS / f"{args.dolma}_vs_{args.pile}_source_shares.json"
    out.write_text(json.dumps(summary, indent=2, default=float))
    print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()
