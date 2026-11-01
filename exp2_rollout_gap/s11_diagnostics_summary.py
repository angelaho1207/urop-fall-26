"""Short results summary of the full_post diagnostics (design.md G40-G45). CPU only, seconds.

Usage: python s11_diagnostics_summary.py
Reads results/full_post_diagnostics.json (s09), results/full_post_{lenmatch,min30}_distribution_summary.json (s10)
and results/full_post_distribution_summary.json (s03). Writes results/full_post_diagnostics_summary.md.
The opening answer is filled from the numbers; it is meant to be read and edited.
"""
import json

import settings
from diag_common import SHOWN

R = settings.RESULTS


def load(name):
    p = R / name
    return json.loads(p.read_text()) if p.exists() else None


def pct(v):
    return f"{100 * v:.0f}%"


def main():
    diag = load("full_post_diagnostics.json")
    pub = load("full_post_distribution_summary.json")
    runs = {k: load(f"full_post_{k}_distribution_summary.json") for k in ("lenmatch", "min30")}
    s = diag["sets"]
    sv = {g: s[g]["shape_vs_shuffle"] for g in ["V"] + SHOWN}
    shape = [sv[g]["shape_share"] for g in SHOWN]
    med = [s[g]["median_log10_ratio"] for g in SHOWN]
    mass = [s[g]["mass_share_of_concepts_above_1x"] for g in SHOWN]
    above = [s[g]["share_slope_concepts_below_1x"] for g in SHOWN]
    trend = [s[g]["variance_split"]["trend_share"] for g in SHOWN]

    md = ["# Exp 2 full_post diagnostics (design.md G39-G45)\n",
          "\nSets: Dolma V (null) and rollouts of stage1, main (final base), Instruct-SFT, -DPO, -Instruct; 7,985 docs each "
          "(G16), slope concepts as G13. Draft answer generated from the numbers; edit after reading.\n",
          "\n## Sheng-Yu's question\n\n"
          f"Panels (a)-(b) compare the two χ distributions without pairing concepts, (c) pairs them. Sorting both sides and "
          f"matching quantiles keeps {pct(min(shape))}-{pct(max(shape))} of the per-concept squared distance (D_marg / D_pair) "
          f"across the five rollout sets; the other {pct(1 - max(shape))}-{pct(1 - min(shape))} is concepts trading places, "
          f"which (a)-(b) cannot show. The median shift is {min(med):+.2f} to {max(med):+.2f} in log10. "
          f"{pct(min(above))}-{pct(max(above))} of slope concepts fall below 1×, while the concepts above 1× hold "
          f"{pct(min(mass))}-{pct(max(mass))} of all χ mass (χ sums to 65,536 in every set). The slope's trend describes "
          f"{100 * min(trend):.2f}-{100 * max(trend):.2f}% of the per-concept variance.\n"]

    md.append("\n| set | median ln ratio (log10) | below 1× | D_pair | D_marg (loc / scale / rest) | shape share | shuffle share | Spearman | split-half noise var |\n|---|---|---|---|---|---|---|---|---|\n")
    for g in ["V"] + SHOWN:
        v = sv[g]
        md.append(f"| {g} | {s[g]['median_ln_ratio']:+.3f} ({s[g]['median_log10_ratio']:+.3f}) | {pct(s[g]['share_slope_concepts_below_1x'])} | "
                  f"{v['D_pair']:.3f} | {v['D_marg']:.3f} ({v['D_marg_location']:.3f} / {v['D_marg_scale']:.3f} / {v['D_marg_rest']:.3f}) | "
                  f"{pct(v['shape_share'])} | {pct(v['shuffle_share'])} | {v['spearman']:.3f} | {s[g]['noise_var_split_half']:.3f} |\n")

    md.append("\n## Item 1: where the χ mass went (G41)\n\n| set | top 10 / 100 / 1,000 share | mass moved (TV) | TV share, top 30 / 1,000 gainers | concepts above 1×: χ mass in set (in train) | top 3 gainers (concept: gain, mean position, share from docs < 30 tokens) |\n|---|---|---|---|---|---|\n")
    t = diag["train_top_k_mass_share"]
    md.append(f"| train | {pct(t['10'])} / {pct(t['100'])} / {pct(t['1000'])} | | | | |\n")
    for g in ["V"] + SHOWN:
        k = s[g]["top_k_mass_share"]
        top = "; ".join(f"{r['concept']}: {r['mass_gain_share']:.1%}, pos {r['mean_token_position']}, short {r['share_chi_from_docs_under_30']}"
                        for r in diag["gainers"][g][:3])
        md.append(f"| {g} | {pct(k['10'])} / {pct(k['100'])} / {pct(k['1000'])} | {pct(s[g]['tv_distance_to_train'])} | "
                  f"{pct(s[g]['tv_share_top_30_gainers'])} / {pct(s[g]['tv_share_top_1000_gainers'])} | "
                  f"{pct(s[g]['mass_share_of_concepts_above_1x'])} ({pct(s[g]['train_mass_share_of_same_concepts'])}) | {top} |\n")

    md.append("\n## Item 2: what the slope describes (G42)\n\n| set | b | Var(r) | trend share | Var(e) | excess dispersion var (sd) |\n|---|---|---|---|---|---|\n")
    for g in ["V"] + SHOWN:
        v = s[g]["variance_split"]
        md.append(f"| {g} | {v['b']:.4f} | {v['var_r']:.3f} | {100 * v['trend_share']:.2f}% | {v['var_e']:.3f} | "
                  f"{s[g]['excess_dispersion_var']:.3f} ({s[g]['excess_dispersion_sd']:.2f}) |\n")
    md.append(f"\nTrain noise variance (Var(r_V) − V's split-half noise): {diag['noise_train_var']:.4f}.\n")

    md.append("\n## Item 3: length (G43), Δ slope vs V (bias-corrected, G45)\n\n| set | full_post | lenmatch | min30 | docs < 30 tokens |\n|---|---|---|---|---|\n")
    docs = {k: (r["sets"]["V"]["docs"] if r else None) for k, r in runs.items()}
    for g in SHOWN:
        cells = [f"{pub['delta_vs_V'][g]['delta']:+.4f} ({diag['full_post_delta_bias_corrected'][g]['delta_bias_corrected']:+.4f})"]
        for k, r in runs.items():
            cells.append(f"{r['delta_vs_V'][g]['delta']:+.4f} ({r['delta_vs_V'][g]['delta_bias_corrected']:+.4f}) "
                         f"[{r['delta_vs_V'][g]['ci95_basic'][0]:+.4f}, {r['delta_vs_V'][g]['ci95_basic'][1]:+.4f}]" if r else "missing")
        md.append(f"| {g} | " + " | ".join(cells) + f" | {pct(s[g]['share_docs_under_30_tokens'])} |\n")
    md.append(f"| docs per set | {pub['docs_per_scope']['doc']:,} | {docs['lenmatch']} | {docs['min30']} | V {pct(s['V']['share_docs_under_30_tokens'])} |\n")
    if all(runs.values()):
        md.append("\nMedian ln ratio (all → lenmatch → min30): " + "; ".join(
            f"{g} {s[g]['median_ln_ratio']:+.2f} → {runs['lenmatch']['sets'][g]['median_ln_ratio']:+.2f} → {runs['min30']['sets'][g]['median_ln_ratio']:+.2f}"
            for g in SHOWN) + ".\n")

    md.append("\n## Item 8: Δ slope vs V by concept range (G44; bias-corrected in parentheses)\n\n| set | all | without rarest 3 bins | without top bin | middle 16 bins |\n|---|---|---|---|---|\n")
    for g in SHOWN:
        d = diag["delta_by_range"][g]
        md.append(f"| {g} | " + " | ".join(f"{d[k]['delta']:+.4f} ({d[k]['delta_bias_corrected']:+.4f}) [{d[k]['ci95_basic'][0]:+.4f}, {d[k]['ci95_basic'][1]:+.4f}]"
                                            for k in ["all", "without_rarest_3_bins", "without_top_bin", "middle_16_bins"]) + " |\n")
    md.append("\nBinned median ln ratio minus V's (rarest bin first): " + "; ".join(
        f"{g} " + ", ".join(f"{v:+.2f}" for v in diag["binned_minus_V"][g]) for g in ["stage1", "main"]) + ".\n")
    (R / "full_post_diagnostics_summary.md").write_text("".join(md))
    print("".join(md))


if __name__ == "__main__":
    main()
