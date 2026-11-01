"""Figures for the full_post diagnostics (design.md G40). New file names only; existing figures are not touched.

Per set (Dolma V, then each rollout set):
  <run>_<set>_scatter.png       hexbin of log10 chi_set vs log10 chi_train over the slope concepts (G13), y = x, the
                                line y = x + median, and the binned median (G11 bins)
  <run>_<set>_hist_shifted.png  panel (b) of G28 (log10 chi, all concepts with chi > 0) with the set's histogram as is,
                                shifted by its median ln ratio / ln 10, and (right) also rescaled to train's sd
Reads DATA/<run>/distribution.parquet and results/<run>_distribution_summary.json.
Run from this folder: python make_diagnostics_figures.py --run full_post
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
from make_histograms import LOG10_BINS  # noqa: E402
from make_rollout_figure import BG, FG, NULL, SERIES, style  # noqa: E402

SETS = ["V", "stage1", "main", "sft", "dpo", "instruct"]


def color_label(name):
    return (NULL, "Dolma V (held out)") if name == "V" else SERIES[name]


def scatter(table, summary, name, out):
    color, label = color_label(name)
    sel = table["in_slope"].to_numpy()
    xt, ys = table["chi_train"].to_numpy()[sel], table[f"chi_{name}"].to_numpy()[sel]
    pos = ys > 0
    x, y = np.log10(xt[pos]), np.log10(ys[pos])
    med = float(np.median(np.log(ys[pos] / xt[pos]))) / np.log(10)
    fig, ax = plt.subplots(figsize=(9, 8), facecolor=BG)
    style(ax)
    hb = ax.hexbin(x, y, gridsize=120, bins="log", cmap="Greys", mincnt=1)
    lim = [min(x.min(), y.min()), max(x.max(), y.max())]
    ax.plot(lim, lim, color=FG, linewidth=1, label="y = x")
    ax.plot(lim, [v + med for v in lim], color=color, linewidth=1.5, linestyle="--", label=f"y = x + median ({med:.2f})")
    edges = np.array(summary["bin_edges_log_chi_train"]) / np.log(10)
    centers = (edges[:-1] + edges[1:]) / 2
    binned = np.array(summary["sets"][name]["binned_median_log_ratio"]) / np.log(10)
    ax.plot(centers, centers + binned, color=color, linewidth=2.5, marker="o", label="binned median (G11 bins)")
    ax.set_xlabel("log10 χ train")
    ax.set_ylabel(f"log10 χ, {label}")
    ax.legend(frameon=False, loc="upper left", fontsize=11)
    fig.colorbar(hb, ax=ax, label="concepts per hexagon (log)")
    ax.set_title(f"Per concept: {label} vs Dolma train ({int(sel.sum()):,} slope concepts; {int((~pos).sum()):,} with χ = 0 left out)",
                 loc="left", fontsize=12)
    path = out / f"{summary['run']}_{name}_scatter.png"
    fig.savefig(path, dpi=100, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    return path


def hist_shifted(table, summary, name, out):
    color, label = color_label(name)
    train = np.log10(table["chi_train"].to_numpy()[table["chi_train"].to_numpy() > 0])
    chi_set = table[f"chi_{name}"].to_numpy()
    y = np.log10(chi_set[chi_set > 0])
    sel = table["in_slope"].to_numpy()
    xs, ys = table["chi_train"].to_numpy()[sel], chi_set[sel]
    med = float(np.median(np.log(ys[ys > 0] / xs[ys > 0]))) / np.log(10)
    shifted = y - med
    rescaled = (y - y.mean()) / y.std() * train.std() + train.mean()
    fig, axes = plt.subplots(1, 2, figsize=(18, 7), facecolor=BG)
    for ax, (curve, title) in zip(axes, [(shifted, f"shifted by the median ratio ({-med:+.2f} in log10)"),
                                         (rescaled, "shifted and rescaled to train's mean and sd")]):
        style(ax)
        ax.hist(train, bins=LOG10_BINS, color=FG, alpha=0.3, label="Dolma train")
        ax.hist(y, bins=LOG10_BINS, histtype="step", color=color, linewidth=1.5, linestyle=":", label=f"{label}, as is")
        ax.hist(curve, bins=LOG10_BINS, histtype="step", color=color, linewidth=2.2, label=f"{label}, {title}")
        ax.set_xlabel("log10 χ")
        ax.set_ylabel("number of concepts")
        ax.legend(frameon=False, loc="upper left", fontsize=11)
    axes[0].set_title(f"(b) of the histogram figure, {label}: sd log10 χ train {train.std():.2f}, set {y.std():.2f}", loc="left", fontsize=12)
    path = out / f"{summary['run']}_{name}_hist_shifted.png"
    fig.savefig(path, dpi=100, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    out = Path(args.out)
    table = pd.read_parquet(settings.DATA / args.run / "distribution.parquet")
    summary = json.loads((settings.RESULTS / f"{args.run}_distribution_summary.json").read_text())
    for name in SETS:
        print(scatter(table, summary, name, out))
        print(hist_shifted(table, summary, name, out))


if __name__ == "__main__":
    main()
