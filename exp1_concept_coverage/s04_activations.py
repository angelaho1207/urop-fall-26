"""SAE activations for every sampled doc (rows 9-15, T10-T12).

Usage: python s04_activations.py --run pilot   (the full run goes through sbatch, T14)
Reads DATA/<run>/docs.parquet. Writes DATA/<run>/acts/part_<k>.npz (1,000 docs each) and
results/<run>_activation_summary.json. Parts already on disk are skipped, so a rerun resumes (T12).
"""
import argparse
import json
import os
import time

import config  # first: sets HF_HOME
import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from s03_pilot import DEVICE, layer_input, load_sae, tokenize

PART_SIZE = 1000


def encode_part(model, sae, token_lists):
    """T11: token-level activations in CSR form, plus per-doc mean, max and argmax for each active concept."""
    out = {k: [] for k in ["doc_tokens", "tok_counts", "latent_ids", "values",
                           "doc_active", "doc_latent_ids", "doc_mean", "doc_max", "doc_argmax"]}
    for ids in token_lists:
        # Row 12: bf16 weights, no autocast. Row 10: position 0 is kept
        acts = sae.encode(layer_input(model, ids, autocast=False))  # (tokens, 65,536), >= 0
        rows, cols = acts.nonzero(as_tuple=True)  # sorted by token, then concept
        out["doc_tokens"].append(acts.shape[0])
        out["tok_counts"].append(torch.bincount(rows, minlength=acts.shape[0]).to(torch.int32).cpu())
        out["latent_ids"].append(cols.to(torch.int32).cpu())
        out["values"].append(acts[rows, cols].half().cpu())
        top = acts.max(0)
        active = (top.values > 0).nonzero(as_tuple=True)[0]  # concepts that fire somewhere in this doc
        out["doc_active"].append(len(active))
        out["doc_latent_ids"].append(active.to(torch.int32).cpu())
        out["doc_mean"].append(acts.mean(0)[active].cpu())  # row 14, Eq. 1
        out["doc_max"].append(top.values[active].cpu())  # row 15
        out["doc_argmax"].append(top.indices[active].to(torch.int32).cpu())
    return {
        "doc_tokens": np.array(out["doc_tokens"], dtype=np.int32),
        "tok_counts": torch.cat(out["tok_counts"]).numpy().astype(np.uint16),
        "latent_ids": torch.cat(out["latent_ids"]).numpy().astype(np.uint16),  # 65,535 is the largest id
        "values": torch.cat(out["values"]).numpy(),
        "doc_active": np.array(out["doc_active"], dtype=np.int32),
        "doc_latent_ids": torch.cat(out["doc_latent_ids"]).numpy().astype(np.uint16),
        "doc_mean": torch.cat(out["doc_mean"]).numpy().astype(np.float32),
        "doc_max": torch.cat(out["doc_max"]).numpy().astype(np.float32),
        "doc_argmax": torch.cat(out["doc_argmax"]).numpy().astype(np.uint16),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    run_dir = config.DATA / args.run
    acts_dir = run_dir / "acts"
    acts_dir.mkdir(parents=True, exist_ok=True)

    docs = pd.read_parquet(run_dir / "docs.parquet", columns=["doc_id", "text"])
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    sae = load_sae()
    model = AutoModelForCausalLM.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION,
                                                 dtype=getattr(torch, config.MODEL_DTYPE), device_map=DEVICE)
    model.eval()

    n_parts = (len(docs) + PART_SIZE - 1) // PART_SIZE
    seconds = []
    for k in range(n_parts):
        path = acts_dir / f"part_{k:05d}.npz"
        if path.exists():
            continue  # T12: resume
        part = docs.iloc[k * PART_SIZE:(k + 1) * PART_SIZE]
        t0 = time.time()
        arrays = encode_part(model, sae, [tokenize(tokenizer, t)[0] for t in part["text"]])
        tmp = acts_dir / f"part_{k:05d}.tmp.npz"
        np.savez(tmp, doc_id=part["doc_id"].to_numpy(), **arrays)
        os.replace(tmp, path)  # T12: a finished part appears under its final name in one step
        seconds.append((time.time() - t0) / len(part))
        print(f"part {k + 1}/{n_parts}: {len(part)} docs, {seconds[-1]:.3f} s/doc", flush=True)

    # Summary from the files on disk, so a resumed run counts every part
    tokens = entries = 0
    size = 0
    for k in range(n_parts):
        path = acts_dir / f"part_{k:05d}.npz"
        with np.load(path, allow_pickle=True) as z:
            tokens += int(z["doc_tokens"].sum())
            entries += len(z["latent_ids"])
        size += path.stat().st_size
    summary = {"run": args.run, "docs": len(docs), "parts": n_parts, "tokens": tokens,
               "mean_active_per_token": round(entries / tokens, 2), "gb_on_disk": round(size / 1e9, 2),
               "model_dtype": config.MODEL_DTYPE, "exclude_position_0": config.EXCLUDE_POSITION_0,
               "seconds_per_doc_this_session": round(float(np.mean(seconds)), 3) if seconds else None}
    (config.RESULTS / f"{args.run}_activation_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
