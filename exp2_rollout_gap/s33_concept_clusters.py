"""Concept clusters: spectral clustering of the top-11 decoder-neighbour graph, and whether classes concentrate in clusters
(design.md G105-G108). CPU, $0.

Usage: python s33_concept_clusters.py
Reads DATA/full_post/similarity/neighbours.npz (s32), DATA/full_post/distribution.parquet and notes/name_cache.json. Writes
DATA/full_post/similarity/clusters.npz and results/full_post_clusters_summary.{json,md} (ids, names, numbers).
"""
import json

import numpy as np
from scipy import sparse
from scipy.cluster.vq import kmeans2
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import eigsh
from scipy.special import comb

K_MAX = 100  # G106
N_SEEDS = 10  # G106
N_PERM, BIN = 100, 1000  # G107


def knn_graph(ids, cos):
    """G105: the k-nearest-neighbour graph (linked if either is in the other's top k), weight = cosine clipped at 0, and the
    concepts with no mutual neighbour (saved for naming later)."""
    n, k = ids.shape
    a = sparse.csr_matrix((np.clip(cos.ravel(), 0, None), (np.repeat(np.arange(n), k), ids.ravel())), shape=(n, n))
    mutual = a.minimum(a.T)  # zero unless both directions exist
    return a.maximum(a.T).tocsr(), np.flatnonzero(np.asarray((mutual > 0).sum(1)).ravel() == 0)


def spectral(w, k_max=K_MAX, n_seeds=N_SEEDS):
    """G106: normalized spectral clustering (Ng-Jordan-Weiss) of a connected graph, K by the largest eigengap."""
    w = w.astype(np.float64)  # float32 cosines leave eigenvalue rounding near 1e-6
    d = np.asarray(w.sum(1)).ravel()
    inv = sparse.diags(1 / np.sqrt(d))
    mu, vec = eigsh(inv @ w @ inv, k=k_max + 1, which="LA")
    order = np.argsort(-mu)
    lam, vec = 1 - mu[order], vec[:, order]  # eigenvalues of the normalized Laplacian, ascending
    gaps = np.diff(lam)  # gaps[j] = lam[j + 1] - lam[j]; K clusters leave the gap after the K-th eigenvalue
    k = int(np.argmax(gaps[1:k_max])) + 2  # K from 2 to k_max
    u = vec[:, :k] / np.linalg.norm(vec[:, :k], axis=1, keepdims=True)
    runs = [kmeans2(u, k, minit="++", seed=s)[1] for s in range(n_seeds)]
    return runs[0], k, lam, [round(adjusted_rand(runs[0], r), 4) for r in runs[1:]]


def cluster_graph(w):
    """G105, G106: spectral clustering on the largest connected component; each smaller component is its own cluster."""
    n_comp, comp = connected_components(w, directed=False)
    big = np.flatnonzero(comp == np.argmax(np.bincount(comp)))
    labels = np.full(w.shape[0], -1)
    labels[big], k, lam, ari = spectral(w[big][:, big])
    others = np.flatnonzero(comp != comp[big[0]])
    labels[others] = k + np.unique(comp[others], return_inverse=True)[1]
    return labels, k, lam, ari, n_comp, big


def adjusted_rand(a, b):
    """Adjusted Rand index (Hubert and Arabie 1985) between two labelings."""
    _, ia = np.unique(a, return_inverse=True)
    _, ib = np.unique(b, return_inverse=True)
    table = sparse.coo_matrix((np.ones(len(a)), (ia, ib))).toarray()
    pairs = comb(table, 2).sum()
    rows, cols, total = comb(table.sum(1), 2).sum(), comb(table.sum(0), 2).sum(), comb(len(a), 2)
    expected = rows * cols / total
    return float((pairs - expected) / ((rows + cols) / 2 - expected))


def same_class_share(labels, cls, ranked):
    """G107: mean over concepts of each class of the share of their other ranked cluster-mates in that class
    (clusters with at least two ranked concepts)."""
    lab, c = labels[ranked], cls[ranked]
    _, inv = np.unique(lab, return_inverse=True)
    size = np.bincount(inv)
    out = {}
    for name in ("under", "over"):
        hit = np.bincount(inv, weights=(c == name))
        keep = size >= 2
        num = (hit[keep] * (hit[keep] - 1) / (size[keep] - 1)).sum()
        out[name] = round(float(num / hit[keep].sum()), 4) if hit[keep].sum() else None
    return out


def permuted(labels, cls, ranked, chi_train, rng, n_perm=N_PERM, bin_size=BIN):
    """G107: the same shares with classes permuted within bins of bin_size consecutive chi_train ranks."""
    by_rank = ranked[np.argsort(-chi_train[ranked], kind="stable")]
    runs = {"under": [], "over": []}
    for _ in range(n_perm):
        shuffled = cls.copy()
        for s in range(0, len(by_rank), bin_size):
            block = by_rank[s:s + bin_size]
            shuffled[block] = cls[rng.permutation(block)]
        for name, v in same_class_share(labels, shuffled, ranked).items():
            runs[name].append(v)
    return {name: {"mean": round(float(np.mean(v)), 4), "range95": np.percentile(v, [2.5, 97.5]).round(4).tolist()} for name, v in runs.items()}


def main():
    import settings  # first: puts Exp 1 on the path and sets HF_HOME
    import config
    import pandas as pd

    import name_cache
    from s12_moved_windows import SETS
    from s19_named_select import classify

    z = np.load(settings.DATA / "full_post" / "similarity" / "neighbours.npz")
    w, no_mutual = knn_graph(z["ids"], z["cos"])
    n = w.shape[0]
    labels, k, lam, ari, n_comp, big = cluster_graph(w)
    np.savez_compressed(settings.DATA / "full_post" / "similarity" / "clusters.npz", labels=labels)
    print("clusters done: K", k, "components", n_comp, flush=True)

    table = pd.read_parquet(settings.DATA / "full_post" / "distribution.parquet")
    chi_train = table["chi_train"].to_numpy()
    cache = name_cache.load()
    name = lambda c: cache[str(c)][0]["name"].replace("|", "/").replace("\n", " ") if str(c) in cache else None  # noqa: E731
    cl_sizes = np.bincount(labels[labels >= 0])
    summary = {"concepts": n, "no_mutual_neighbour": len(no_mutual), "no_mutual_neighbour_ids": no_mutual.tolist(), "components": int(n_comp), "largest_component": int(len(big)),
               "k_spectral": k, "k_at_cap": k == K_MAX, "eigenvalues_first_101": lam.round(5).tolist(), "ari_seeds_vs_seed0": ari,
               "clusters": int(len(cl_sizes)), "cluster_size_quantiles_10_50_90_max": np.percentile(cl_sizes, [10, 50, 90, 100]).tolist(), "sets": {}}
    md = [f"# Concept clusters (design.md G105-G108)\n\nK = {k} spectral clusters on the largest component ({len(big):,} concepts), plus {len(cl_sizes) - k} small components; "
          f"{len(no_mutual)} concepts with no mutual top-11 neighbour (ids in the JSON). Adjusted Rand index of 9 more k-means seeds against seed 0: {ari}. Names are cached names, not checked against text.\n"]
    for i, s in enumerate(["V"] + SETS):
        _, cls, order = classify(chi_train, table[f"chi_{s}"].to_numpy())
        ranked = np.sort(order)
        rng = np.random.default_rng([config.SEED, 107, i])
        summary["sets"][s] = {"same_class_share": same_class_share(labels, cls, ranked), "permuted": permuted(labels, cls, ranked, chi_train, rng)}
        print(s, json.dumps(summary["sets"][s]), flush=True)
        if s == "V":
            continue
        lab = labels[ranked]
        n_ranked = np.bincount(lab, minlength=len(cl_sizes))
        for side in ("under", "over"):
            excess = np.bincount(lab, weights=(cls[ranked] == side), minlength=len(cl_sizes)) - 0.1 * n_ranked
            md.append(f"\n## {s}: 10 clusters with the largest excess of {side} concepts\n\n| cluster | size | ranked | {side} | excess | named members (up to 10) |\n|---|---|---|---|---|---|\n")
            for c in np.argsort(-excess, kind="stable")[:10]:
                members = [m for m in np.flatnonzero(labels == c) if name(m)][:10]
                md.append(f"| {c} | {cl_sizes[c]} | {n_ranked[c]} | {int(round(excess[c] + 0.1 * n_ranked[c]))} | {excess[c]:.1f} | {'<br>'.join(f'{m}: {name(m)[:140]}' for m in members) or '–'} |\n")
    (settings.RESULTS / "full_post_clusters_summary.json").write_text(json.dumps(summary, indent=1))
    (settings.RESULTS / "full_post_clusters_summary.md").write_text("".join(md))
    print(json.dumps({key: v for key, v in summary.items() if key not in ("sets", "no_mutual_neighbour_ids", "eigenvalues_first_101")}, indent=1))


if __name__ == "__main__":
    main()
