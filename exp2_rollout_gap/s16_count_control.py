"""Doc-count control for the garbled check (design.md G60). CPU only.

Usage: python s16_count_control.py --seed 0     # one random drop (no flag) to G58's count; seeds 0-19
       python s16_count_control.py --check     # measure() on G58's own docs must reproduce the noflag summary
       python s16_count_control.py --summary   # full_post, noflag and the 20 control draws side by side
Per seed: DATA/full_post_countctl/seed_<s>.json. Summary: results/full_post_countctl_summary.{json,md}.
"""
import argparse
import json

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import numpy as np

import diag_common as dc
from s14_nll import GENERATORS
from s15_garbled import NOFLAG, R, RUN, measure, read_nll

SEEDS = range(20)  # G60
OUT = settings.DATA / f"{RUN}_countctl"
STATS = ["delta", "delta_bias_corrected", "excess_dispersion_sd", "median_ln_ratio"]


def stats(summary, g):
    d, s = summary["delta_vs_V"][g], summary["sets"][g]
    return {"delta": d["delta"], "delta_bias_corrected": d["delta_bias_corrected"],
            "excess_dispersion_sd": s["excess_dispersion_sd"], "median_ln_ratio": s["median_ln_ratio"]}


def run_seed(seed):
    n = json.loads((R / f"{NOFLAG}_distribution_summary.json").read_text())["docs"]  # 5,751 (G58)
    c = dc.concepts()
    paths, all_lengths = dc.set_lengths()
    chosen = {name: np.random.default_rng([0, 60, seed, j]).choice(np.sort(lens.index.to_numpy()), size=n, replace=False)
              for j, (name, lens) in enumerate(all_lengths.items())}
    summary, _ = measure(c, paths, chosen)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"seed_{seed:02d}.json").write_text(json.dumps({"seed": seed, "docs": n, **summary}, indent=1))
    print(seed, {g: stats(summary, g) for g in dc.SHOWN}, flush=True)


def check():
    """G60: the refactored measure() on G58's docs (same seeds) gives the published noflag numbers."""
    thr = json.loads((R / f"{RUN}_garbled_threshold.json").read_text())["threshold_nats"]
    drop = {}
    for s in ["V"] + GENERATORS:
        d = read_nll(s)
        drop[s] = set(d.index[(d["nll_mean"] > thr) | d["nll_mean"].isna()])
    c = dc.concepts()
    paths, all_lengths = dc.set_lengths()
    eligible = {name: np.sort(lens.index[~lens.index.isin(list(drop[name.replace("_no_loops", "")]))].to_numpy()) for name, lens in all_lengths.items()}
    n = min(len(e) for e in eligible.values())
    chosen = {name: np.random.default_rng([0, 58, 9, j]).choice(e, size=n, replace=False) for j, (name, e) in enumerate(eligible.items())}
    summary, _ = measure(c, paths, chosen)
    pub = json.loads((R / f"{NOFLAG}_distribution_summary.json").read_text())
    diff = max(abs(stats(summary, g)[k] - stats(pub, g)[k]) for g in dc.SHOWN for k in STATS)
    print("max difference from published noflag:", diff, flush=True)
    if diff > 0:
        raise SystemExit("G60: measure() does not reproduce the noflag summary")


def summarize():
    pub = json.loads((R / f"{RUN}_distribution_summary.json").read_text())
    diag = json.loads((R / f"{RUN}_diagnostics.json").read_text())
    noflag = json.loads((R / f"{NOFLAG}_distribution_summary.json").read_text())
    seeds = [json.loads((OUT / f"seed_{s:02d}.json").read_text()) for s in SEEDS if (OUT / f"seed_{s:02d}.json").exists()]
    report = {"docs": noflag["docs"], "seeds_done": len(seeds), "seeds_planned": len(SEEDS), "sets": {}}
    for g in dc.SHOWN:
        full = {"delta": pub["delta_vs_V"][g]["delta"], "delta_bias_corrected": diag["full_post_delta_bias_corrected"][g]["delta_bias_corrected"],
                "excess_dispersion_sd": diag["sets"][g]["excess_dispersion_sd"], "median_ln_ratio": diag["sets"][g]["median_ln_ratio"]}
        nf = stats(noflag, g)
        entry = {}
        for k in STATS:
            v = np.array([stats(s, g)[k] for s in seeds])
            mean, sd = float(v.mean()), float(v.std(ddof=1))
            entry[k] = {"full_post": full[k], "noflag": nf[k], "control_mean": round(mean, 4), "control_sd": round(sd, 4),
                        "control_min": round(float(v.min()), 4), "control_max": round(float(v.max()), 4),
                        "count_effect": round(mean - full[k], 4), "filter_effect": round(nf[k] - mean, 4),
                        "filter_effect_in_sd": round((nf[k] - mean) / sd, 1) if sd > 0 else None,
                        "noflag_outside_control_range": bool(nf[k] < v.min() or nf[k] > v.max())}
        report["sets"][g] = entry
    (R / f"{RUN}_countctl_summary.json").write_text(json.dumps(report, indent=1))
    md = [f"# Exp 2 doc-count control (design.md G60)\n\nEvery set drawn at random (no flag) to {report['docs']:,} docs, "
          f"{report['seeds_done']} of {report['seeds_planned']} seeds. Count effect = control mean − full_post; filter effect = noflag − control mean "
          "(in control sd units in parentheses).\n"]
    for k, title in (("delta_bias_corrected", "Δ vs V, bias-corrected (G45)"), ("delta", "Δ vs V"),
                     ("excess_dispersion_sd", "Excess dispersion sd (G42)"), ("median_ln_ratio", "Median ln ratio")):
        md.append(f"\n## {title}\n\n| set | full_post | noflag | control mean ± sd [min, max] | count effect | filter effect |\n|---|---|---|---|---|---|\n")
        for g, e in report["sets"].items():
            x = e[k]
            md.append(f"| {g} | {x['full_post']:+.4f} | {x['noflag']:+.4f} | {x['control_mean']:+.4f} ± {x['control_sd']:.4f} "
                      f"[{x['control_min']:+.4f}, {x['control_max']:+.4f}] | {x['count_effect']:+.4f} | {x['filter_effect']:+.4f} ({x['filter_effect_in_sd']}) |\n")
    (R / f"{RUN}_countctl_summary.md").write_text("".join(md))
    print("".join(md))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed", type=int)
    group.add_argument("--check", action="store_true")
    group.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    elif args.summary:
        summarize()
    else:
        run_seed(args.seed)
