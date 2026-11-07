"""Pure logic of the missing-concept run (design.md G87-G92): list membership, draws, baseline counts and theme statistics.
Numpy only, so it can be tested without pool data or a GPU.
"""
import numpy as np

EPSILON = float(np.exp(-5))  # CG paper Sec. 3.1; equals Exp 1's MISSING, asserted in s26
N_RANDOM, N_EXTREME, MIN_PRESENT_DOCS = 80, 50, 50  # G88: the same sizes and floor as G70
DIRECTIONS = ["in_dolma_missing_rollouts", "in_rollouts_missing_dolma"]  # G87: lists A and B


def members_of(direction, chi_train, chi_set):
    """G87: every concept qualifies; there is no firing floor here."""
    if direction == DIRECTIONS[0]:
        return np.flatnonzero((chi_train >= EPSILON) & (chi_set < EPSILON))
    return np.flatnonzero((chi_train < EPSILON) & (chi_set >= EPSILON))


def log_ratio(chi_train, chi_set):
    """r = ln(chi_rollout / chi_train). chi_rollout = 0 gives -inf, chi_train = 0 gives +inf."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(chi_set) - np.log(chi_train)


def extreme_order(direction, r, members):
    """G88: most extreme first, ties by concept id (members are ascending and the sort is stable)."""
    key = r[members] if direction == DIRECTIONS[0] else -r[members]
    return members[np.argsort(key, kind="stable")]


def choose_lists(direction, chi_train, chi_set, fire_present, seed):
    """G88: the random draw and both extreme lists of one model and direction. fire_present counts firing docs on the side
    where the concept is present (Dolma train for A, rollouts for B)."""
    members = members_of(direction, chi_train, chi_set)
    r = log_ratio(chi_train, chi_set)
    order = extreme_order(direction, r, members)
    passing = order[fire_present[order] >= MIN_PRESENT_DOCS]
    rng = np.random.default_rng(seed)
    random_draw = np.sort(rng.choice(members, size=min(N_RANDOM, len(members)), replace=False)) if len(members) else members
    return {"random": random_draw, "extreme_unfiltered": order[:N_EXTREME], "extreme_filtered": passing[:N_EXTREME]}, members, r


def v_agrees(direction, chi_v):
    """G89: held-out Dolma, at the same doc count as the rollouts, falls on the rollouts' side of the cutoff."""
    return chi_v < EPSILON if direction == DIRECTIONS[0] else chi_v >= EPSILON


def share_quantiles(values):
    """G92: quartiles of a per-concept share, None when there is nothing to describe."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return {"n": int(len(values)), "q25": round(float(np.quantile(values, 0.25)), 4), "median": round(float(np.median(values)), 4),
            "q75": round(float(np.quantile(values, 0.75)), 4)} if len(values) else {"n": 0, "q25": None, "median": None, "q75": None}


def garbled_share(means_sum_flagged, means_sum_all):
    """G92: per concept, the share of its summed Eq. 1 means from flagged docs; nan where it never fires in these docs."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(means_sum_all > 0, means_sum_flagged / means_sum_all, np.nan)


def cohen_kappa(a, b, categories):
    """G91, Exp 1 Q4: chance-corrected agreement of two codings over the concepts both answered."""
    a, b = np.asarray(a, dtype=object), np.asarray(b, dtype=object)
    if not len(a):
        return None, None
    observed = float((a == b).mean())
    chance = sum(float((a == c).mean()) * float((b == c).mean()) for c in categories)
    return round((observed - chance) / (1 - chance), 4) if chance < 1 else None, round(observed, 4)


def category_shares(labels, categories, rng, n_boot=10_000):
    """G91, Exp 1 Q4: {category: [share, 2.5th, 97.5th percentile]} with a bootstrap over concepts."""
    labels = np.asarray(labels, dtype=object)
    if not len(labels):
        return {c: [None, None, None] for c in categories}
    out = {}
    index = rng.integers(0, len(labels), (n_boot, len(labels)))
    for c in categories:
        flags = (labels == c).astype(float)
        boots = flags[index].mean(1)
        out[c] = [round(float(flags.mean()), 4), round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)]
    return out


def check_scheme(categories, unclear):
    """Exp 1 s13: 8-12 categories plus the unclear one, no duplicate names."""
    names = [c["name"] for c in categories]
    problems = []
    if not 8 <= len(categories) <= 13:
        problems.append(f"{len(categories)} categories (asked for 8-12 plus the unclear one)")
    if unclear not in names:
        problems.append(f"no '{unclear}' category")
    if len(set(names)) != len(names):
        problems.append("duplicate names")
    return problems
