"""cc_analysis.py -- benchmark vs training-data concept coverage (CPU only).

Reads cc_*.pt written by cc_compute.py. Writes summary.txt, results.json, flagged_concepts.json.
Run:  python3 cc_analysis.py [--old_tensor s_tilde_pile_pythia70m_topk.pt]
"""
import argparse
import json
import os

import numpy as np

MISSING = 1e-5
BENCHES = ["gsm8k", "mmlu", "arc_challenge", "humaneval"]


# ---------------------------------------------------------------- core math
def s_tilde(d, bos):
    """Eq. 1 per item. bos=True: include BOS position. Returns (N, D) float32."""
    S = np.asarray(d["sum_nobos"], dtype=np.float32)
    L = np.asarray(d["lengths"], dtype=np.float32)
    if bos:
        return (S + np.asarray(d["bos_acts"], dtype=np.float32)) / L[:, None]
    return S / (L - 1.0)[:, None]


def tot(d, bos):
    return s_tilde(d, bos).sum(0).astype(np.float64)


def chi(t):
    """Eq. 2: tot(c) / mean_c' tot(c')."""
    return t / t.mean()


def classify(x):
    """missing: chi<1e-5. Among non-missing: bottom decile = under, top decile = over."""
    missing = x < MISSING
    alive = ~missing
    lo, hi = np.percentile(x[alive], [10, 90])
    under = alive & (x <= lo)
    over = alive & (x >= hi)
    return missing, under, over


def spearman(a, b):
    from scipy.stats import spearmanr
    return float(spearmanr(a, b).correlation)


def gap_stats(chi_bench, chi_ref):
    """How much of the benchmark's concept mass sits on concepts the reference covers poorly?"""
    miss_r, under_r, _ = classify(chi_ref)
    miss_b, _, over_b = classify(chi_bench)
    p = chi_bench / chi_bench.sum()
    both = (~miss_b) & (~miss_r)
    out = {
        "bench_missing_pct": 100 * float(miss_b.mean()),
        "ref_missing_pct": 100 * float(miss_r.mean()),
        "mass_on_ref_missing": float(p[miss_r].sum()),
        "mass_on_ref_under": float(p[under_r].sum()),
        "mass_on_ref_missing_or_under": float(p[miss_r | under_r].sum()),
        "n_bench_active_ref_missing": int(((~miss_b) & miss_r).sum()),
        "n_bench_over_ref_missing_or_under": int((over_b & (miss_r | under_r)).sum()),
        "n_bench_over": int(over_b.sum()),
        "spearman_logchi_both_alive": spearman(np.log(chi_bench[both]), np.log(chi_ref[both])) if both.sum() > 10 else None,
        "n_both_alive": int(both.sum()),
    }
    return out


def split_half(d, bos, seed=0):
    X = s_tilde(d, bos)
    idx = np.random.default_rng(seed).permutation(X.shape[0])
    h = X.shape[0] // 2
    a = chi(X[idx[:h]].sum(0).astype(np.float64))
    b = chi(X[idx[h:]].sum(0).astype(np.float64))
    ma, mb = a < MISSING, b < MISSING
    return {
        "missing_pct_half_A": 100 * float(ma.mean()),
        "missing_pct_half_B": 100 * float(mb.mean()),
        "missing_set_jaccard": float((ma & mb).sum() / max((ma | mb).sum(), 1)),
        "missing_in_A_also_in_B": float((ma & mb).sum() / max(ma.sum(), 1)),
        "spearman_logchi_both_alive": spearman(np.log(a[~ma & ~mb]), np.log(b[~ma & ~mb])),
    }


def cross_bench(chis):
    """Eq. 3 two readings. chis: (B, D). A = divide by |B|; B = divide by number of active benchmarks."""
    act = chis >= MISSING
    a = chis.sum(0) / chis.shape[0]
    n_act = act.sum(0)
    b = np.where(n_act > 0, (chis * act).sum(0) / np.maximum(n_act, 1), 0.0)
    both = (a >= MISSING) & (b >= MISSING)
    return {
        "missing_pct_divide_by_all": 100 * float((a < MISSING).mean()),
        "missing_pct_divide_by_active": 100 * float((b < MISSING).mean()),
        "spearman_logchi_two_readings": spearman(np.log(a[both]), np.log(b[both])),
    }


# ---------------------------------------------------------------- driver
def load(path):
    import torch
    d = torch.load(path, map_location="cpu", weights_only=False)
    return {k: (v.numpy() if hasattr(v, "numpy") else v) for k, v in d.items()}


def flag_concepts(name, bench_d, chi_b, chi_ref, pile_d, k=25, items_per=3):
    miss_r, under_r, _ = classify(chi_ref)
    miss_b, _, over_b = classify(chi_b)
    cand = np.where(over_b & (miss_r | under_r))[0]
    score = chi_b[cand] / (chi_ref[cand] + 1e-3)
    cand = cand[np.argsort(-score)][:k]
    Xb = s_tilde(bench_d, False)
    Xp = s_tilde(pile_d, False)
    out = []
    for c in cand:
        bi = np.argsort(-Xb[:, c])[:items_per]
        pi = np.argsort(-Xp[:, c])[:items_per]
        out.append({
            "concept": int(c),
            "chi_bench": float(chi_b[c]),
            "chi_train_ref": float(chi_ref[c]),
            "ref_status": "missing" if miss_r[c] else "underrepresented",
            "top_benchmark_items": [bench_d["snippets"][i][:200] for i in bi],
            "top_pile_docs": [pile_d["snippets"][i][:200] for i in pi if Xp[i, c] > 0],
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old_tensor", default="s_tilde_pile_pythia70m_topk.pt")
    args = ap.parse_args()
    R, lines = {}, []

    def say(s=""):
        print(s, flush=True)
        lines.append(s)

    inst = load("cc_pile_instream.pt")
    held = load("cc_pile_heldout.pt")
    bench = {b: load(f"cc_{b}.pt") for b in BENCHES if os.path.exists(f"cc_{b}.pt")}

    # 0. sanity: rebuilt with-BOS tensor vs the old one
    if os.path.exists(args.old_tensor):
        import torch
        old = torch.load(args.old_tensor, map_location="cpu").float().numpy()
        new = s_tilde(inst, True)
        if old.shape == new.shape:
            r = float(np.corrcoef(old.ravel()[:5_000_000], new.ravel()[:5_000_000])[0, 1])
            md = float(np.abs(old - new).max())
            say(f"[check] rebuilt with-BOS tensor vs old: corr={r:.6f}, max|diff|={md:.2e}")
            R["old_tensor_check"] = {"corr": r, "max_abs_diff": md}
        else:
            say(f"[check] SHAPE MISMATCH old {old.shape} vs new {new.shape} (different doc filter/truncation?)")
            R["old_tensor_check"] = {"old_shape": list(old.shape), "new_shape": list(new.shape)}
        del old, new
    else:
        say("[check] old tensor not found; skipped")

    # 1. training-side coverage with / without BOS
    pooled_tot = {bos: tot(inst, bos) + tot(held, bos) for bos in (True, False)}
    say("\n== 1. Missing concepts per source (chi<1e-5, share of 32,768) ==")
    say("  pile docs: N in-stream=%d, held-out=%d" % (len(inst["lengths"]), len(held["lengths"])))
    for bos in (True, False):
        tag = "with BOS" if bos else "no BOS  "
        mi, mh = (chi(tot(d, bos)) < MISSING for d in (inst, held))
        mp = chi(pooled_tot[bos]) < MISSING
        say(f"  {tag}: in-stream {100*mi.mean():.2f}%  held-out {100*mh.mean():.2f}%  pooled {100*mp.mean():.2f}%")
        R[f"train_missing_pct_{'bos' if bos else 'nobos'}"] = {
            "instream": 100 * float(mi.mean()), "heldout": 100 * float(mh.mean()), "pooled": 100 * float(mp.mean())}

    say("\n== 2. Split-half stability (in-stream docs, no BOS) ==")
    sh = split_half(inst, False)
    R["split_half"] = sh
    for k_, v in sh.items():
        say(f"  {k_}: {v:.4f}")

    # 3. Benchmark vs training
    say("\n== 3. Benchmark vs training coverage ==")
    refs = {"instream": chi(tot(inst, False)), "heldout": chi(tot(held, False)),
            "pooled": chi(pooled_tot[False])}
    # baseline: held-out Pile vs in-stream reference (same distribution => floor for 'gap mass')
    base = gap_stats(refs["heldout"], refs["instream"])
    R["baseline_heldout_vs_instream"] = base
    say("  baseline (held-out Pile treated as 'benchmark', in-stream as training ref):")
    say(f"    mass on ref missing-or-under = {base['mass_on_ref_missing_or_under']:.4f}, "
        f"spearman = {base['spearman_logchi_both_alive']:.3f}")
    chis_nobos = []
    for b, d in bench.items():
        say(f"\n  -- {b}: N={len(d['lengths'])}, mean tokens={d['lengths'].mean():.1f} --")
        R[b] = {"n": int(len(d["lengths"])), "mean_tokens": float(d["lengths"].mean())}
        for bos in (False, True):
            cb = chi(tot(d, bos))
            if not bos:
                chis_nobos.append(cb)
            for rn, cr in (refs.items() if not bos else [("pooled", chi(pooled_tot[True]))]):
                g = gap_stats(cb, cr)
                key = f"ref_{rn}_{'bos' if bos else 'nobos'}"
                R[b][key] = g
                say(f"    [{'BOS' if bos else 'noBOS'} vs {rn}] bench missing {g['bench_missing_pct']:.2f}% | "
                    f"ref missing {g['ref_missing_pct']:.2f}% | mass on ref missing-or-under {g['mass_on_ref_missing_or_under']:.4f} | "
                    f"bench-over & ref-poor {g['n_bench_over_ref_missing_or_under']}/{g['n_bench_over']} | "
                    f"spearman {g['spearman_logchi_both_alive']:.3f}")

    # 4. Eq. 3 readings
    if chis_nobos:
        say("\n== 4. Eq. 3 divisor (benchmarks combined, no BOS) ==")
        cb = cross_bench(np.stack(chis_nobos))
        R["eq3"] = cb
        for k_, v in cb.items():
            say(f"  {k_}: {v:.4f}")

    # 5. flagged concepts (vs pooled training, no BOS)
    pile_all = {"sum_nobos": np.concatenate([inst["sum_nobos"], held["sum_nobos"]]),
                "lengths": np.concatenate([inst["lengths"], held["lengths"]]),
                "snippets": inst["snippets"] + held["snippets"]}
    flagged = {b: flag_concepts(b, d, chi(tot(d, False)), refs["pooled"], pile_all) for b, d in bench.items()}
    json.dump(flagged, open("flagged_concepts.json", "w"), indent=1)
    say("\n== 5. Flagged concepts written to flagged_concepts.json (top 25 per benchmark) ==")
    for b, f in flagged.items():
        say(f"  {b}: {len(f)} flagged; first: " + (str(f[0]['concept']) if f else "-"))

    json.dump(R, open("results.json", "w"), indent=1)
    open("summary.txt", "w").write("\n".join(lines))
    print("\nwrote summary.txt, results.json, flagged_concepts.json")


if __name__ == "__main__":
    main()
