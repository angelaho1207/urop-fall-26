"""Unprompted rollouts with pure sampling (design.md G1-G7, X1). GPU.

Usage: python s01_rollouts.py --run full --generator stage1 [--n 10000] [--batch auto]
Writes DATA/<run>/<generator>/rollouts/part_<k>.parquet (rollout_id, ids, ended_by_eos, batch, gpu, seconds) and
results/<run>_<generator>_rollouts_summary.json. Parts already on disk are skipped, so a rerun resumes (X1).
Several workers can run at once: each claims a part with a lock file first (G21).
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


LOCK_MINUTES = 10  # G21: workers touch their lock after every batch; one untouched this long was abandoned


def claim(done, lock):
    """G21: True if this worker may make the part. Creating the lock file is atomic, so two workers cannot both win."""
    if done.exists():
        return False
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        try:
            if time.time() - lock.stat().st_mtime < LOCK_MINUTES * 60:
                return False
            lock.unlink()  # abandoned: take it over
        except FileNotFoundError:
            pass
        return claim(done, lock)


def auto_batch():
    """G22: batch size from GPU memory, (GB - 17) / 0.75, between 8 and 128."""
    gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    return int(min(128, max(8, (gb - 17) / 0.75)))


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
    parser.add_argument("--batch", default="auto")  # G22
    args = parser.parse_args()
    out_dir = settings.DATA / args.run / args.generator / "rollouts"
    out_dir.mkdir(parents=True, exist_ok=True)

    n_parts = (args.n + settings.PART_SIZE - 1) // settings.PART_SIZE
    if all((out_dir / f"part_{k:05d}.parquet").exists() for k in range(n_parts)):
        print(f"{args.generator}: all {n_parts} parts done", flush=True)
        return  # G21: a late worker exits without loading the model
    commit = resolve(settings.GENERATORS[args.generator])
    model = AutoModelForCausalLM.from_pretrained(config.MODEL_ID, revision=commit,
                                                 dtype=getattr(torch, config.MODEL_DTYPE), device_map=DEVICE)
    model.eval()
    batch = auto_batch() if args.batch == "auto" else int(args.batch)
    gpu = torch.cuda.get_device_name()
    print(f"generator {args.generator}: {settings.GENERATORS[args.generator]} -> {commit}; {gpu}, batch {batch}", flush=True)

    for k in range(n_parts):
        path = out_dir / f"part_{k:05d}.parquet"
        lock = out_dir / f"part_{k:05d}.lock"
        if not claim(path, lock):
            continue  # X1, G21: done, or another worker has it
        size = min(settings.PART_SIZE, args.n - k * settings.PART_SIZE)
        gen = part_generator(args.run, k)
        t0 = time.time()
        rows = []
        for start in range(0, size, batch):
            rows += sample_batch(model, min(batch, size - start), gen)
            lock.touch()  # G21: heartbeat
        seconds = time.time() - t0
        part = pd.DataFrame({"rollout_id": [f"{args.generator}/{k:05d}/{i:03d}" for i in range(size)],
                             "ids": [ids for ids, _ in rows], "ended_by_eos": [eos for _, eos in rows],
                             "batch": batch, "gpu": gpu, "seconds": seconds})  # G22: per part, for reproducibility
        tmp = out_dir / f"part_{k:05d}.{os.getpid()}.tmp.parquet"
        part.to_parquet(tmp)
        os.replace(tmp, path)
        lock.unlink(missing_ok=True)
        n_tok = int(part["ids"].map(len).sum())
        print(f"part {k + 1}/{n_parts}: {size} rollouts, {n_tok} tokens, {n_tok / seconds:.0f} tokens/s", flush=True)

    # Summary from the files on disk, so a resumed run counts every part
    parts = pd.concat([pd.read_parquet(p) for p in sorted(out_dir.glob("part_?????.parquet"))])
    lengths = parts["ids"].map(len).to_numpy()
    summary = {
        "run": args.run, "generator": args.generator, "revision": settings.GENERATORS[args.generator],
        "commit": commit, "rollouts": len(parts), "parts_done": int(parts["rollout_id"].str[:-4].nunique()),
        "ended_by_eos_share": round(float(parts["ended_by_eos"].mean()), 4),
        "empty_rollouts": int((lengths == 0).sum()),
        "length_quantiles": {q: int(np.quantile(lengths, q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
        "mean_length": round(float(lengths.mean()), 1),
    }
    if "gpu" in parts:  # G22: speed per GPU type over all parts on disk
        per_part = parts.assign(n=lengths).groupby(parts["rollout_id"].str[:-4]).agg(
            gpu=("gpu", "first"), batch=("batch", "first"), seconds=("seconds", "first"), tokens=("n", "sum"))
        summary["tokens_per_second_by_gpu"] = {g: round(float(d["tokens"].sum() / d["seconds"].sum()), 1)
                                               for g, d in per_part.groupby("gpu")}
    settings.RESULTS.mkdir(exist_ok=True)
    (settings.RESULTS / f"{args.run}_{args.generator}_rollouts_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
