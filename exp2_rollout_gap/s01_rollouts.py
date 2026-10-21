"""Unprompted rollouts with pure sampling (design.md G1-G7, X1). GPU.

Usage: python s01_rollouts.py --run pilot --generator stage1 --n 200 --batch 48
Writes DATA/<run>/<generator>/rollouts/part_<k>.parquet (rollout_id, ids, ended_by_eos) and
results/<run>_<generator>_rollouts_summary.json. Parts already on disk are skipped, so a rerun resumes (X1).
"""
import argparse
import json
import os
import time

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np
import pandas as pd
import torch
from huggingface_hub import list_repo_refs
from transformers import AutoModelForCausalLM

torch.set_grad_enabled(False)
DEVICE = "cuda"


def resolve(revision):
    """G4: turn a branch name into the commit hash it points to today, so the run is pinned and logged."""
    for branch in list_repo_refs(config.MODEL_ID).branches:
        if branch.name == revision:
            return branch.target_commit
    return revision  # already a commit hash


def part_generator(run, k):
    """G6: one seeded RNG per part, so any part can be regenerated alone."""
    seed = int(np.random.SeedSequence([settings.SEED_ROOT[run], k]).generate_state(1)[0])
    return torch.Generator(device=DEVICE).manual_seed(seed)


def sample_batch(model, size, gen):
    """G1-G3, G7: start every rollout from <|endoftext|>, then draw each next token from softmax(logits) in float32.
    No temperature change, top-k, top-p or penalty. A rollout ends at its first <|endoftext|> or after MAX_NEW tokens."""
    step_ids = torch.full((size, 1), settings.EOS_ID, device=DEVICE)
    out = model(step_ids, use_cache=True)
    tokens = torch.full((size, settings.MAX_NEW), settings.EOS_ID, device=DEVICE)
    done = torch.zeros(size, dtype=torch.bool, device=DEVICE)
    for t in range(settings.MAX_NEW):
        probs = torch.softmax(out.logits[:, -1].float(), dim=-1)
        nxt = torch.multinomial(probs, 1, generator=gen)[:, 0]
        nxt = torch.where(done, settings.EOS_ID, nxt)  # finished rollouts keep stepping in the batch; cut below
        tokens[:, t] = nxt
        done |= nxt == settings.EOS_ID
        if done.all():
            break
        out = model(nxt[:, None], past_key_values=out.past_key_values, use_cache=True)
    rows = []
    for seq in tokens.cpu().tolist():
        n = seq.index(settings.EOS_ID) if settings.EOS_ID in seq else len(seq)
        rows.append((seq[:n], n < len(seq)))  # G3: drop the closing <|endoftext|>
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, choices=["pilot", "full"])
    parser.add_argument("--generator", required=True, choices=list(settings.GENERATORS))
    parser.add_argument("--n", type=int, default=settings.N_ROLLOUTS)
    parser.add_argument("--batch", type=int, required=True)  # G15: set on the pilot
    args = parser.parse_args()
    out_dir = settings.DATA / args.run / args.generator / "rollouts"
    out_dir.mkdir(parents=True, exist_ok=True)

    commit = resolve(settings.GENERATORS[args.generator])
    model = AutoModelForCausalLM.from_pretrained(config.MODEL_ID, revision=commit,
                                                 dtype=getattr(torch, config.MODEL_DTYPE), device_map=DEVICE)
    model.eval()
    print(f"generator {args.generator}: {settings.GENERATORS[args.generator]} -> {commit}", flush=True)

    n_parts = (args.n + settings.PART_SIZE - 1) // settings.PART_SIZE
    timing = []  # (seconds, tokens) per finished part
    for k in range(n_parts):
        path = out_dir / f"part_{k:05d}.parquet"
        if path.exists():
            continue  # X1: resume
        size = min(settings.PART_SIZE, args.n - k * settings.PART_SIZE)
        gen = part_generator(args.run, k)
        t0 = time.time()
        rows = []
        for start in range(0, size, args.batch):
            rows += sample_batch(model, min(args.batch, size - start), gen)
        seconds = time.time() - t0
        part = pd.DataFrame({"rollout_id": [f"{args.generator}/{k:05d}/{i:03d}" for i in range(size)],
                             "ids": [ids for ids, _ in rows], "ended_by_eos": [eos for _, eos in rows]})
        tmp = out_dir / f"part_{k:05d}.tmp.parquet"
        part.to_parquet(tmp)
        os.replace(tmp, path)
        n_tok = int(part["ids"].map(len).sum())
        timing.append((seconds, n_tok))
        print(f"part {k + 1}/{n_parts}: {size} rollouts, {n_tok} tokens, {n_tok / seconds:.0f} tokens/s", flush=True)

    # Summary from the files on disk, so a resumed run counts every part
    parts = pd.concat([pd.read_parquet(p) for p in sorted(out_dir.glob("part_?????.parquet"))])
    lengths = parts["ids"].map(len).to_numpy()
    summary = {
        "run": args.run, "generator": args.generator, "revision": settings.GENERATORS[args.generator],
        "commit": commit, "rollouts": len(parts), "batch": args.batch,
        "ended_by_eos_share": round(float(parts["ended_by_eos"].mean()), 4),
        "empty_rollouts": int((lengths == 0).sum()),
        "length_quantiles": {q: int(np.quantile(lengths, q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
        "mean_length": round(float(lengths.mean()), 1),
        "tokens_per_second_this_session": round(sum(t for _, t in timing) / sum(s for s, _ in timing), 1) if timing else None,
        "peak_gpu_gb": round(torch.cuda.max_memory_allocated() / 1e9, 1),
        "gpu": torch.cuda.get_device_name(),
    }
    settings.RESULTS.mkdir(exist_ok=True)
    (settings.RESULTS / f"{args.run}_{args.generator}_rollouts_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
