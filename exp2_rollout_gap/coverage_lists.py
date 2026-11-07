"""Pure logic of the coverage-list run (design.md G95-G97): lists, Jaccard overlap and rerun stability. Numpy only, testable
without pool data.
"""
import numpy as np

EPSILON = float(np.exp(-5))  # CG paper Sec. 3.1; equals Exp 1's MISSING, asserted in s29
N_LIST = 10  # G95: CG paper Sec. 4.2.1
N_RERUNS, DROP = 100, 0.2  # G96: CG paper App. B.3, as G72
SEED_ROW = 96  # G96


def top_k(chi, k=N_LIST):
    """Highest chi first, ties by concept id."""
    return np.argsort(-chi, kind="stable")[:k]


def zeros(chi):
    """Every concept with chi = 0, in id order."""
    return np.flatnonzero(chi == 0)


def bottom_k_above(chi, k=N_LIST, eps=EPSILON):
    """Lowest chi among chi >= e^-5 first, ties by concept id."""
    above = np.flatnonzero(chi >= eps)
    return above[np.argsort(chi[above], kind="stable")][:k]


def lists_of(chi):
    return {"top": top_k(chi), "zero": zeros(chi), "bottom": bottom_k_above(chi)}


def jaccard(a, b):
    """CG paper Fig. 28: |A and B| / |A or B|; None for two empty sets."""
    a, b = set(map(int, a)), set(map(int, b))
    return round(len(a & b) / len(a | b), 4) if a | b else None


def rerun_stability(sums_of, n_docs, seed_prefix, chi_of, full, n_reruns=N_RERUNS, drop=DROP):
    """G96: keep a random (1 - drop) of the same docs, recompute chi, rebuild the top and bottom lists.
    sums_of(weights) gives per-concept summed means over the docs with weight 1; chi_of(sums) is Eq. 2; full holds the
    lists from the published chi. Returns, per list, {concept: share of reruns it stays} and the mean share of the list that
    stays, plus the lists rebuilt from all the docs (to compare with full)."""
    rebuilt = lists_of(chi_of(sums_of(np.ones(n_docs))))
    keep = int(round(n_docs * (1 - drop)))
    stays = {name: {int(c): 0 for c in full[name]} for name in ("top", "bottom")}
    overlap = {name: [] for name in stays}
    for r in range(n_reruns):
        weights = np.zeros(n_docs)
        weights[np.random.default_rng([*seed_prefix[:2], r, *seed_prefix[2:]]).choice(n_docs, size=keep, replace=False)] = 1.0
        chi = chi_of(sums_of(weights))
        again = {"top": set(map(int, top_k(chi))), "bottom": set(map(int, bottom_k_above(chi)))}
        for name in stays:
            for c in stays[name]:
                stays[name][c] += c in again[name]
            overlap[name].append(len(again[name] & set(stays[name])) / max(len(stays[name]), 1))
    return ({name: {c: round(v / n_reruns, 4) for c, v in d.items()} for name, d in stays.items()},
            {name: round(float(np.mean(v)), 4) for name, v in overlap.items()}, rebuilt)
