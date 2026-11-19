"""Embedding similarity, step 2: embed every window with Qwen3-Embedding-8B and average into concept vectors (design.md G117).
One GPU, $0. Resumes from its last saved state if a job is cut at the time limit.

Usage: python s38_embed_vectors.py
Reads DATA/full_post/similarity_embed/windows.parquet and pairs.npz (s37). Writes concept_vectors.npy (65,536 x 4,096,
mean-removed, unit length) and window_counts.npy there, and results/full_post_embed_vectors_summary.json (counts only).
"""
import json
import time

import numpy as np

EMBED_ID = "Qwen/Qwen3-Embedding-8B"  # G117
EMBED_REVISION = "1d8ad4ca9b3dd8059ad90a75d4983776a23d44af"
MAX_LEN = 128  # G117
BATCH = 256
SAVE_EVERY = 100_000  # G117: windows between saved states


def window_concepts(batch, starts, by_window, concept):
    """For a batch of window ids: (row in the batch, concept) for every pair that uses one of these windows.
    by_window orders the pairs by window; starts[w]:starts[w + 1] are window w's pairs in that order."""
    lens = starts[batch + 1] - starts[batch]
    rows = np.repeat(np.arange(len(batch)), lens)
    offset = np.arange(lens.sum()) - np.repeat(np.cumsum(lens) - lens, lens)
    return rows, concept[by_window[np.repeat(starts[batch], lens) + offset]]


def finish(sums, counts):
    """G117: mean of each concept's window embeddings, minus the mean over concepts, scaled to unit length."""
    v = sums / counts[:, None]
    v = v - v.mean(0)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def main():
    import settings  # first: puts Exp 1 on the path and sets HF_HOME
    import pandas as pd
    import torch
    from transformers import AutoModel, AutoTokenizer

    from s12_moved_windows import D_SAE

    t0 = time.time()
    d = settings.DATA / "full_post" / "similarity_embed"
    text = pd.read_parquet(d / "windows.parquet", columns=["text"])["text"].tolist()
    z = np.load(d / "pairs.npz")
    concept, window = z["concept"], z["window"]
    by_window = np.argsort(window, kind="stable")
    starts = np.searchsorted(window[by_window], np.arange(len(text) + 1))
    counts = np.bincount(concept, minlength=D_SAE).astype(np.float64)
    if (counts == 0).any():
        raise SystemExit(f"G116: {int((counts == 0).sum())} concepts have no window")

    tok = AutoTokenizer.from_pretrained(EMBED_ID, revision=EMBED_REVISION, padding_side="left")
    model = AutoModel.from_pretrained(EMBED_ID, revision=EMBED_REVISION, torch_dtype=torch.bfloat16).cuda().eval()
    n_tok = np.array([len(x) for x in tok(text, add_special_tokens=True)["input_ids"]])
    order = np.argsort(n_tok, kind="stable")  # similar lengths per batch, less padding
    state = d / "embed_state.npz"
    if state.exists():
        s = np.load(state)
        done, sums = int(s["done"]), torch.from_numpy(s["sums"]).cuda()
        print("resuming at", done, flush=True)
    else:
        done, sums = 0, torch.zeros(D_SAE, model.config.hidden_size, dtype=torch.float32, device="cuda")
    since = 0
    with torch.inference_mode():
        for b in range(done, len(order), BATCH):
            batch = order[b:b + BATCH]
            enc = tok([text[i] for i in batch], padding=True, truncation=True, max_length=MAX_LEN, return_tensors="pt").to("cuda")
            if not enc["attention_mask"][:, -1].all():
                raise SystemExit("G117: left padding expected, so the last position is each window's last token")
            emb = torch.nn.functional.normalize(model(**enc).last_hidden_state[:, -1].float(), dim=1)  # last-token pooling (card)
            rows, cs = window_concepts(batch, starts, by_window, concept)
            sums.index_add_(0, torch.from_numpy(cs).cuda(), emb[torch.from_numpy(rows).cuda()])
            since += len(batch)
            if since >= SAVE_EVERY or b + BATCH >= len(order):
                np.savez(state, done=b + len(batch), sums=sums.cpu().numpy())
                since = 0
                print(f"{b + len(batch):,} of {len(order):,} windows, {round(time.time() - t0)} s", flush=True)
    np.save(d / "concept_vectors.npy", finish(sums.cpu().numpy().astype(np.float64), counts).astype(np.float32))
    np.save(d / "window_counts.npy", counts.astype(np.int64))
    state.unlink()  # finished: a later run starts fresh
    summary = {"model": EMBED_ID, "revision": EMBED_REVISION, "windows": len(text), "pairs": int(len(concept)), "tokens": int(n_tok.sum()),
               "tokens_10_50_90_max": np.percentile(n_tok, [10, 50, 90, 100]).tolist(), "truncated": int((n_tok > MAX_LEN).sum()),
               "gpu": torch.cuda.get_device_name(), "seconds_this_job": round(time.time() - t0)}
    (settings.RESULTS / "full_post_embed_vectors_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
