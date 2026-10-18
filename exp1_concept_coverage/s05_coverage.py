"""Coverage per concept: Eq. 1-2, classes and agreement checks (rows 11, 14, C1-C6). CPU only.

Usage: python s05_coverage.py --run pilot
Reads DATA/<run>/docs.parquet and DATA/<run>/acts/part_?????.npz (from s04).
Saves DATA/<run>/coverage.parquet and results/<run>_coverage_summary.json.
"""
import argparse
import json

import config
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

D_SAE = 65_536
MISSING = np.exp(-5)  # row 14 main threshold, as printed in CG Sec. 3.1
MIN_TOKENS = 30  # row 11 check
GROUPS = ["train", "T1", "T2", "V", "train_min30"]


def chi(sums):
    """Eq. 2 (C1): each concept's sum of per-doc means, divided by the mean of that sum over concepts."""
    return sums / sums.mean()


def classes(values):
    """Row 14: missing below e^-5; among the rest, under at or below the 10th pct, over at or above the 90th."""
    out = np.full(len(values), "middle", dtype=object)
    missing = values < MISSING
    low, high = np.quantile(values[~missing], [0.1, 0.9])
    out[missing] = "missing"
    out[~missing & (values <= low)] = "under"
    out[~missing & (values >= high)] = "over"
    return out


def agreement(a, b):
    """C3: Spearman of log chi over concepts non-missing in both, and the share of concepts with the same class."""
    both = (a >= MISSING) & (b >= MISSING)
    return {"concepts_nonmissing_in_both": int(both.sum()),
            "spearman_log_chi": round(float(spearmanr(np.log(a[both]), np.log(b[both])).statistic), 4),
            "same_class_share": round(float((classes(a) == classes(b)).mean()), 4)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    run_dir = config.DATA / args.run

    docs = pd.read_parquet(run_dir / "docs.parquet", columns=["doc_id", "source", "split", "subset"])
    meta = docs.set_index("doc_id")
    sums = {g: np.zeros(D_SAE) for g in GROUPS}  # Eq. 2 numerators, float64
    by_source = {s: np.zeros(D_SAE) for s in config.TOKEN_SHARE}  # C5, train only
    n_docs = {g: 0 for g in GROUPS}

    parts = sorted(run_dir.glob("acts/part_?????.npz"))  # the ? pattern skips unfinished .tmp files (T12)
    for path in parts:
        with np.load(path, allow_pickle=True) as z:
            offsets = np.concatenate([[0], np.cumsum(z["doc_active"])])
            rows = meta.loc[z["doc_id"]]
            for i in range(len(z["doc_id"])):
                ids = z["doc_latent_ids"][offsets[i]:offsets[i + 1]].astype(np.int64)
                means = z["doc_mean"][offsets[i]:offsets[i + 1]].astype(np.float64)  # Eq. 1 per doc
                split, subset, source = rows.iloc[i][["split", "subset", "source"]]
                targets = [subset] if subset in ("T1", "T2", "V") else []
                if split == "train":
                    targets.append("train")
                    by_source[source][ids] += means
                    if z["doc_tokens"][i] >= MIN_TOKENS:
                        targets.append("train_min30")
                for g in targets:
                    sums[g][ids] += means  # ids are distinct within a doc, so += adds each once
                    n_docs[g] += 1
    if sum(n_docs[g] for g in ("train", "V")) != len(docs):
        raise RuntimeError(f"activations cover {n_docs['train'] + n_docs['V']} of {len(docs)} docs")

    chis = {g: chi(sums[g]) for g in GROUPS}
    table = pd.DataFrame({"concept": np.arange(D_SAE)})
    for g in GROUPS:
        table[f"chi_{g}"] = chis[g]
        table[f"class_{g}"] = classes(chis[g])
    total = sums["train"]
    for s, v in by_source.items():
        # C5: share of the concept's train sum from each source (NaN for concepts that never fire in train)
        table[f"share_{s}"] = np.divide(v, total, out=np.full(D_SAE, np.nan), where=total > 0)
    table.to_parquet(run_dir / "coverage.parquet", index=False)

    summary = {
        "run": args.run, "docs": n_docs, "parts": len(parts),
        "missing_counts": {g: {"never_fires": int((chis[g] == 0).sum()), "below_1e-5": int((chis[g] < 1e-5).sum()),
                               "below_e^-5": int((chis[g] < MISSING).sum())} for g in GROUPS},
        "train_classes": table["class_train"].value_counts().to_dict(),
        "agreement_T1_vs_T2_noise_floor": agreement(chis["T1"], chis["T2"]),
        "agreement_T1_vs_V_test": agreement(chis["T1"], chis["V"]),
        "row11_check": {"train_docs_under_30_tokens": n_docs["train"] - n_docs["train_min30"],
                        "concepts_changing_class": int((table["class_train"] != table["class_train_min30"]).sum())},
    }
    (config.RESULTS / f"{args.run}_coverage_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
