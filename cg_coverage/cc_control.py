"""cc_control.py -- length- and size-matched Pile control for the benchmark coverage numbers.

For each benchmark, draw N_bench Pile items (truncated to ~64 or ~128 tokens) many times and compare
missing%, Spearman vs the full in-stream reference, and mass on poorly covered concepts.
Needs cc_pile_len64.pt, cc_pile_len128.pt, cc_pile_instream.pt and the benchmark files.
"""
import json
import sys

import numpy as np

import cc_analysis as A

REPS = 20
SUFFIX = sys.argv[1] if len(sys.argv) > 1 else ""


def metrics(chi_x, chi_ref):
    g = A.gap_stats(chi_x, chi_ref)
    return {"missing_pct": g["bench_missing_pct"], "spearman": g["spearman_logchi_both_alive"],
            "mass_poor": g["mass_on_ref_missing_or_under"]}


def main():
    lines, R = [], {}

    def say(s=""):
        print(s, flush=True)
        lines.append(s)

    inst = A.load("cc_pile_instream.pt")
    ref = A.chi(A.tot(inst, False))
    ctrl = {}
    for L in (32, 64, 128):
        try:
            ctrl[L] = A.load(f"cc_pile_heldout_len{L}.pt")
        except FileNotFoundError:
            pass
    for L, d in ctrl.items():
        say(f"control len{L}: N={len(d['lengths'])}, mean tokens={d['lengths'].mean():.1f}")
    Xc = {L: A.s_tilde(d, False) for L, d in ctrl.items()}
    rng = np.random.default_rng(0)

    say("\nbenchmark vs size/length-matched Pile control (mean +- sd over %d draws)" % REPS)
    for b in A.BENCHES:
        try:
            d = A.load(f"cc_{b}{SUFFIX}.pt")
        except FileNotFoundError:
            continue
        n, mt = len(d["lengths"]), float(d["lengths"].mean())
        L = min(ctrl, key=lambda k: abs(float(ctrl[k]["lengths"].mean()) - mt))  # closest mean length
        X = Xc[L]
        bm = metrics(A.chi(A.tot(d, False)), ref)
        reps = []
        for _ in range(REPS):
            idx = rng.choice(X.shape[0], size=min(n, X.shape[0]), replace=False)
            reps.append(metrics(A.chi(X[idx].sum(0).astype(np.float64)), ref))
        R[b] = {"n": n, "mean_tokens": mt, "control_len": L, "bench": bm,
                "control_mean": {k: float(np.mean([r[k] for r in reps])) for k in bm},
                "control_sd": {k: float(np.std([r[k] for r in reps])) for k in bm}}
        say(f"\n-- {b}: N={n}, mean tokens={mt:.1f}, control = Pile cut to {L} tokens (mean {ctrl[L]['lengths'].mean():.1f}), N={min(n, X.shape[0])} --")
        for k in bm:
            c, s = R[b]["control_mean"][k], R[b]["control_sd"][k]
            say(f"  {k:12s} bench {bm[k]:.4f} | control {c:.4f} +- {s:.4f} | diff {bm[k]-c:+.4f}")
    json.dump(R, open(f"control_results{SUFFIX}.json", "w"), indent=1)
    open(f"control_summary{SUFFIX}.txt", "w").write("\n".join(lines))
    print(f"\nwrote control_summary{SUFFIX}.txt")


if __name__ == "__main__":
    main()
