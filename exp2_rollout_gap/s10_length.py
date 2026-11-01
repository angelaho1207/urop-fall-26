"""Length checks on full_post (design.md G43, G45). CPU only, whole document only.

Usage: python s10_length.py --mode lenmatch   (every set subsampled to the same length distribution)
       python s10_length.py --mode min30      (docs under 30 tokens dropped, then one doc count, as G16)
Reads the full_post acts (s02) and Exp 1's V acts. Writes results/full_post_<mode>_distribution_summary.json and
DATA/full_post_<mode>/distribution.parquet. full_post itself is not changed.
"""
import argparse
import json

import settings  # first: puts Exp 1 on the path
import numpy as np
import pandas as pd

import diag_common as dc
from s03_distribution import D_SAE, binned, bootstrap_slopes, log_y, slope

LENGTH_BINS = [1, 30, 100, 300, 1024, 1025]  # G43: [1,30) [30,100) [100,300) [300,1024) [1024]
MIN_TOKENS = 30  # Exp 1 row 11


def choose_lenmatch(all_lengths):
    """G43: in each length bin, every set gets the smallest count over sets, drawn with a fixed seed."""
    chosen, per_bin = {name: [] for name in all_lengths}, []
    for b, (lo, hi) in enumerate(zip(LENGTH_BINS[:-1], LENGTH_BINS[1:])):
        eligible = {name: np.sort(n.index[(n.to_numpy() >= lo) & (n.to_numpy() < hi)].to_numpy()) for name, n in all_lengths.items()}
        n_b = min(len(e) for e in eligible.values())
        per_bin.append({"bin": [lo, hi], "docs": n_b, "available": {k: len(e) for k, e in eligible.items()}})
        for j, (name, e) in enumerate(eligible.items()):
            chosen[name].append(np.random.default_rng([0, 43, b, j]).choice(e, size=n_b, replace=False))
    return {k: np.concatenate(v) for k, v in chosen.items()}, per_bin


def choose_min30(all_lengths):
    """G43: docs under 30 tokens dropped from every set, then one doc count (G16)."""
    eligible = {name: np.sort(n.index[n.to_numpy() >= MIN_TOKENS].to_numpy()) for name, n in all_lengths.items()}
    n = min(len(e) for e in eligible.values())
    chosen = {name: np.random.default_rng([0, 43, 9, j]).choice(e, size=n, replace=False) for j, (name, e) in enumerate(eligible.items())}
    return chosen, [{"docs": n, "available": {k: len(e) for k, e in eligible.items()}}]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["lenmatch", "min30"])
    args = parser.parse_args()
    run = f"{dc.RUN}_{args.mode}"
    c = dc.concepts()
    x, sel, x_fire, edges = c["x"], c["sel"], c["x_fire"], c["edges"]
    paths, all_lengths = dc.set_lengths()
    chosen, selection = (choose_lenmatch if args.mode == "lenmatch" else choose_min30)(all_lengths)
    rng = np.random.default_rng(0)  # as s03
    summary = {"run": run, "selection": selection, "concepts_in_slope": int(sel.sum()), "sets": {}}
    table = pd.DataFrame({"concept": np.arange(D_SAE), "chi_train": c["chi_train"], "in_slope": sel})
    boots, slopes = {}, {}
    for name in paths:
        means, _, lens = dc.read_means(paths[name], chosen[name])
        n = means.shape[0]
        cs = dc.set_chi(means)
        n_fire = np.diff((means > 0).T.tocsr().indptr)
        table[f"chi_{name}"], table[f"n_fire_{name}"] = cs, n_fire
        b = slope(x, cs[sel])
        boot = bootstrap_slopes(means, x, sel, rng, settings.BOOTSTRAP)
        boots[name], slopes[name] = boot, b
        y, zeros = log_y(cs[sel])
        before = all_lengths[name].to_numpy()
        summary["sets"][name] = {
            "docs": n, "slope_chi": round(b, 4), "slope_chi_ci95_basic": (2 * b - np.quantile(boot, [0.975, 0.025])).round(4).tolist(),
            "bootstrap_bias": round(float(boot.mean() - b), 4), "slope_fire_share": round(slope(x_fire, (n_fire / n)[sel]), 4),
            "selected_concepts_with_chi_0": zeros, "binned_median_log_ratio": binned(x, cs[sel], edges),
            "median_ln_ratio": round(float(np.median(y - x)), 4), "sd_ln_ratio": round(float((y - x).std()), 4),
            "length_quantiles_before": {str(q): int(np.quantile(before, q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
            "length_quantiles_after": {str(q): int(np.quantile(lens, q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
        }
        print(name, n, round(b, 4), flush=True)
    summary["delta_vs_V"] = {}
    for name in paths:
        if name == "V":
            continue
        d, db = slopes[name] - slopes["V"], boots[name] - boots["V"]
        bias = float(db.mean() - d)
        summary["delta_vs_V"][name] = {"delta": round(d, 4), "ci95_basic": (2 * d - np.quantile(db, [0.975, 0.025])).round(4).tolist(),
                                       "bootstrap_bias": round(bias, 4), "delta_bias_corrected": round(d - bias, 4)}  # G45
    out_dir = settings.DATA / run
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_dir / "distribution.parquet")
    (settings.RESULTS / f"{run}_distribution_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary["delta_vs_V"], indent=1))


if __name__ == "__main__":
    main()
