"""cc_curve.py -- (1) missing-concept rate vs number of Pile docs, (2) stability of flagged concepts.

CPU only. Needs cc_pile_instream.pt, cc_pile_heldout.pt, flagged_concepts.json and the benchmark files.
Writes curve_summary.txt and curve_results.json.
"""
import json

import numpy as np

import cc_analysis as A

SIZES = [100, 300, 1000, 3000, 6000]
DRAWS = 10
SPLITS = 20


def main():
    lines, R = [], {}

    def say(s=""):
        print(s, flush=True)
        lines.append(s)

    inst, held = A.load("cc_pile_instream.pt"), A.load("cc_pile_heldout.pt")
    X = np.concatenate([A.s_tilde(inst, False), A.s_tilde(held, False)])
    n_all = X.shape[0]
    full = A.chi(X.sum(0).astype(np.float64))
    rng = np.random.default_rng(0)

    say(f"== 1. Missing concepts vs number of Pile docs (pooled {n_all} docs, no BOS) ==")
    say("  docs | missing % (mean +- sd over draws) | Spearman of log coverage vs full pooled")
    curve = []
    for n in SIZES + [n_all]:
        reps = 1 if n == n_all else DRAWS
        miss, rho = [], []
        for _ in range(reps):
            idx = rng.choice(n_all, size=n, replace=False)
            c = A.chi(X[idx].sum(0).astype(np.float64))
            both = (c >= A.MISSING) & (full >= A.MISSING)
            miss.append(100 * float((c < A.MISSING).mean()))
            rho.append(A.spearman(np.log(c[both]), np.log(full[both])))
        curve.append({"docs": n, "missing_pct": float(np.mean(miss)), "missing_sd": float(np.std(miss)),
                      "spearman": float(np.mean(rho))})
        say(f"  {n:5d} | {np.mean(miss):6.2f} +- {np.std(miss):.2f} | {np.mean(rho):.3f}")
    R["curve"] = curve

    say(f"\n== 2. Are the flagged concepts stable? ({SPLITS} random half-splits of the pooled Pile as reference) ==")
    flagged = json.load(open("flagged_concepts.json"))
    R["flag_stability"] = {}
    for b, items in flagged.items():
        if not items:
            continue
        d = A.load(f"cc_{b}.pt")
        miss_b, _, over_b = A.classify(A.chi(A.tot(d, False)))
        concepts = [it["concept"] for it in items]
        hits = {c: 0 for c in concepts}
        totals = []
        for _ in range(SPLITS):
            idx = rng.permutation(n_all)[: n_all // 2]
            cr = A.chi(X[idx].sum(0).astype(np.float64))
            miss_r, under_r, _ = A.classify(cr)
            flag = over_b & (miss_r | under_r)
            totals.append(int(flag.sum()))
            for c in concepts:
                hits[c] += int(flag[c])
        R["flag_stability"][b] = {"per_concept_fraction": {str(c): hits[c] / SPLITS for c in concepts},
                                  "n_flagged_per_split_mean": float(np.mean(totals)),
                                  "n_flagged_per_split_sd": float(np.std(totals))}
        say(f"\n  -- {b}: flagged in full pooled Pile = {len(concepts)}; "
            f"flagged per half-split = {np.mean(totals):.1f} +- {np.std(totals):.1f}")
        fr = np.array([hits[c] / SPLITS for c in concepts])
        say(f"     all {len(concepts)} flagged concepts: mean fraction of splits flagged = {fr.mean():.2f}; "
            f"flagged in every split: {int((fr == 1).sum())}; in under half of splits: {int((fr < 0.5).sum())}")
        for c in concepts[:10]:
            say(f"     concept {c}: flagged in {hits[c]}/{SPLITS} splits")
    json.dump(R, open("curve_results.json", "w"), indent=1)
    open("curve_summary.txt", "w").write("\n".join(lines))
    print("\nwrote curve_summary.txt, curve_results.json")


if __name__ == "__main__":
    main()
