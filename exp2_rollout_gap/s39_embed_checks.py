"""Embedding similarity, step 4: top-doc overlap of neighbours, and the blind name-check items (design.md G119, G120). CPU, $0.

Usage: python s39_embed_checks.py
Reads DATA/full_post/similarity_embed/{pairs.npz, window_counts.npy, neighbours.npz}, DATA/full_post/similarity/neighbours.npz,
DATA/full_post/distribution.parquet and notes/name_cache.json. Writes results/full_post_embed_checks.json (numbers),
results/full_post_embed_name_check_blind.json (shuffled name pairs, no key) and the key to the pool.
"""
import json

import numpy as np
from scipy import sparse

N_CHECK = 100  # G120: as the G101 check


def doc_overlap(top_docs, nbr):
    """G119: per (concept, neighbour column): shared top docs and Jaccard index. top_docs: concepts x docs, 0/1 sparse."""
    size = np.asarray(top_docs.sum(1)).ravel()
    shared = np.stack([np.asarray(top_docs.multiply(top_docs[nbr[:, j]]).sum(1)).ravel() for j in range(nbr.shape[1])], 1)
    return shared, shared / (size[:, None] + size[nbr] - shared)


def overlap_summary(shared, jac):
    return {"pairs": int(shared.size), "share_with_a_shared_doc": round(float((shared > 0).mean()), 4), "mean_jaccard": round(float(jac.mean()), 4)}


def blind_items(named, nn1, rng, n=N_CHECK):
    """G120: n seeded concepts whose nearest neighbour is named, and n random pairs of named concepts, shuffled.
    Returns items [(a, b)] and the key (\"neighbour\" or \"random\" per item)."""
    is_named = np.zeros(len(nn1), dtype=bool)
    is_named[named] = True
    pool = np.flatnonzero(is_named & is_named[nn1])
    nb = [(int(a), int(nn1[a])) for a in rng.choice(pool, n, replace=False)]
    rd = [tuple(int(x) for x in rng.choice(named, 2, replace=False)) for _ in range(n)]
    order = rng.permutation(2 * n)
    items = nb + rd
    return [items[i] for i in order], ["neighbour" if i < n else "random" for i in order]


def main():
    import settings  # first: puts Exp 1 on the path and sets HF_HOME
    import config
    import pandas as pd

    import name_cache
    from s32_concept_similarity import matched_random

    d = settings.DATA / "full_post"
    z = np.load(d / "similarity_embed" / "pairs.npz")
    n = 65_536
    top_docs = sparse.csr_matrix((np.ones(len(z["concept"])), (z["concept"], z["doc"])), shape=(n, int(z["doc"].max()) + 1))
    emb = np.load(d / "similarity_embed" / "neighbours.npz")
    dec = np.load(d / "similarity" / "neighbours.npz")
    chi_train = pd.read_parquet(d / "distribution.parquet")["chi_train"].to_numpy()
    rand = matched_random(chi_train, np.arange(n), emb["ids"].shape[1], np.random.default_rng([config.SEED, 119]))
    out = {"windows_per_concept_10_50_90": np.percentile(np.load(d / "similarity_embed" / "window_counts.npy"), [10, 50, 90]).tolist(),
           "embed_cosine_10_50_90": {f"neighbour_{j + 1}": np.quantile(emb["cos"][:, j], [0.1, 0.5, 0.9]).round(4).tolist() for j in (0, 10)}}
    for label, nbr in (("embedding_neighbours", emb["ids"]), ("decoder_neighbours", dec["ids"]), ("random_frequency_matched", rand)):
        out[label] = overlap_summary(*doc_overlap(top_docs, nbr))
        print(label, out[label], flush=True)
    same = (emb["ids"][:, :, None] == dec["ids"][:, None, :]).any(2)
    out["embedding_neighbours_also_decoder_neighbours"] = round(float(same.mean()), 4)

    cache = name_cache.load()
    named = np.array(sorted(int(c) for c in cache))
    name = lambda c: cache[str(c)][0]["name"]  # noqa: E731  # as the G101 check
    items, key = blind_items(named, emb["ids"][:, 0], np.random.default_rng([config.SEED, 120]))
    (settings.RESULTS / "full_post_embed_name_check_blind.json").write_text(json.dumps(
        [{"item": i, "name_a": name(a), "name_b": name(b)} for i, (a, b) in enumerate(items)], ensure_ascii=False, indent=0))  # no ids: blind
    (d / "similarity_embed" / "name_check_key.json").write_text(json.dumps([{"item": i, "a": a, "b": b, "kind": k} for i, ((a, b), k) in enumerate(zip(items, key))]))
    (settings.RESULTS / "full_post_embed_checks.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
