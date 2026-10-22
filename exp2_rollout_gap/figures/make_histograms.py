"""Histogram figures for Exp 2 (design.md G28), in the style of CG paper Figs. 3-4: per generator and frame (whole doc,
then each token window), three panels over the same sets as the rank graphs (Dolma train, Dolma V, rollouts):
(a) number of concepts per chi bin, linear chi and log counts, as in the paper; (b) the same over log10 chi;
(c) per-concept ln(chi / chi_train) over the slope concepts (G13), with each set's median.
Reads DATA/<run>/distribution.parquet (or --table) and results/<run>_distribution_summary.json.
Writes <run>_<generator>_hist_<frame>.png for every frame and <run>_<generator>_hist_animation.gif into --out.
Run from this folder: python make_histograms.py --run full [--out DIR] [--table PATH]
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
from make_rollout_figure import BG, FG, NULL, SERIES, style  # noqa: E402  (same colors and axes as the rank graphs)

LOG10_BINS = np.arange(-6, 3.6 + 1e-9, 0.1)  # G28 (b): chi spans about 10^-5 to 10^3.4
RATIO_BINS = np.arange(-5, 4 + 1e-9, 0.1)  # G28 (c): fixed across frames
N_LINEAR_BINS = 50  # G28 (a), as in the paper's figure


def draw(table, summary, g, frame, linear_bins, out):
    """One PNG with panels (a)-(c). frame is None (whole doc) or a window index."""
    suffix = "" if frame is None else f"_w{frame}"
    color, label = SERIES[g]
    sets = [("Dolma train", table["chi_train"].to_numpy(), FG),
            ("Dolma V (held out)", table[f"chi_V{suffix}"].to_numpy(), NULL),
            (label, table[f"chi_{g}{suffix}"].to_numpy(), color)]

    fig, axes = plt.subplots(1, 3, figsize=(21, 8), facecolor=BG, gridspec_kw={"wspace": 0.22})
    fig.subplots_adjust(top=0.88, bottom=0.3)
    for k, (name, chi, c) in enumerate(sets):
        filled = k == 0  # Dolma train as bars, the others as outlines
        kw = dict(color=c, alpha=0.35, edgecolor=c) if filled else dict(histtype="step", color=c, linewidth=2)
        axes[0].hist(chi, bins=linear_bins, label=name, **kw)
        zeros = int((chi == 0).sum())
        axes[1].hist(np.log10(chi[chi > 0]), bins=LOG10_BINS, label=f"{name} ({zeros:,} with χ = 0)", **kw)
        if k == 0:
            continue
        # (c): slope concepts only (G13); chi = 0 in this set is left out and counted (G28)
        y, x = chi[table["in_slope"].to_numpy()], table["chi_train"].to_numpy()[table["in_slope"].to_numpy()]
        ratio = np.log(y[y > 0] / x[y > 0])
        outside = int(((ratio < RATIO_BINS[0]) | (ratio > RATIO_BINS[-1])).sum())
        median = float(np.median(ratio))
        axes[2].hist(ratio, bins=RATIO_BINS, histtype="step", color=c, linewidth=2,
                     label=f"{name}: sd {ratio.std():.2f}, {int((y == 0).sum()):,} with χ = 0, {outside:,} off-axis")
        axes[2].axvline(median, color=c, linestyle="--", linewidth=2, label=f"median {median:.2f}")

    titles = ["(a) χ, linear (as in CG paper Fig. 3)", "(b) log10 χ", "(c) per concept: ln(χ / χ train), slope concepts"]
    xlabels = ["χ (relative to the average concept)", "log10 χ", "ln(χ / χ train)"]
    for ax, title, xlabel in zip(axes, titles, xlabels):
        style(ax)
        ax.set_title(title, loc="left", fontsize=15)
        ax.set_xlabel(xlabel)
        ax.legend(frameon=False, fontsize=11, loc="upper left", bbox_to_anchor=(0, -0.14))  # below, off the data
    axes[0].set_yscale("log")
    axes[0].set_ylabel("number of concepts (log)")
    axes[1].set_ylabel("number of concepts")
    axes[2].axvline(0, color=FG, linewidth=1)

    key = "doc" if frame is None else str(frame)
    scope = "whole document" if frame is None else f"tokens {settings.WINDOWS[frame][0]}-{settings.WINDOWS[frame][1]}"
    fig.suptitle(f"Concept score histograms, Dolma vs {label} ({scope}). "
                 f"{summary['docs_per_scope'][key]:,} documents per set (V and rollouts); Dolma train uses all train docs",
                 x=0.06, ha="left", fontsize=16)
    path = out / f"{summary['run']}_{g}_hist_{'doc' if frame is None else f'w{frame}'}.png"
    fig.savefig(path, dpi=100, facecolor=BG)  # fixed size, so the GIF frames line up
    plt.close(fig)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--table", default=None)  # a local copy of distribution.parquet
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    table = pd.read_parquet(args.table or settings.DATA / args.run / "distribution.parquet")
    summary = json.loads((settings.RESULTS / f"{args.run}_distribution_summary.json").read_text())
    frames = [None] + list(range(len(settings.WINDOWS)))
    # G28 (a): one set of linear bins for every set and frame, so the GIF frames share an x axis
    chi_columns = [c for c in table if c.startswith("chi_") and "no_loops" not in c]
    linear_bins = np.linspace(0, table[chi_columns].to_numpy().max(), N_LINEAR_BINS + 1)
    for g in [g for g in SERIES if f"chi_{g}" in table]:
        paths = [draw(table, summary, g, frame, linear_bins, out) for frame in frames]
        images = [Image.open(p).convert("RGB") for p in paths]
        gif = out / f"{args.run}_{g}_hist_animation.gif"
        images[0].save(gif, save_all=True, append_images=images[1:], duration=1500, loop=0)
        print("\n".join(str(p) for p in paths + [gif]))


if __name__ == "__main__":
    main()
