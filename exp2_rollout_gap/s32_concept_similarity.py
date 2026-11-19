"""Concept similarity: decoder-cosine neighbours, and whether concepts move with their neighbours (design.md G101-G104). CPU, $0.

Usage: python s32_concept_similarity.py
Reads the SAE's W_dec (pinned revision), DATA/full_post/distribution.parquet and notes/name_cache.json. Writes
DATA/full_post/similarity/neighbours.npz and results/full_post_similarity_summary.{json,md} (ids, names, numbers).
"""
import json

import numpy as np
from scipy.stats import spearmanr

K = 11  # G101: ln 65,536 rounded (von Luxburg 2007)
WINDOW = 500  # G102: G47's frequency match, in chi_train ranks
N_BOOT = 1000  # G102: as G11


def neighbours(w, k=K, chunk=2048):
    """G101: each row's k nearest other rows by cosine, most similar first."""
    w = w / np.linalg.norm(w, axis=1, keepdims=True)
    ids, cos = np.empty((len(w), k), dtype=np.int64), np.empty((len(w), k), dtype=np.float32)
    for s in range(0, len(w), chunk):
        sims = w[s:s + chunk] @ w.T
        sims[np.arange(len(sims)), np.arange(s, s + len(sims))] = -np.inf  # not its own neighbour
        top = np.argpartition(-sims, k, axis=1)[:, :k]
        order = np.argsort(-np.take_along_axis(sims, top, axis=1), axis=1)
        ids[s:s + chunk] = np.take_along_axis(top, order, axis=1)
        cos[s:s + chunk] = np.take_along_axis(sims, ids[s:s + chunk], axis=1)
    return ids, cos


def rank_u(order, n):
    """G102: position in G70's rank order (lowest r first), scaled to 0-1; nan for unranked concepts."""
    u = np.full(n, np.nan)
    u[order] = np.arange(len(order)) / (len(order) - 1)
    return u


def matched_random(chi_train, ranked, k, rng, window=WINDOW):
    """G102: per ranked concept, k random other ranked concepts within +-window chi_train ranks; -1 for unranked concepts."""
    by_rank = ranked[np.argsort(-chi_train[ranked], kind="stable")]
    n = len(by_rank)
    pos = np.arange(n)[:, None]
    low, high = np.maximum(pos - window, 0), np.minimum(pos + window, n - 1)
    draw = low + rng.integers(0, high - low, size=(n, k))  # one of the high - low other positions in the window
    draw = draw + (draw >= pos)  # skip the concept itself
    out = np.full((len(chi_train), k), -1)
    out[by_rank] = by_rank[draw]
    return out


def comove(u, nbr, rng, n_boot=N_BOOT):
    """G102: Spearman rho between a concept's u and the mean u of its ranked neighbours (nbr = -1 leaves the mean),
    with a bootstrap interval over concepts."""
    vals = np.where(nbr >= 0, u[np.maximum(nbr, 0)], np.nan)
    count = (~np.isnan(vals)).sum(1)
    m = np.where(count > 0, np.nansum(vals, 1) / np.maximum(count, 1), np.nan)
    keep = ~np.isnan(u) & ~np.isnan(m)
    x, y = u[keep], m[keep]
    boots = [spearmanr(x[i], y[i]).statistic for i in (rng.integers(0, len(x), len(x)) for _ in range(n_boot))]
    return {"rho": round(float(spearmanr(x, y).statistic), 4), "ci95": np.percentile(boots, [2.5, 97.5]).round(4).tolist(), "concepts": int(keep.sum())}


def substitution(cls, nn1, rng, n_boot=N_BOOT):
    """G103: share of under concepts whose nearest ranked neighbour is over, and the reverse, with bootstrap intervals."""
    out = {}
    for a, b in (("under", "over"), ("over", "under")):
        hit = (cls[nn1[(cls == a) & (nn1 >= 0)]] == b).astype(float)
        boots = [hit[rng.integers(0, len(hit), len(hit))].mean() for _ in range(n_boot)]
        out[f"{a}_to_{b}"] = {"share": round(float(hit.mean()), 4), "ci95": np.percentile(boots, [2.5, 97.5]).round(4).tolist(), "concepts": int(len(hit))}
    return out


def nearest_ranked(nbr):
    """G103: first ranked neighbour in cosine order, and its column; -1 where none of the k is ranked."""
    first = np.argmax(nbr >= 0, axis=1)
    return np.where((nbr >= 0).any(1), nbr[np.arange(len(nbr)), first], -1), first


def main():
    import settings  # first: puts Exp 1 on the path and sets HF_HOME
    import config
    import pandas as pd
    from huggingface_hub import snapshot_download
    from safetensors import safe_open

    import name_cache
    from s12_moved_windows import SETS
    from s19_named_select import classify

    root = snapshot_download(config.SAE_REPO, revision=config.SAE_REVISION, allow_patterns=[f"{config.SAE_ID}/*"])
    with safe_open(f"{root}/{config.SAE_ID}/sae_weights.safetensors", "np") as f:
        w = f.get_tensor("W_dec").astype(np.float32)  # (65,536 concepts, 4,096), as Exp 1 N15
    ids, cos = neighbours(w)
    out_dir = settings.DATA / "full_post" / "similarity"
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_dir / "neighbours.npz", ids=ids, cos=cos)
    print("neighbours done", flush=True)

    table = pd.read_parquet(settings.DATA / "full_post" / "distribution.parquet")
    chi_train = table["chi_train"].to_numpy()
    n = len(chi_train)
    cache = name_cache.load()
    name = lambda c: cache[str(c)][0]["name"].replace("|", "/").replace("\n", " ") if str(c) in cache else None  # noqa: E731
    summary = {"k": K, "window": WINDOW, "bootstrap": N_BOOT, "concepts": n, "sets": {},
               "cosine_quantiles_10_50_90": {f"neighbour_{j + 1}": np.quantile(cos[:, j], [0.1, 0.5, 0.9]).round(4).tolist() for j in (0, K - 1)}}
    named = [(c, int(ids[c, 0])) for c in range(n) if name(c) and name(ids[c, 0])]
    summary["named_neighbour_pairs"] = len(named)
    head = "| concept | neighbour | cosine | concept name | neighbour name |\n|---|---|---|---|---|\n"
    md = ["# Concept similarity (design.md G101-G104)\n\nDecoder-cosine neighbours of all 65,536 concepts. Names are cached names, not checked against text.\n",
          f"\n## Nearest-neighbour pairs where both concepts are named ({len(named)})\n\n{head}"]
    md += [f"| {a} | {b} | {cos[a, 0]:.3f} | {name(a)} | {name(b)} |\n" for a, b in named]
    for i, s in enumerate(["V"] + SETS):
        _, cls, order = classify(chi_train, table[f"chi_{s}"].to_numpy())  # G70's ranking, V as a set for the baseline
        is_ranked = np.zeros(n, dtype=bool)
        is_ranked[order] = True
        rng = np.random.default_rng([config.SEED, 102, i])
        u = rank_u(order, n)
        nbr = np.where(is_ranked[ids] & is_ranked[:, None], ids, -1)  # unranked concepts and neighbours leave out
        rand = matched_random(chi_train, np.sort(order), K, rng)
        nn1, first = nearest_ranked(nbr)
        summary["sets"][s] = {"comove_neighbours": comove(u, nbr, rng), "comove_random": comove(u, rand, rng),
                              "substitution_neighbour": substitution(cls, nn1, rng), "substitution_random": substitution(cls, rand[:, 0], rng)}
        print(s, json.dumps(summary["sets"][s]), flush=True)
        if s != "V":
            pairs = [(c, nn1[c], cos[c, first[c]]) for c in np.flatnonzero((cls == "under") & (nn1 >= 0)) if cls[nn1[c]] == "over" and name(c) and name(nn1[c])]
            md.append(f"\n## {s}: under concepts whose nearest ranked neighbour is over, both named ({len(pairs)})\n\n{head}")
            md += [f"| {a} | {b} | {x:.3f} | {name(a)} | {name(b)} |\n" for a, b, x in pairs]
    (settings.RESULTS / "full_post_similarity_summary.json").write_text(json.dumps(summary, indent=1))
    (settings.RESULTS / "full_post_similarity_summary.md").write_text("".join(md))
    print(json.dumps({k: v for k, v in summary.items() if k != "sets"}, indent=1))


if __name__ == "__main__":
    main()
