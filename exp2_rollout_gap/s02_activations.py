"""SAE activations for every rollout, through Exp 1's pipeline unchanged (design.md G8, X1). GPU.

Usage: python s02_activations.py --run pilot --generator stage1
Reads DATA/<run>/<generator>/rollouts/part_<k>.parquet (from s01). Writes DATA/<run>/<generator>/acts/part_<k>.npz
in Exp 1's T11 format and results/<run>_<generator>_activation_summary.json. Parts already on disk are skipped.
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
from transformers import AutoModelForCausalLM, AutoTokenizer

from s03_pilot import DEVICE, load_sae, tokenize  # Exp 1
from s04_activations import encode_part  # Exp 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, choices=["pilot", "full"])
    parser.add_argument("--generator", required=True, choices=list(settings.GENERATORS))
    args = parser.parse_args()
    gen_dir = settings.DATA / args.run / args.generator
    acts_dir = gen_dir / "acts"
    acts_dir.mkdir(parents=True, exist_ok=True)

    # G8: the encoder is always the final model at Exp 1's pinned revision, whichever model wrote the rollout
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    sae = load_sae()
    model = AutoModelForCausalLM.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION,
                                                 dtype=getattr(torch, config.MODEL_DTYPE), device_map=DEVICE)
    model.eval()

    seconds = []
    for src in sorted((gen_dir / "rollouts").glob("part_?????.parquet")):
        path = acts_dir / src.name.replace(".parquet", ".npz")
        if path.exists():
            continue  # X1: resume
        part = pd.read_parquet(src)
        part = part[part["ids"].map(len) > 0]  # G3: empty rollouts have no tokens to encode
        # G8: decode to text, then the same tokenize() as every Dolma doc (no special tokens, cut to 1,024)
        texts = [tokenizer.decode(ids) for ids in part["ids"]]
        token_lists = [tokenize(tokenizer, t)[0] for t in texts]
        retokenized_same = np.array([list(a) == list(b) for a, b in zip(part["ids"], token_lists)])
        t0 = time.time()
        arrays = encode_part(model, sae, token_lists)
        tmp = acts_dir / src.name.replace(".parquet", ".tmp.npz")
        np.savez(tmp, doc_id=part["rollout_id"].to_numpy(), retokenized_same=retokenized_same, **arrays)
        os.replace(tmp, path)
        seconds.append((time.time() - t0) / len(part))
        print(f"{src.name}: {len(part)} rollouts, {seconds[-1]:.3f} s/rollout", flush=True)

    # Summary from the files on disk, so a resumed run counts every part
    docs = tokens = entries = same = 0
    for path in sorted(acts_dir.glob("part_?????.npz")):
        with np.load(path, allow_pickle=True) as z:
            docs += len(z["doc_id"])
            tokens += int(z["doc_tokens"].sum())
            entries += len(z["latent_ids"])
            same += int(z["retokenized_same"].sum())
    summary = {"run": args.run, "generator": args.generator, "encoder_revision": config.MODEL_REVISION,
               "rollouts_encoded": docs, "tokens": tokens, "mean_active_per_token": round(entries / tokens, 2),
               "retokenized_different": docs - same,
               "seconds_per_rollout_this_session": round(float(np.mean(seconds)), 3) if seconds else None}
    (settings.RESULTS / f"{args.run}_{args.generator}_activation_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
