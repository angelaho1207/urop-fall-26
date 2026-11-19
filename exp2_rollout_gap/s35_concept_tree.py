"""Concept tree: repeated splitting (pieces, else spectral K = 2) of the top-11 decoder-neighbour graph, and where under- and over-represented
concepts concentrate (design.md G110-G112). CPU, $0.

Usage: python s35_concept_tree.py
Reads DATA/full_post/similarity/neighbours.npz (s32), DATA/full_post/distribution.parquet and notes/name_cache.json. Writes
DATA/full_post/similarity/tree.npz and results/full_post_tree_summary.{json,md} (ids, names, numbers).
"""
import json

import numpy as np
from scipy import sparse
from scipy.cluster.vq import kmeans2
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import eigsh

from s33_concept_clusters import knn_graph

DEPTH, MIN_SPLIT = 8, 22  # G110
N_PERM, BIN, MIN_RANKED = 100, 1000, 10  # G111


def split(w):
    """G110: children of one group, as a label per member: its connected pieces if there are several, else spectral K = 2.
    Returns (labels, how), or (None, None) if the spectral split leaves one side empty."""
    n_comp, comp = connected_components(w, directed=False)
    if n_comp > 1:
        return comp, "pieces"
    w = w.astype(np.float64)
    inv = sparse.diags(1 / np.sqrt(np.asarray(w.sum(1)).ravel()))
    _, vec = eigsh(inv @ w @ inv, k=2, which="LA")
    u = vec / np.linalg.norm(vec, axis=1, keepdims=True)
    side = kmeans2(u, 2, minit="++", seed=0)[1]
    return (side, "spectral") if 0 < side.sum() < len(side) else (None, None)


def build_tree(w, depth=DEPTH, min_split=MIN_SPLIT):
    """G110: levels[d][i] = id of concept i's group at depth d (root 0); -1 once the concept's group stopped splitting at
    a shallower depth. groups[id] = depth, size, parent and how it split."""
    n = w.shape[0]
    levels = np.full((depth + 1, n), -1)
    levels[0] = 0
    groups = {0: {"depth": 0, "size": n, "parent": None, "split": None}}
    for d in range(depth):
        for g in np.unique(levels[d][levels[d] >= 0]):
            members = np.flatnonzero(levels[d] == g)
            labels, how = split(w[members][:, members]) if len(members) >= min_split else (None, None)
            if labels is None:
                continue
            groups[int(g)]["split"] = how
            for part in np.unique(labels):
                child = len(groups)
                levels[d + 1][members[labels == part]] = child
                groups[child] = {"depth": d + 1, "size": int((labels == part).sum()), "parent": int(g), "split": None}
    return levels, groups


def shares(levels, flag, ranked):
    """G111: per depth, {group: (ranked count, flagged count)} over ranked concepts."""
    out = []
    for lab in levels:
        lab_r = lab[ranked]
        keep = lab_r >= 0
        ids, inv = np.unique(lab_r[keep], return_inverse=True)
        out.append((ids, np.bincount(inv), np.bincount(inv, weights=flag[ranked][keep])))
    return out


def enrichment(levels, cls, ranked, chi_train, rng, n_perm=N_PERM, bin_size=BIN, min_ranked=MIN_RANKED):
    """G111: per group and class, observed share, the 97.5th percentile of 100 within-frequency-bin permutations, and
    whether it exceeds; per depth, groups tested and groups exceeding."""
    by_rank = ranked[np.argsort(-chi_train[ranked], kind="stable")]
    perms = []
    for _ in range(n_perm):
        shuffled = cls.copy()
        for s in range(0, len(by_rank), bin_size):
            block = by_rank[s:s + bin_size]
            shuffled[block] = cls[rng.permutation(block)]
        perms.append(shuffled)
    groups, per_depth = {}, []
    for side in ("under", "over"):
        obs = shares(levels, cls == side, ranked)
        null = [shares(levels, p == side, ranked) for p in perms]
        for d, (ids, n_r, hit) in enumerate(obs):
            p975 = np.percentile(np.stack([nl[d][2] for nl in null]) / n_r, 97.5, axis=0)
            tested = n_r >= min_ranked
            exceeds = tested & (hit / n_r > p975)
            for j, g in enumerate(ids):
                rec = groups.setdefault(int(g), {"depth": d, "ranked": int(n_r[j])})
                rec[side] = {"count": int(hit[j]), "share": round(float(hit[j] / n_r[j]), 4), "null_p975": round(float(p975[j]), 4), "exceeds": bool(exceeds[j])}
            if side == "under":
                per_depth.append({"depth": d, "tested": int(tested.sum())})
            per_depth[d][f"{side}_exceeding"] = int(exceeds.sum())
    return groups, per_depth


def path(g, groups):
    """Group ids from the root down to group g."""
    out = [g]
    while groups[out[-1]]["parent"] is not None:
        out.append(groups[out[-1]]["parent"])
    return out[::-1]


def main():
    import settings  # first: puts Exp 1 on the path and sets HF_HOME
    import config
    import pandas as pd

    import name_cache
    from s12_moved_windows import SETS
    from s19_named_select import classify

    z = np.load(settings.DATA / "full_post" / "similarity" / "neighbours.npz")
    w, _ = knn_graph(z["ids"], z["cos"])
    levels, groups = build_tree(w)
    np.savez_compressed(settings.DATA / "full_post" / "similarity" / "tree.npz", levels=levels)
    print("tree done:", {d: int(len(np.unique(levels[d][levels[d] >= 0]))) for d in range(DEPTH + 1)}, flush=True)

    table = pd.read_parquet(settings.DATA / "full_post" / "distribution.parquet")
    chi_train = table["chi_train"].to_numpy()
    cache = name_cache.load()
    name = lambda c: cache[str(c)][0]["name"].replace("|", "/").replace("\n", " ")[:140] if str(c) in cache else None  # noqa: E731
    deepest = np.array([col[col >= 0][-1] for col in levels.T])  # each concept's leaf
    summary = {"depth": DEPTH, "min_split": MIN_SPLIT, "groups": {str(g): v for g, v in groups.items()},
               "groups_per_depth": {d: int(len(np.unique(levels[d][levels[d] >= 0]))) for d in range(DEPTH + 1)}, "sets": {}}
    md = ["# Concept tree (design.md G110-G112)\n\nRepeated splitting (separate pieces, else spectral K = 2) of the top-11 decoder-neighbour graph. Groups are numbered from the root (0); paths list group ids from the root. "
          "A group exceeds when its share is above the 97.5th percentile of 100 frequency-matched permutations (about 2.5% expected by chance). Names are cached names, not checked against text.\n",
          "\n## Groups per depth\n\n| depth | " + " | ".join(str(d) for d in range(DEPTH + 1)) + " |\n" + "|---" * (DEPTH + 1) + "|---|\n| groups | " + " | ".join(str(v) for v in summary["groups_per_depth"].values()) + " |\n"]
    for i, s in enumerate(["V"] + SETS):
        _, cls, order = classify(chi_train, table[f"chi_{s}"].to_numpy())
        enr, per_depth = enrichment(levels, cls, np.sort(order), chi_train, np.random.default_rng([config.SEED, 111, i]))
        summary["sets"][s] = {"per_depth": per_depth, "groups": {str(g): v for g, v in enr.items()}}
        print(s, json.dumps(per_depth), flush=True)
        md.append(f"\n## {s}: groups exceeding the permutation null, per depth\n\n| depth | tested | under exceeding | over exceeding |\n|---|---|---|---|\n")
        md += [f"| {x['depth']} | {x['tested']} | {x['under_exceeding']} | {x['over_exceeding']} |\n" for x in per_depth]
        if s == "V":
            continue
        for side in ("under", "over"):
            hits = [(g, v) for g, v in enr.items() if v[side]["exceeds"]]
            hits.sort(key=lambda gv: -(gv[1][side]["count"] - 0.1 * gv[1]["ranked"]))
            md.append(f"\n### {s}: 10 enriched groups with the largest excess of {side} concepts\n\n| group | depth | path | size | ranked | {side} | share | null 97.5% | named members (up to 10) |\n|---|---|---|---|---|---|---|---|---|\n")
            for g, v in hits[:10]:
                members = [m for m in np.flatnonzero(levels[v["depth"]] == g) if name(m)][:10]
                md.append(f"| {g} | {v['depth']} | {' → '.join(map(str, path(g, groups)))} | {groups[g]['size']} | {v['ranked']} | {v[side]['count']} | {v[side]['share']} | {v[side]['null_p975']} | "
                          + ("<br>".join(f"{m}: {name(m)}" for m in members) or "–") + " |\n")
    summary["leaf_sizes_10_50_90_max"] = np.percentile(np.bincount(deepest)[np.unique(deepest)], [10, 50, 90, 100]).tolist()
    (settings.RESULTS / "full_post_tree_summary.json").write_text(json.dumps(summary))
    (settings.RESULTS / "full_post_tree_summary.md").write_text("".join(md))
    print(json.dumps({k: summary[k] for k in ("groups_per_depth", "leaf_sizes_10_50_90_max")}, indent=1))


if __name__ == "__main__":
    main()
