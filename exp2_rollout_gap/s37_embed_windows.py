"""Embedding similarity, step 1: each concept's top-activating Dolma train windows (design.md G114-G116). CPU, $0.

Usage: python s37_embed_windows.py
Reads Exp 1's train acts and docs and DATA/full_post/distribution.parquet. Writes DATA/full_post/similarity_embed/windows.parquet
(window text: pool only, G20) and pairs.npz (concept, window, rank, max), and results/full_post_embed_windows_summary.json
(counts only).
"""
import json
import time

import numpy as np

N_TOP = 40  # G116: Exp 1's naming docs (E2)


def top_per_concept(c, score, doc, n_top=N_TOP):
    """G116: positions of each concept's n_top entries with the highest score (ties to the lower doc), ordered by concept
    then rank, and their ranks (0 = highest)."""
    order = np.lexsort((doc, -score, c))
    cs = c[order]
    rank = np.arange(len(order)) - np.searchsorted(cs, cs, side="left")  # position within the concept's run
    keep = rank < n_top
    return order[keep], rank[keep]


def top_entries(parts, n_top=N_TOP):
    """G116: stream the acts parts, keeping each concept's n_top docs by per-doc max. Returns doc keys (part, local index,
    doc id), doc lengths, and per kept entry: concept, max, side doc index, argmax token, rank."""
    keys, doc_len, cur = [], [], None
    for k, (path, mask_of) in enumerate(parts):
        with np.load(path, allow_pickle=True) as z:
            ids = z["doc_id"]
            keep = mask_of(ids)
            local = np.flatnonzero(keep)
            glob = np.full(len(ids), -1)
            glob[local] = np.arange(len(keys), len(keys) + len(local))
            keys += [(k, int(j), ids[j]) for j in local]
            doc_len += [int(n) for n in z["doc_tokens"][local]]
            doc = np.repeat(np.arange(len(ids)), z["doc_active"])
            m = keep[doc]
            new = (z["doc_latent_ids"][m].astype(np.int64), z["doc_max"][m].astype(np.float32), glob[doc[m]], z["doc_argmax"][m].astype(np.int64))
        both = new if cur is None else tuple(np.concatenate([a, b]) for a, b in zip(cur, new))
        sel, _ = top_per_concept(both[0], both[1], both[2], n_top)
        cur = tuple(a[sel] for a in both)
    sel, rank = top_per_concept(cur[0], cur[1], cur[2], n_top)
    return keys, np.array(doc_len), (*(a[sel] for a in cur), rank)


def unique_windows(doc, start):
    """G116: one id per distinct (doc, start); returns the distinct (doc, start) pairs and each entry's window id."""
    pairs, window = np.unique(np.stack([doc, start], 1), axis=0, return_inverse=True)
    return pairs, window.ravel()


def main():
    import settings  # first: puts Exp 1 on the path and sets HF_HOME
    import config
    import pandas as pd
    from transformers import AutoTokenizer

    from s06_examples import WINDOW, window_start  # Exp 1 E1
    from s12_moved_windows import D_SAE, side_parts, token_ids

    t0 = time.time()
    out = settings.DATA / "full_post" / "similarity_embed"
    out.mkdir(parents=True, exist_ok=True)
    keys, doc_len, (c, mx, doc, arg, rank) = top_entries(side_parts("train"))
    print("top entries", len(c), "docs", len(keys), round(time.time() - t0), flush=True)

    n_win = np.bincount(c, minlength=D_SAE)
    fire = pd.read_parquet(settings.DATA / "full_post" / "distribution.parquet")["n_fire_train"].to_numpy()
    mismatch = np.flatnonzero(n_win != np.minimum(fire, N_TOP))  # G116 check
    if len(mismatch):
        raise SystemExit(f"G116: window counts differ from min(n_fire_train, {N_TOP}) for {len(mismatch)} concepts, e.g. {mismatch[:10].tolist()}")

    start = np.array([window_start(int(a), int(doc_len[d])) for a, d in zip(arg, doc)])
    distinct, window = unique_windows(doc, start)
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    ids_of = token_ids("train", keys, doc_len, np.unique(distinct[:, 0]), tokenizer)
    text = tokenizer.batch_decode([ids_of[d][s:s + WINDOW] for d, s in distinct])
    print("windows decoded", len(text), round(time.time() - t0), flush=True)

    pd.DataFrame({"window": np.arange(len(distinct)), "doc": distinct[:, 0], "doc_id": [keys[d][2] for d in distinct[:, 0]], "start": distinct[:, 1],
                  "text": text}).to_parquet(out / "windows.parquet")
    np.savez_compressed(out / "pairs.npz", concept=c, window=window, rank=rank, max=mx, doc=doc)
    summary = {"docs": len(keys), "concepts": int((n_win > 0).sum()), "concepts_without_window": int((n_win == 0).sum()), "pairs": int(len(c)), "distinct_windows": int(len(distinct)),
               "windows_per_concept_10_50_90": np.percentile(n_win, [10, 50, 90]).tolist(), "concepts_under_40": int((n_win < N_TOP).sum()), "concepts_with_1": int((n_win == 1).sum()),
               "concepts_under_5": int((n_win < 5).sum()), "seconds": round(time.time() - t0)}
    (settings.RESULTS / "full_post_embed_windows_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
