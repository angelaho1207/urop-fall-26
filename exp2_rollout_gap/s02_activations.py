"""SAE activations for every rollout, through Exp 1's pipeline unchanged (design.md G8, X1). GPU.

Usage: python s02_activations.py --run pilot --generator stage1
Reads DATA/<run>/<generator>/rollouts/part_<k>.parquet (from s01). Writes DATA/<run>/<generator>/acts/part_<k>.npz
in Exp 1's T11 format and results/<run>_<generator>_activation_summary.json. Parts already on disk are skipped.
In the runs of settings.DROP_SPECIAL, ids >= 100256 are removed before decoding (G34) and counted.
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

from s01_rollouts import claim
from s03_pilot import DEVICE, load_sae, tokenize  # Exp 1
from s04_activations import encode_part  # Exp 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, choices=list(settings.SEED_ROOT))
    parser.add_argument("--generator", required=True, choices=list(settings.GENERATORS))
    args = parser.parse_args()
    gen_dir = settings.DATA / args.run / args.generator
    acts_dir = gen_dir / "acts"
    acts_dir.mkdir(parents=True, exist_ok=True)

    srcs = sorted((gen_dir / "rollouts").glob("part_?????.parquet"))
    if all((acts_dir / s.name.replace(".parquet", ".npz")).exists() for s in srcs):
        print(f"{args.generator}: all {len(srcs)} rollout parts on disk are encoded", flush=True)
        return  # G21: a late worker exits without loading the model
    # G8: the encoder is always the final model at Exp 1's pinned revision, whichever model wrote the rollout
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    sae = load_sae()
    model = AutoModelForCausalLM.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION,
                                                 dtype=getattr(torch, config.MODEL_DTYPE), device_map=DEVICE)
    model.eval()

    seconds = []
    for src in srcs:
        path = acts_dir / src.name.replace(".parquet", ".npz")
        lock = acts_dir / src.name.replace(".parquet", ".lock")
        if not claim(path, lock):
            continue  # X1, G21: done, or another worker has it
        part = pd.read_parquet(src)
        n_empty = int((part["ids"].map(len) == 0).sum())
        part = part[part["ids"].map(len) > 0]  # G3: empty rollouts have no tokens to encode
        # G34: ids >= 100256 removed before decoding (in DROP_SPECIAL runs); rollouts left empty are dropped, as G3
        special = [np.asarray(ids)[np.asarray(ids) >= settings.SPECIAL_MIN] for ids in part["ids"]]
        kept_ids = [settings.encoder_ids(args.run, ids) for ids in part["ids"]]
        special_all = np.concatenate(special + [np.zeros(0, dtype=np.int64)])  # every generated special id, empty-after-drop rollouts included
        nonempty = np.array([len(ids) > 0 for ids in kept_ids], dtype=bool)
        part = part[nonempty]
        special = [x for x, k in zip(special, nonempty) if k]
        kept_ids = [x for x, k in zip(kept_ids, nonempty) if k]
        # G8: decode to text, then the same tokenize() as every Dolma doc (no special tokens, cut to 1,024)
        texts = [tokenizer.decode(ids) for ids in kept_ids]
        token_lists = [tokenize(tokenizer, t)[0] for t in texts]
        retokenized_same = np.array([list(a) == list(b) for a, b in zip(kept_ids, token_lists)])
        # Check 5 (G34, G36): special ids in the generated rollout, and in the SAE input after decode and re-tokenize
        n_special_generated = np.array([len(x) for x in special], dtype=np.int32)
        n_special_input = np.array([sum(t >= settings.SPECIAL_MIN for t in ids) for ids in token_lists], dtype=np.int32)
        t0 = time.time()
        arrays = encode_part(model, sae, token_lists)
        tmp = acts_dir / src.name.replace(".parquet", f".{os.getpid()}.tmp.npz")
        np.savez(tmp, doc_id=part["rollout_id"].to_numpy(), retokenized_same=retokenized_same,
                 n_special_generated=n_special_generated, n_special_input=n_special_input,
                 special_ids_generated=special_all,
                 empty_generated=n_empty, empty_after_special_drop=int((~nonempty).sum()), **arrays)
        os.replace(tmp, path)
        lock.unlink(missing_ok=True)
        seconds.append((time.time() - t0) / len(part))
        print(f"{src.name}: {len(part)} rollouts, {seconds[-1]:.3f} s/rollout", flush=True)

    # Summary from the files on disk, so a resumed run counts every part
    docs = tokens = entries = same = 0
    check = {"empty_generated": 0, "empty_after_special_drop": 0, "special_ids_generated": 0,
             "rollouts_with_special_ids": 0, "special_ids_in_sae_input": 0}
    special_by_id = {}
    for path in sorted(acts_dir.glob("part_?????.npz")):
        with np.load(path, allow_pickle=True) as z:
            docs += len(z["doc_id"])
            tokens += int(z["doc_tokens"].sum())
            entries += len(z["latent_ids"])
            same += int(z["retokenized_same"].sum())
            if "n_special_generated" not in z.files:
                continue  # parts written before G34 (runs pilot, full)
            for k in ("empty_generated", "empty_after_special_drop"):
                check[k] += int(z[k])
            check["special_ids_generated"] += len(z["special_ids_generated"])
            check["rollouts_with_special_ids"] += int((z["n_special_generated"] > 0).sum()) + int(z["empty_after_special_drop"])
            check["special_ids_in_sae_input"] += int(z["n_special_input"].sum())
            for i, c in zip(*np.unique(z["special_ids_generated"], return_counts=True)):
                special_by_id[str(int(i))] = special_by_id.get(str(int(i)), 0) + int(c)
    summary = {"run": args.run, "generator": args.generator, "encoder_revision": config.MODEL_REVISION,
               "rollouts_encoded": docs, "tokens": tokens, "mean_active_per_token": round(entries / tokens, 2),
               "retokenized_different": docs - same,
               "drop_special_ids": args.run in settings.DROP_SPECIAL,  # G34
               **check, "special_ids_generated_by_id": dict(sorted(special_by_id.items())),
               "seconds_per_rollout_this_session": round(float(np.mean(seconds)), 3) if seconds else None}
    (settings.RESULTS / f"{args.run}_{args.generator}_activation_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
