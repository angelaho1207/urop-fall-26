"""Static figures for Exp 2 (design.md G10, G12, G23): per generator and frame (whole doc, then each token window),
graph 1 the Dolma distribution alone, graph 2 the rollout distribution alone, graph 3 the overlay, and the ratio panel.

x = concept rank by Dolma train chi in every graph. Bands: 10th-90th percentile of chi in bins of 512 ranks, line =
median. Ratio panel: binned median of log(chi / chi_train) from s03's summary.
Reads DATA/<run>/distribution.parquet and results/<run>_distribution_summary.json. Colors match space/style.css.
Writes <run>_<generator>_<frame>.png for every frame and <run>_<generator>_animation.gif into --out.
Run from this folder: python make_rollout_figure.py --run full [--out DIR]
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
from PIL import Image  # noqa: E402

BG, FG, MUTED, LINE = "#fbfbfa", "#1d1d1f", "#6b6b70", "#e2e2e0"
NULL = "#9a9a9a"
SERIES = {"stage1": ("#2a6fb0", "rollouts, end of stage 1"), "main": ("#d1601f", "rollouts, final model")}
STEP = 512  # ranks per band bin

plt.rcParams.update({"font.family": ["Arial", "Liberation Sans", "DejaVu Sans"], "font.size": 14, "text.color": FG,
                     "axes.labelcolor": FG, "xtick.color": MUTED, "ytick.color": FG})


def band(values):
    """10th, 50th and 90th percentile of the positive chi values in each bin of STEP ranks (chi = 0 is counted in s03)."""
    rows = [v[v > 0] for v in np.array_split(values, int(np.ceil(len(values) / STEP)))]
    return np.array([np.percentile(r, [10, 50, 90]) if len(r) else [np.nan] * 3 for r in rows]).T


def style(ax):
    ax.set_facecolor(BG)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(LINE)


def draw(table, summary, g, frame, out):
    """One PNG: graphs 1-3 in the top row, the ratio panel below. frame is None (whole doc) or a window index."""
    suffix = "" if frame is None else f"_w{frame}"
    rank = np.arange(1, len(table) + 1)
    n_bins = int(np.ceil(len(table) / STEP))
    centers = np.arange(n_bins) * STEP + STEP / 2
    v_band, g_band = band(table[f"chi_V{suffix}"].to_numpy()), band(table[f"chi_{g}{suffix}"].to_numpy())
    color, label = SERIES[g]

    fig = plt.figure(figsize=(19, 10), facecolor=BG)
    grid = fig.add_gridspec(2, 3, height_ratios=[3, 2], hspace=0.35, wspace=0.08)
    graphs = [fig.add_subplot(grid[0, i]) for i in range(3)]
    for ax in graphs[1:]:
        ax.sharey(graphs[0])
        ax.tick_params(labelleft=False)
    ratio = fig.add_subplot(grid[1, :])

    def dolma(ax):
        ax.fill_between(centers, v_band[0], v_band[2], color=NULL, alpha=0.25, linewidth=0)
        ax.plot(centers, v_band[1], color=NULL, linewidth=2, label="Dolma V (held out): median, 10th-90th pct")
        ax.plot(rank, table["chi_train"], color=FG, linewidth=2, label="Dolma train (sets the order)")

    def rollouts(ax):
        ax.fill_between(centers, g_band[0], g_band[2], color=color, alpha=0.2, linewidth=0)
        ax.plot(centers, g_band[1], color=color, linewidth=2, label=f"{label}: median, 10th-90th pct")

    dolma(graphs[0])
    rollouts(graphs[1])
    dolma(graphs[2])
    rollouts(graphs[2])
    for ax, title in zip(graphs, ["1. Dolma", "2. Rollouts", "3. Overlay"]):
        style(ax)
        ax.set_yscale("log")
        ax.set_title(title, loc="left", fontsize=15)
        ax.set_xlabel("concept rank by Dolma train χ")
        ax.legend(frameon=False, loc="lower left", fontsize=11)
    graphs[0].set_ylabel("χ (relative to the average concept)")

    # Ratio panel: binned medians over the concepts in the slope (G11, G13), at the rank of each bin's center
    edges = np.array(summary["bin_edges_log_chi_train"])
    at_rank = np.searchsorted(-table["chi_train"].to_numpy(), -np.exp((edges[:-1] + edges[1:]) / 2))
    style(ratio)
    ratio.axhline(0, color=LINE, linewidth=1)
    for name, c, lab in [("V", NULL, "Dolma V (null)"), (g, color, label)]:
        entry = summary["sets"][name] if frame is None else summary["sets"][name]["windows"][frame]
        ratio.plot(at_rank, entry["binned_median_log_ratio"], color=c, linewidth=2, marker="o", markersize=8,
                   markeredgecolor=BG, markeredgewidth=2, label=f"{lab}, slope {entry['slope_chi']:.2f}")
    ratio.set_xlim(graphs[0].get_xlim())
    ratio.set_xlabel("concept rank by Dolma train χ (1 = most common)")
    ratio.set_ylabel("median log(χ / χ train)")
    ratio.legend(frameon=False, loc="lower left", fontsize=12)

    key = "doc" if frame is None else str(frame)
    title = "whole document" if frame is None else f"tokens {settings.WINDOWS[frame][0]}-{settings.WINDOWS[frame][1]}"
    note = f"{summary['docs_per_scope'][key]:,} documents per set"
    if frame is None and g in summary.get("delta_vs_V", {}):
        d = summary["delta_vs_V"][g]
        note += f"; Δ slope vs V {d['delta']:.3f} (95% CI {d['ci95_basic'][0]:.3f} to {d['ci95_basic'][1]:.3f})"
    fig.suptitle(f"Concept distribution, Dolma vs {label} ({title}). {note}", x=0.06, ha="left", fontsize=16)
    path = out / f"{summary['run']}_{g}_{'doc' if frame is None else f'w{frame}'}.png"
    fig.savefig(path, dpi=110, facecolor=BG)
    plt.close(fig)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    table = pd.read_parquet(settings.DATA / args.run / "distribution.parquet").sort_values("chi_train", ascending=False)
    summary = json.loads((settings.RESULTS / f"{args.run}_distribution_summary.json").read_text())
    for g in [g for g in SERIES if f"chi_{g}" in table]:
        paths = [draw(table, summary, g, frame, out) for frame in [None] + list(range(len(settings.WINDOWS)))]
        frames = [Image.open(p).convert("RGB") for p in paths]
        gif = out / f"{args.run}_{g}_animation.gif"
        frames[0].save(gif, save_all=True, append_images=frames[1:], duration=1500, loop=0)
        print("\n".join(str(p) for p in paths + [gif]))


if __name__ == "__main__":
    main()
