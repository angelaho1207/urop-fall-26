"""Slide figures not on the HF Space: tier artifact (experiment 6) and faithfulness gaps (experiment 13).

Numbers come from results/full_vs_pile_summary.json, results/faith_analysis_summary.json and design.md
(paper-class tier shares, "Pile reference" section). Colors match space/style.css.
Run from this folder: python make_slide_figures.py
"""
import json

import matplotlib.pyplot as plt

BG, FG, MUTED, LINE = "#fbfbfa", "#1d1d1f", "#6b6b70", "#e2e2e0"
OVER, UNDER, MIDDLE = "#d1601f", "#2a6fb0", "#9a9a9a"
TIER_COLORS = ["#184f95", "#5598e7", "#b7d3f6"]  # ids 0-2,047 / 2,048-16,383 / 16,384-65,535

plt.rcParams.update({"font.family": "Arial", "font.size": 15, "text.color": FG,
                     "axes.labelcolor": FG, "xtick.color": MUTED, "ytick.color": FG})


def tier_artifact():
    pile_ref = json.load(open("../results/full_vs_pile_summary.json"))["tier_share_by_class"]
    tiers = ["0-2047", "2048-16383", "16384-65535"]
    rows = [  # (label, shares in %), paper-class shares from design.md "Pile reference" section
        ("All 65,536 concepts", [3.1, 21.9, 75.0]),
        ('Paper classes: "over"', [34.6, 63.8, 1.6]),
        ('Paper classes: "under"', [0.0, 6.0, 94.0]),
        ('Vs the Pile: "over"', [100 * pile_ref["over"][t] for t in tiers]),
        ('Vs the Pile: "under"', [100 * pile_ref["under"][t] for t in tiers]),
    ]
    fig, ax = plt.subplots(figsize=(12, 4.6), facecolor=BG)
    ax.set_facecolor(BG)
    for row, (label, shares) in enumerate(rows):
        left = 0
        for tier_index, share in enumerate(shares):
            ax.barh(row, share, left=left, height=0.62, color=TIER_COLORS[tier_index],
                    edgecolor=BG, linewidth=2)
            if share >= 6:
                ax.text(left + share / 2, row, f"{share:.0f}%", va="center", ha="center",
                        color="white" if tier_index < 2 else FG, fontsize=13)
            left += share
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("share of the class's concepts in each Matryoshka tier (%)")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(LINE)
    ax.tick_params(axis="y", length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in TIER_COLORS]
    ax.legend(handles, ["ids 0-2,047 (broadest)", "ids 2,048-16,383", "ids 16,384-65,535 (most specific)"],
              loc="upper center", bbox_to_anchor=(0.45, -0.2), ncol=3, frameon=False, fontsize=13)
    fig.tight_layout()
    fig.savefig("chart_tier_artifact.png", dpi=200, facecolor=BG)


def faithfulness_gaps():
    summary = json.load(open("../results/faith_analysis_summary.json"))["classes"]
    rows = [("over", OVER), ("under", UNDER), ("middle", MIDDLE)]
    fig, ax = plt.subplots(figsize=(12, 4.2), facecolor=BG)
    ax.set_facecolor(BG)
    for row, (cls, color) in enumerate(rows):
        c = summary[cls]
        low, high = c["gap_ci95"]
        ax.plot([low, high], [row, row], color=color, linewidth=3, solid_capstyle="round")
        ax.plot(c["gap_mean"], row, "o", color=color, markersize=11, markeredgecolor=BG, markeredgewidth=2)
        ax.text(0.047, row, f'Pile name {c["pile_name_mean"]:.3f}   Dolma name {c["dolma_name_mean"]:.3f}   '
                f'(n = {c["concepts_scored"]})', va="center", fontsize=13, color=MUTED)
    # all 227 concepts, from design.md "F run results"
    ax.plot([0.003, 0.019], [3, 3], color=FG, linewidth=3, solid_capstyle="round")
    ax.plot(0.011, 3, "o", color=FG, markersize=11, markeredgecolor=BG, markeredgewidth=2)
    ax.text(0.047, 3, "Pile name 0.748   Dolma name 0.759   (n = 227)", va="center", fontsize=13, color=MUTED)
    ax.axvline(0, color=MUTED, linewidth=1, linestyle="--")
    ax.set_yticks(range(4), ["over", "under", "middle", "all"])
    ax.invert_yaxis()
    ax.set_xlim(-0.02, 0.12)
    ax.set_xticks([-0.02, 0, 0.02, 0.04])
    ax.set_xlabel("paired gap in detection score, Dolma name minus Pile name (mean, 95% bootstrap interval)")
    ax.xaxis.set_label_coords(0.33, -0.15)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(LINE)
    ax.spines["bottom"].set_bounds(-0.02, 0.04)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout()
    fig.savefig("chart_faithfulness_gap.png", dpi=200, facecolor=BG)


if __name__ == "__main__":
    tier_artifact()
    faithfulness_gaps()
