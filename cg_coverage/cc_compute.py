"""cc_compute.py -- per-item SAE concept activations for Pythia-70m (TopK SAE, layer 4).

Saves, per source, a dict with
  sum_nobos : (N, d_sae) float32  sum over tokens 1..T-1 of SAE activations (BOS excluded)
  bos_acts  : (N, d_sae) float32  SAE activations at position 0 (BOS)
  lengths   : (N,) int64          T = total tokens INCLUDING BOS
  snippets  : list[str]           first 400 chars of each text
so that BOTH variants of Eq. 1 can be rebuilt later:
  with BOS   : (sum_nobos + bos_acts) / T
  without BOS: sum_nobos / (T - 1)

Usage:
  python3 cc_compute.py --source benchmarks
  python3 cc_compute.py --source pile_instream     # first 5000 docs of the stream the SAE trained on
  python3 cc_compute.py --source pile_heldout      # docs after --skip (never seen by the SAE)
"""
import argparse
import random
import time

import torch

HOOK = "blocks.4.hook_resid_post"
SAE_PATH = "pythia70m_layer4_topk32_sae"
MODEL = "pythia-70m-deduped"


def get_benchmarks(seed=0, n_mmlu=2000):
    from datasets import load_dataset

    out = {}

    ds = load_dataset("openai/gsm8k", "main", split="test")
    out["gsm8k"] = [r["question"] for r in ds]

    ds = load_dataset("cais/mmlu", "all", split="test")
    idx = list(range(len(ds)))
    random.Random(seed).shuffle(idx)
    texts = []
    for i in idx[:n_mmlu]:
        r = ds[i]
        opts = "\n".join(f"{l}. {c}" for l, c in zip("ABCD", r["choices"]))
        texts.append(f"{r['question']}\n{opts}")
    out["mmlu"] = texts

    ds = load_dataset("allenai/ai2_arc", "ARC-Challenge", split="test")
    texts = []
    for r in ds:
        opts = "\n".join(f"{l}. {c}" for l, c in zip(r["choices"]["label"], r["choices"]["text"]))
        texts.append(f"{r['question']}\n{opts}")
    out["arc_challenge"] = texts

    ds = load_dataset("openai/openai_humaneval", split="test")
    out["humaneval"] = [r["prompt"] for r in ds]
    return out


def pile_texts(n_docs, skip, max_chars):
    from datasets import load_dataset

    ds = load_dataset("EleutherAI/the_pile_deduplicated", split="train", streaming=True)
    if skip:
        ds = ds.skip(skip)
    for r in ds:
        yield r["text"][:max_chars]


@torch.no_grad()
def run(model, sae, texts, min_tokens, max_tokens, tag):
    sums, boss, lens, snips = [], [], [], []
    t0 = time.time()
    for k, text in enumerate(texts):
        toks = model.to_tokens(text)[:, :max_tokens]
        T = toks.shape[1]
        if T < min_tokens:
            continue
        _, cache = model.run_with_cache(toks, names_filter=HOOK, stop_at_layer=5)
        acts = sae.encode(cache[HOOK]).float()  # (1, T, d_sae)
        boss.append(acts[0, 0].cpu())
        sums.append(acts[0, 1:].sum(0).cpu())
        lens.append(T)
        snips.append(text[:400])
        if len(lens) % 500 == 0:
            print(f"[{tag}] kept {len(lens)} items ({time.time() - t0:.0f}s)", flush=True)
    return {
        "sum_nobos": torch.stack(sums),
        "bos_acts": torch.stack(boss),
        "lengths": torch.tensor(lens, dtype=torch.long),
        "snippets": snips,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, choices=["benchmarks", "pile_instream", "pile_heldout"])
    ap.add_argument("--n_docs", type=int, default=5000)
    ap.add_argument("--skip", type=int, default=150000)
    ap.add_argument("--max_tokens", type=int, default=2048)
    ap.add_argument("--max_chars", type=int, default=4000)
    ap.add_argument("--min_tokens_pile", type=int, default=30)
    ap.add_argument("--min_tokens_bench", type=int, default=5)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    from sae_lens import SAE
    from transformer_lens import HookedTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = HookedTransformer.from_pretrained(MODEL, device=device, dtype=torch.bfloat16)
    model.eval()
    sae = SAE.load_from_disk(SAE_PATH, device=device)
    sae.eval()
    print("device", device, "d_sae", sae.cfg.d_sae, flush=True)

    if args.source == "benchmarks":
        for name, texts in get_benchmarks().items():
            res = run(model, sae, texts, args.min_tokens_bench, args.max_tokens, name)
            print(name, "items kept:", len(res["lengths"]), "of", len(texts),
                  "mean tokens:", res["lengths"].float().mean().item(), flush=True)
            torch.save(res, f"cc_{name}.pt")
    else:
        skip = 0 if args.source == "pile_instream" else args.skip
        gen = pile_texts(args.n_docs, skip, args.max_chars)
        # take docs until n_docs have been KEPT (the generator is lazy)
        def limited():
            kept = 0
            for t in gen:
                yield t
                kept += 1
                if kept >= args.n_docs:
                    return
        res = run(model, sae, limited(), args.min_tokens_pile, args.max_tokens, args.source)
        print(args.source, "items kept:", len(res["lengths"]), flush=True)
        torch.save(res, f"cc_{args.source}{args.tag}.pt")
    print("done")


if __name__ == "__main__":
    main()
