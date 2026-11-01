"""Per-doc mean token NLL under the encoder model (design.md G54, G55). GPU worker; any number can run at once.

Usage: python s14_nll.py
Scores Dolma V (Exp 1) and every encoded doc of stage1, main, sft, dpo, instruct (full_post). Each worker claims the
next free part with a lock file (G21). Writes DATA/full_post/nll/<set>/part_<k>.npz: doc_id, n_tokens, n_pred,
nll_sum, nll_mean (nats; NaN for a 1-token doc, which has no prediction).
"""
import functools
import os
import time

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from s01_rollouts import claim
from s03_pilot import DEVICE, tokenize  # Exp 1

RUN = "full_post"
GENERATORS = ["stage1", "main", "sft", "dpo", "instruct"]
OUT = settings.DATA / RUN / "nll"
PART = settings.PART_SIZE  # 500 docs, as X1


def acts_run(g):
    """G54: the run whose acts the SAE input came from (stage1's acts are the `full` run's, symlinked, G35)."""
    return (settings.DATA / RUN / g / "acts").resolve().parents[1].name


@functools.cache
def v_parts():
    """V's doc ids in docs.parquet order, cut into parts of 500, with their doc_tokens from Exp 1's acts."""
    docs = pd.read_parquet(settings.EXP1_RUN / "docs.parquet", columns=["doc_id", "subset"])
    ids = docs.loc[docs["subset"] == "V", "doc_id"].to_numpy()
    return [ids[i:i + PART] for i in range(0, len(ids), PART)]


@functools.cache
def v_doc_tokens():
    keep = {d for part in v_parts() for d in part}
    out = {}
    for path in sorted((settings.EXP1_RUN / "acts").glob("part_?????.npz")):
        with np.load(path, allow_pickle=True) as z:
            for d, n in zip(z["doc_id"], z["doc_tokens"]):
                if d in keep:
                    out[d] = int(n)
    return out


@torch.inference_mode()
def doc_nll(model, ids):
    """G54: sum of -ln p(t_i | t_<i) for i = 1..n-1, log-softmax in float32."""
    if len(ids) < 2:
        return 0.0, 0
    x = torch.tensor([ids], device=DEVICE)
    logits = model(x).logits[0, :-1].float()
    return float(torch.nn.functional.cross_entropy(logits, x[0, 1:], reduction="sum")), len(ids) - 1


def score(model, path, doc_ids, token_lists, expected):
    n_tok = np.array([len(t) for t in token_lists], dtype=np.int32)
    bad = [d for d, n in zip(doc_ids, n_tok) if n != expected[d]]
    if bad:
        raise SystemExit(f"G54: {len(bad)} docs re-tokenize to a length other than doc_tokens in {path}, e.g. {bad[0]}")
    sums, preds = zip(*(doc_nll(model, t) for t in token_lists))
    sums, preds = np.array(sums), np.array(preds, dtype=np.int32)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(preds > 0, sums / np.maximum(preds, 1), np.nan)
    tmp = path.with_suffix(f".{os.getpid()}.tmp.npz")
    np.savez(tmp, doc_id=np.asarray(doc_ids), n_tokens=n_tok, n_pred=preds, nll_sum=sums, nll_mean=mean)
    os.replace(tmp, path)


def main():
    jobs = [("V", k, None) for k in range(len(v_parts()))]
    for g in GENERATORS:
        jobs += [(g, int(p.stem.split("_")[1]), p) for p in sorted((settings.DATA / RUN / g / "acts").glob("part_?????.npz"))]
    for s in {j[0] for j in jobs}:
        (OUT / s).mkdir(parents=True, exist_ok=True)
    if all((OUT / s / f"part_{k:05d}.npz").exists() for s, k, _ in jobs):
        print(f"all {len(jobs)} parts on disk", flush=True)
        return  # G21: a late worker exits without loading the model
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    model = AutoModelForCausalLM.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION,
                                                 dtype=getattr(torch, config.MODEL_DTYPE), device_map=DEVICE)  # Exp 1 row 12
    model.eval()
    v_text = None
    for s, k, acts_path in jobs:
        path, lock = OUT / s / f"part_{k:05d}.npz", OUT / s / f"part_{k:05d}.lock"
        if not claim(path, lock):
            continue
        t0 = time.time()
        if s == "V":
            if v_text is None:
                docs = pd.read_parquet(settings.EXP1_RUN / "docs.parquet", columns=["doc_id", "text"])
                v_text = docs.set_index("doc_id")["text"]
            doc_ids = list(v_parts()[k])
            expected = v_doc_tokens()
            token_lists = [tokenize(tokenizer, v_text.at[d])[0] for d in doc_ids]
        else:
            with np.load(acts_path, allow_pickle=True) as z:
                doc_ids, n = list(z["doc_id"]), z["doc_tokens"]
            expected = dict(zip(doc_ids, n.tolist()))
            rolls = pd.read_parquet(settings.DATA / RUN / s / "rollouts" / f"part_{k:05d}.parquet").set_index("rollout_id")["ids"]
            run = acts_run(s)
            token_lists = [tokenize(tokenizer, tokenizer.decode(settings.encoder_ids(run, rolls.at[d])))[0] for d in doc_ids]
        score(model, path, doc_ids, token_lists, expected)
        lock.unlink(missing_ok=True)
        print(f"{s} part {k}: {len(doc_ids)} docs, {(time.time() - t0) / len(doc_ids):.3f} s/doc", flush=True)


if __name__ == "__main__":
    main()
