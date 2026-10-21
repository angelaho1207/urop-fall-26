"""Static slide figure for Exp 2 (design.md G10): concept distribution of Dolma vs rollouts in one concept order.

Top: chi per concept, x = rank by Dolma train chi. Dolma train is the curve, held-out V the gray null, rollouts in color.
Bottom: binned median of log(chi / chi_train) for V and each rollout set (from s03's summary).
Reads DATA/<run>/distribution.parquet and results/<run>_distribution_summary.json. Colors match space/style.css.
Run from this folder: python make_rollout_figure.py --run full [--window 0]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import settings  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BG, FG, MUTED, LINE = "#fbfbfa", "#1d1d1f", "#6b6b70", "#e2e2e0"
NULL = "#9a9a9a"
SERIES = {"stage1": ("#2a6fb0", "rollouts, end of stage 1"), "main": ("#d1601f", "rollouts, final model")}

plt.rcParams.update({"font.family": ["Arial", "Liberation Sans", "DejaVu Sans"], "font.size": 15, "text.color": FG,
                     "axes.labelcolor": FG, "xtick.color": MUTED, "ytick.color": FG})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--window", type=int, default=None)  # G12: one frame; whole doc if omitted
    args = parser.parse_args()
    table = pd.read_parquet(settings.DATA / args.run / "distribution.parquet").sort_values("chi_train", ascending=False)
    summary = json.loads((settings.RESULTS / f"{args.run}_distribution_summary.json").read_text())
    suffix = "" if args.window is None else f"_w{args.window}"
    gens = [g for g in SERIES if f"chi_{g}" in table]
    rank = np.arange(1, len(table) + 1)

    fig, (top, bottom) = plt.subplots(2, 1, figsize=(12, 9), facecolor=BG, height_ratios=[3, 2], sharex=True)
    for ax in (top, bottom):
        ax.set_facecolor(BG)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(LINE)

    # Top: per bin of 512 consecutive ranks, the median (line) and 10th-90th percentile (band) of each set's chi.
    # Raw clouds of 65,536 points per set hide each other. Concepts with chi = 0 are left out of the band
    # (counted in the summary, G13)
    step = 512
    centers_rank = np.arange(step / 2, len(table), step)

    def band(values):
        rows = [v[v > 0] for v in np.array_split(values, len(centers_rank))]
        return np.array([np.percentile(r, [10, 50, 90]) if len(r) else [np.nan] * 3 for r in rows]).T

    for name, color, label in [("V", NULL, "Dolma V (held out, null)")] + [(g, *SERIES[g]) for g in gens[:1]]:
        lo, mid, hi = band(table[f"chi_{name}{suffix}"].to_numpy())
        top.fill_between(centers_rank, lo, hi, color=color, alpha=0.18, linewidth=0)
        top.plot(centers_rank, mid, color=color, linewidth=2, label=f"{label}: median, 10th-90th pct")
    top.plot(rank, table["chi_train"], color=FG, linewidth=2, label="Dolma train (sets the order)")
    top.set_yscale("log")
    top.set_ylabel("χ (share relative to the average concept)")
    top.legend(frameon=False, loc="lower left", fontsize=13)

    # Bottom: binned medians over the concepts in the slope (G11, G13), placed at the rank of each bin's center
    edges = np.array(summary["bin_edges_log_chi_train"])
    centers_chi = np.exp((edges[:-1] + edges[1:]) / 2)
    sorted_chi = table["chi_train"].to_numpy()  # descending
    at_rank = np.searchsorted(-sorted_chi, -centers_chi)
    bottom.axhline(0, color=LINE, linewidth=1)
    for name, color, label in [("V", NULL, "Dolma V (null)")] + [(g, *SERIES[g]) for g in gens]:
        entry = summary["sets"][name] if args.window is None else summary["sets"][name]["windows"][args.window]
        bottom.plot(at_rank, entry["binned_median_log_ratio"], color=color, linewidth=2, marker="o", markersize=8,
                    markeredgecolor=BG, markeredgewidth=2, label=f"{label}, slope {entry['slope_chi']:.2f}")
    bottom.set_xlabel("concept rank by Dolma train χ (1 = most common)")
    bottom.set_ylabel("median log(χ / χ train)")
    bottom.legend(frameon=False, loc="lower left", fontsize=13)
    bottom.set_xlim(top.get_xlim())

    title = "whole document" if args.window is None else f"tokens {settings.WINDOWS[args.window][0]}-{settings.WINDOWS[args.window][1]}"
    fig.suptitle(f"Concept distribution, Dolma vs unprompted rollouts ({title})", x=0.06, ha="left", fontsize=17)
    fig.tight_layout()
    out = Path(__file__).resolve().parent / f"{args.run}_rollout_distribution{suffix}.png"
    fig.savefig(out, dpi=200, facecolor=BG)
    print(out)


if __name__ == "__main__":
    main()
