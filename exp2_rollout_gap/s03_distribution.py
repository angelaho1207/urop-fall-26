"""Concept distribution of Dolma V and of each rollout set, whole doc and per window, and the slope test
(design.md G9-G14). CPU only.

Usage: python s03_distribution.py --run pilot [--degen 0.5]
Reads Exp 1's coverage.parquet, coverage_vs_pile_web.parquet, docs.parquet and acts/ (V docs only), and
DATA/<run>/<generator>/{rollouts,acts} from s01-s02.
Saves DATA/<run>/distribution.parquet and results/<run>_distribution_summary.json.
"""
import argparse
import json

import settings  # first: puts Exp 1 on the path
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.stats import spearmanr

from s05_coverage import MISSING, chi  # Exp 1: e^-5 and Eq. 2

D_SAE = 65_536


def read_part(path, chosen):
    """One acts part (Exp 1 T11 format). chosen maps "doc" and each window index to the doc ids to use (G16).
    Returns the whole-doc Eq. 1 means as a sparse (docs x concepts) matrix, and per window the Eq. 1 sums over
    docs, the firing-doc counts and the number of docs used (G12)."""
    with np.load(path, allow_pickle=True) as z:
        z = {k: z[k] for k in z.files}
    n_docs = len(z["doc_tokens"])
    keep = np.isin(z["doc_id"], chosen["doc"])
    doc_rows = np.repeat(np.arange(n_docs), z["doc_active"])
    means = sparse.csr_matrix((z["doc_mean"].astype(np.float64), (doc_rows, z["doc_latent_ids"].astype(np.int64))),
                              shape=(n_docs, D_SAE))[keep]

    # Token-level CSR: each token lists its active concepts. Recover each entry's doc and position in that doc
    doc_tokens = z["doc_tokens"].astype(np.int64)
    tok_doc = np.repeat(np.arange(n_docs), doc_tokens)
    tok_pos = np.arange(len(tok_doc)) - np.repeat(np.cumsum(doc_tokens) - doc_tokens, doc_tokens)
    ent_tok = np.repeat(np.arange(len(tok_doc)), z["tok_counts"].astype(np.int64))
    ent_doc, ent_pos = tok_doc[ent_tok], tok_pos[ent_tok]
    lat, val = z["latent_ids"].astype(np.int64), z["values"].astype(np.float64)

    windows = []
    for w, (a, b) in enumerate(settings.WINDOWS):
        n_in = np.clip(doc_tokens - a, 0, b - a)  # tokens of each doc inside [a, b)
        doc_in = np.isin(z["doc_id"], chosen[w]) & (n_in > 0)
        m = doc_in[ent_doc] & (ent_pos >= a) & (ent_pos < b)
        sums = np.bincount(lat[m], weights=val[m] / n_in[ent_doc[m]], minlength=D_SAE)  # Eq. 1 within the window
        pairs = np.unique(ent_doc[m] * D_SAE + lat[m])
        fires = np.bincount(pairs % D_SAE, minlength=D_SAE)
        windows.append((sums, fires, int(doc_in.sum())))
    return means, windows


def lengths(paths, keep_of):
    """Token count of every eligible doc, read from the acts parts without loading the activations."""
    out = []
    for path in paths:
        with np.load(path, allow_pickle=True) as z:
            ids, n = z["doc_id"], z["doc_tokens"]
        keep = keep_of(ids)
        out.append(pd.Series(n[keep], index=ids[keep]))
    return pd.concat(out)


def choose(all_lengths):
    """G16: per scope (whole doc, then each window), every set gets the same number of docs: the smallest count
    of docs reaching that scope among all sets, drawn without replacement with a fixed seed."""
    scopes = [("doc", 0)] + [(w, a) for w, (a, _) in enumerate(settings.WINDOWS)]
    chosen = {name: {} for name in all_lengths}
    counts = {}
    for i, (scope, start) in enumerate(scopes):
        eligible = {name: np.sort(n.index[n.to_numpy() > start].to_numpy()) for name, n in all_lengths.items()}
        counts[str(scope)] = n = min(len(e) for e in eligible.values())
        for j, (name, e) in enumerate(eligible.items()):
            chosen[name][scope] = np.random.default_rng([0, 16, i, j]).choice(e, size=n, replace=False)
    return chosen, counts


def read_set(paths, chosen):
    """Concatenate read_part over parts."""
    mats = []
    win = [[np.zeros(D_SAE), np.zeros(D_SAE, dtype=np.int64), 0] for _ in settings.WINDOWS]
    for path in paths:
        means, windows = read_part(path, chosen)
        mats.append(means)
        for w, (s, f, n) in zip(win, windows):
            w[0] += s
            w[1] += f
            w[2] += n
    return sparse.vstack(mats).tocsr(), win


def log_y(values):
    """G13: zeros are set to half the smallest positive value, so the log fit keeps them. Returns the count."""
    zero = values <= 0
    floor = values[~zero].min() / 2
    return np.log(np.where(zero, floor, values)), int(zero.sum())


def slope(x, y_values):
    """G11: OLS slope of log y on x (x is log chi_train over the selected concepts)."""
    y, _ = log_y(y_values)
    xc = x - x.mean()
    return float(xc @ (y - y.mean()) / (xc @ xc))


def bootstrap_slopes(means, x, sel, rng, n_boot, chunk=50):
    """G11: resample docs with replacement, recompute chi (Eq. 2) and the slope, n_boot times."""
    n = means.shape[0]
    out = []
    mt = means.T.tocsr()  # concepts x docs
    for start in range(0, n_boot, chunk):
        size = min(chunk, n_boot - start)
        counts = rng.multinomial(n, np.full(n, 1 / n), size=size).T  # docs x resamples
        sums = np.asarray(mt @ counts).T  # resamples x concepts
        out += [slope(x, chi(s)[sel]) for s in sums]
    return np.array(out)


def binned(x, y_values, edges):
    """G10, G11: median of log(chi_y / chi_train) in each bin of log chi_train."""
    y, _ = log_y(y_values)
    idx = np.clip(np.digitize(x, edges[1:-1]), 0, len(edges) - 2)
    return [round(float(np.median((y - x)[idx == i])), 4) for i in range(len(edges) - 1)]


def degeneration(ids):
    """G14: share of repeated token 4-grams (1 - distinct/total) in the last 256 tokens, where loops sit.
    NaN for rollouts under 64 tokens."""
    if len(ids) < settings.DEGEN_MIN_TOKENS:
        return np.nan
    ids = list(ids)[-settings.DEGEN_TAIL:]
    grams = [tuple(ids[i:i + settings.DEGEN_NGRAM]) for i in range(len(ids) - settings.DEGEN_NGRAM + 1)]
    return 1 - len(set(grams)) / len(grams)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, choices=["pilot", "full"])
    parser.add_argument("--degen", type=float, default=None)  # G14 threshold, set after the pilot
    parser.add_argument("--boot", type=int, default=settings.BOOTSTRAP)
    args = parser.parse_args()
    rng = np.random.default_rng(0)
    run_dir = settings.DATA / args.run

    cov = pd.read_parquet(settings.EXP1_RUN / "coverage.parquet")
    web = pd.read_parquet(settings.EXP1_RUN / "coverage_vs_pile_web.parquet", columns=["n_fire_train"])
    docs = pd.read_parquet(settings.EXP1_RUN / "docs.parquet", columns=["doc_id", "subset"])
    n_train = int((docs["subset"] != "V").sum())
    chi_train = cov["chi_train"].to_numpy()
    sel = (web["n_fire_train"].to_numpy() >= settings.MIN_TRAIN_FIRING_DOCS) & (chi_train >= MISSING)  # G13
    x = np.log(chi_train[sel])
    edges = np.quantile(x, np.linspace(0, 1, settings.N_BINS + 1))
    fire_train = web["n_fire_train"].to_numpy() / n_train
    x_fire = np.log(fire_train[sel])

    # Data sets: V from Exp 1, then each generator that has acts for this run (and its no-loop version, G14)
    v_ids = set(docs.loc[docs["subset"] == "V", "doc_id"])
    paths = {"V": sorted((settings.EXP1_RUN / "acts").glob("part_?????.npz"))}
    all_lengths = {"V": lengths(paths["V"], lambda ids: np.array([d in v_ids for d in ids]))}
    degen = {}
    for g in settings.GENERATORS:
        g_paths = sorted((run_dir / g / "acts").glob("part_?????.npz"))
        if not g_paths:
            continue
        rolls = pd.concat([pd.read_parquet(p) for p in sorted((run_dir / g / "rollouts").glob("part_?????.parquet"))])
        degen[g] = rolls.set_index("rollout_id")["ids"].map(degeneration).astype(float)
        paths[g] = g_paths
        all_lengths[g] = lengths(g_paths, lambda ids: np.ones(len(ids), dtype=bool))
        if args.degen is not None:
            flagged = set(degen[g].index[degen[g] >= args.degen])
            paths[f"{g}_no_loops"] = g_paths
            all_lengths[f"{g}_no_loops"] = lengths(g_paths, lambda ids: np.array([d not in flagged for d in ids]))
    chosen, counts = choose(all_lengths)
    sets = {name: read_set(paths[name], chosen[name]) for name in paths}

    table = pd.DataFrame({"concept": np.arange(D_SAE), "chi_train": chi_train, "in_slope": sel,
                          "n_fire_train": web["n_fire_train"].to_numpy()})
    summary = {"run": args.run, "concepts_in_slope": int(sel.sum()), "bin_edges_log_chi_train": edges.round(4).tolist(),
               "sets": {}}
    summary["docs_per_scope"] = counts
    boots, slopes = {}, {}
    for name, (means, win) in sets.items():
        n = means.shape[0]
        c = chi(np.asarray(means.sum(0)).ravel())
        n_fire = np.diff((means > 0).T.tocsr().indptr)  # docs per concept with a non-zero mean = fires
        table[f"chi_{name}"] = c
        table[f"n_fire_{name}"] = n_fire
        b = slope(x, c[sel])
        boot = bootstrap_slopes(means, x, sel, rng, args.boot)
        boots[name], slopes[name] = boot, b
        _, zeros = log_y(c[sel])
        entry = {
            "docs": n,
            "slope_chi": round(b, 4),
            "slope_chi_ci95_basic": (2 * b - np.quantile(boot, [0.975, 0.025])).round(4).tolist(),  # G17
            "bootstrap_bias": round(float(boot.mean() - b), 4),
            "slope_fire_share": round(slope(x_fire, (n_fire / n)[sel]), 4),  # G9 check
            "selected_concepts_with_chi_0": zeros,
            "binned_median_log_ratio": binned(x, c[sel], edges),
            "windows": [],
        }
        for i, (s, f, nw) in enumerate(win):
            cw = chi(s) if nw else np.zeros(D_SAE)
            table[f"chi_{name}_w{i}"] = cw
            table[f"n_fire_{name}_w{i}"] = f
            entry["windows"].append({"window": list(settings.WINDOWS[i]), "docs": nw,
                                     "slope_chi": round(slope(x, cw[sel]), 4) if nw else None,
                                     "binned_median_log_ratio": binned(x, cw[sel], edges) if nw else None})
        summary["sets"][name] = entry

    # G17: the test statistic, delta = b(set) - b(V) at the same doc count; the noise bias cancels in the difference
    summary["delta_vs_V"] = {}
    for name in sets:
        if name == "V":
            continue
        d, d_boot = slopes[name] - slopes["V"], boots[name] - boots["V"]  # independent resamples of the two sets
        summary["delta_vs_V"][name] = {"delta": round(d, 4),
                                       "ci95_basic": (2 * d - np.quantile(d_boot, [0.975, 0.025])).round(4).tolist(),
                                       "bootstrap_bias": round(float(d_boot.mean() - d), 4)}

    # Pilot check 6: V agrees with train as in Exp 1 C3. V is subsampled here (G16), so its chi differs from Exp 1's
    # chi_V; the exact match with all 9,955 V docs was checked on 2026-10-21 (max relative difference 0)
    both = (chi_train >= MISSING) & (table["chi_V"].to_numpy() >= MISSING)
    summary["check_V"] = {
        "spearman_log_chi_V_vs_train": round(float(spearmanr(np.log(chi_train[both]), np.log(table["chi_V"][both])).statistic), 4),
    }
    summary["degeneration"] = {g: {"rollouts_scored": int(d.notna().sum()),
                                   "quantiles": {q: round(float(d.dropna().quantile(q)), 3) for q in (0.5, 0.9, 0.95, 0.99)},
                                   "flagged": int((d >= args.degen).sum()) if args.degen is not None else None}
                               for g, d in degen.items()}
    summary["degeneration_threshold"] = args.degen
    run_dir.mkdir(parents=True, exist_ok=True)
    settings.RESULTS.mkdir(exist_ok=True)
    table.to_parquet(run_dir / "distribution.parquet")
    (settings.RESULTS / f"{args.run}_distribution_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "bin_edges_log_chi_train"}, indent=1)[:6000])


if __name__ == "__main__":
    main()
