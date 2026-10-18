"""Pilot checks 1-7, 9 and 11 on the GPU (P1, P7-P16).

Usage: python s03_pilot.py --run pilot   (inside the tunnel GPU job)
Reads DATA/<run>/docs.parquet and results/<run>_sample_summary.json.
Saves results/<run>_pilot_checks.json and DATA/<run>/doc_stats.npz.
"""
import argparse
import io
import json
import platform
import time

import config  # first: sets HF_HOME
import numpy as np
import pandas as pd
import sae_lens
import torch
import transformers
import zstandard
from huggingface_hub import HfFileSystem, snapshot_download
from sae_lens import SAE
from transformers import AutoModelForCausalLM, AutoTokenizer

torch.set_grad_enabled(False)
DEVICE = "cuda"


def load_sae():
    """P9: download only the layer-16 folder at the pinned revision, then load it from disk."""
    root = snapshot_download(config.SAE_REPO, revision=config.SAE_REVISION, allow_patterns=[f"{config.SAE_ID}/*"])
    return SAE.load_from_disk(f"{root}/{config.SAE_ID}", device=DEVICE)


def load_pile_texts():
    """P7: 50 docs drawn with seed 0 from the first 10,000 docs of a Pile file the SAE never trained on."""
    path = f"datasets/{config.PILE_ID}@{config.PILE_REVISION}/{config.PILE_FILE}"
    texts = []
    with HfFileSystem().open(path, "rb") as f:
        reader = io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(f), encoding="utf-8")
        for line in reader:
            text = json.loads(line)["text"]
            if text.strip():  # row 11: non-empty docs only, as for Dolma
                texts.append(text)
            if len(texts) == config.PILE_HEAD_DOCS:
                break
    picks = np.random.default_rng(config.SEED).choice(len(texts), size=config.PILE_N_DOCS, replace=False)
    return [texts[i] for i in sorted(picks)]


def tokenize(tokenizer, text):
    """P10, rows 9-10: no special tokens added, cut to 1,024 tokens. Also returns the uncut length."""
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    return ids[: config.CONTEXT], len(ids)


def layer_input(model, ids, autocast):
    """Row 13: the residual stream after decoder layer 16, i.e. hidden_states[17], as float32."""
    input_ids = torch.tensor([ids], device=DEVICE)
    # Row 12: setup (1) runs bf16 autocast over fp32 weights, as in SAE training
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=autocast):
        out = model.model(input_ids, output_hidden_states=True)  # model.model skips the unembedding
    return out.hidden_states[config.HIDDEN_STATES_INDEX][0].float()


class VarianceExplained:
    """P12: pooled fraction of variance explained and L0, from running sums so tokens need not be kept."""

    def __init__(self):
        self.n = 0
        self.sum_x = 0.0
        self.sum_sq = 0.0
        self.sum_err = 0.0
        self.active = 0

    def add(self, x, x_hat, acts):
        x64 = x.double()
        self.n += x.shape[0]
        self.sum_x = self.sum_x + x64.sum(0)
        self.sum_sq += (x64 ** 2).sum().item()
        self.sum_err += ((x64 - x_hat.double()) ** 2).sum().item()
        self.active += (acts > 0).sum().item()

    def result(self):
        mean = self.sum_x / self.n
        total = self.sum_sq - self.n * (mean ** 2).sum().item()  # sum ||x - mean||^2 = sum ||x||^2 - n ||mean||^2
        return {"tokens": self.n, "fve": round(1 - self.sum_err / total, 5), "l0": round(self.active / self.n, 2)}


def encode(sae, x):
    acts = sae.encode(x)
    return acts, sae.decode(acts)


def run_set(model, sae, token_lists, autocast, keep_doc_stats=False):
    """Run docs through model + SAE; return pooled metrics, position-0 numbers, timing and optional per-doc stats."""
    all_tok, pos0, rest = VarianceExplained(), VarianceExplained(), VarianceExplained()
    norm_ratio, seconds, means, maxes, argmaxes = [], [], [], [], []
    for ids in token_lists:
        torch.cuda.synchronize()
        t0 = time.time()
        x = layer_input(model, ids, autocast)
        acts, x_hat = encode(sae, x)
        torch.cuda.synchronize()
        seconds.append(time.time() - t0)
        all_tok.add(x, x_hat, acts)
        pos0.add(x[:1], x_hat[:1], acts[:1])
        if len(ids) > 1:
            rest.add(x[1:], x_hat[1:], acts[1:])
            norms = x.norm(dim=1)
            norm_ratio.append((norms[0] / norms[1:].median()).item())  # P14: position 0 vs typical position
        if keep_doc_stats:
            means.append(acts.mean(0).cpu().numpy())  # row 14, Eq. 1: per-doc mean over tokens
            top = acts.max(0)
            maxes.append(top.values.cpu().numpy())  # row 15: max token activation per concept
            argmaxes.append(top.indices.to(torch.int16).cpu().numpy())
    result = {
        "all_tokens": all_tok.result(), "position_0": pos0.result(),
        "positions_1_on": rest.result() if rest.n else None,
        "pos0_norm_over_median_norm": np.quantile(norm_ratio, [0.1, 0.5, 0.9]).round(2).tolist() if norm_ratio else None,
        "seconds_per_doc": round(float(np.mean(seconds)), 3),
    }
    stats = (np.stack(means), np.stack(maxes), np.stack(argmaxes)) if keep_doc_stats else None
    return result, stats


def compare_setup(model, sae, token_lists, x_ref, autocast):
    """P13: one precision setup vs setup (1) on the same docs."""
    fve, rel_x, rel_acts, overlap, seconds = VarianceExplained(), [], [], [], []
    for ids, x1 in zip(token_lists, x_ref):
        torch.cuda.synchronize()
        t0 = time.time()
        x = layer_input(model, ids, autocast)
        acts, x_hat = encode(sae, x)
        torch.cuda.synchronize()
        seconds.append(time.time() - t0)
        fve.add(x, x_hat, acts)
        x1 = x1.to(DEVICE)
        acts1, _ = encode(sae, x1)
        rel_x.append((x - x1).norm(dim=1) / x1.norm(dim=1))
        has = acts1.norm(dim=1) > 0
        rel_acts.append(((acts - acts1).norm(dim=1) / acts1.norm(dim=1))[has])
        # Share of each token's top-10 concepts that also appear in setup (1)'s top 10. Only tokens with at
        # least 10 active concepts in setup (1) count; below that, topk would rank arbitrary zeros
        full = (acts1 > 0).sum(1) >= 10
        top, top1 = acts[full].topk(10, dim=1).indices, acts1[full].topk(10, dim=1).indices
        overlap.append((top.unsqueeze(2) == top1.unsqueeze(1)).any(2).float().mean(1))
    return {
        **fve.result(),
        "mean_rel_diff_residual": round(torch.cat(rel_x).mean().item(), 5),
        "mean_rel_diff_latents": round(torch.cat(rel_acts).mean().item(), 5),
        "mean_top10_overlap": round(torch.cat(overlap).mean().item(), 4),
        "seconds_per_doc": round(float(np.mean(seconds)), 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    out_dir = config.DATA / args.run
    checks = {"run": args.run, "versions": {"python": platform.python_version(), "torch": torch.__version__,
              "transformers": transformers.__version__, "sae_lens": sae_lens.__version__,
              "gpu": torch.cuda.get_device_name(0)}}

    docs = pd.read_parquet(out_dir / "docs.parquet")
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    special = set(tokenizer.all_special_ids)
    tokenized = [tokenize(tokenizer, t) for t in docs["text"]]
    docs["tokens"] = [ids for ids, _ in tokenized]
    docs["n_tokens"] = [n for _, n in tokenized]
    docs["length"] = docs["tokens"].map(len)

    # Rows 9, 10, 11 and P10
    checks["tokens"] = {
        "special_ids": sorted(special),
        "docs_with_special_ids": int(docs["tokens"].map(lambda ids: any(i in special for i in ids)).sum()),
        "by_source": {
            s: {"docs": int(len(g)), "truncated_share": round(float((g["n_tokens"] > config.CONTEXT).mean()), 3),
                "under_30_tokens": int((g["n_tokens"] < 30).sum()),
                "n_tokens_quantiles_10_50_90": g["n_tokens"].quantile([0.1, 0.5, 0.9]).round(0).tolist()}
            for s, g in docs.groupby("source")
        },
    }
    pile_tokens = [tokenize(tokenizer, t)[0] for t in load_pile_texts()]

    sae = load_sae()
    model = AutoModelForCausalLM.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION,
                                                 dtype=torch.float32, device_map=DEVICE)
    model.eval()
    # Without this, autocast keeps a bf16 copy of every weight (14.6 GB) next to the fp32 weights (29 GB),
    # which would overflow the L40S's 46 GB. Autocast only caches casts of tensors that require grad
    model.requires_grad_(False)

    # Check 1 (row 13): a forward hook on layer 16 must return the same tensor as hidden_states[17]
    captured = {}
    handle = model.model.layers[config.LAYER].register_forward_hook(
        lambda module, inputs, output: captured.update(x=output[0] if isinstance(output, tuple) else output))
    equal = []
    for ids in docs["tokens"][: config.PILOT_HOOK_CHECK_DOCS]:
        x = layer_input(model, ids, autocast=True)
        equal.append(torch.equal(captured["x"][0].float(), x))
    handle.remove()
    checks["check1_hook_equals_hidden_states_17"] = all(equal)

    # Checks 2, 4, 5 on all Dolma docs with setup (1); keep the residuals of the precision docs
    rng = np.random.default_rng(config.SEED)
    precision_rows = sorted(rng.choice(len(docs), size=config.PILOT_PRECISION_DOCS, replace=False).tolist())
    precision_tokens = [docs["tokens"][i] for i in precision_rows]
    x_ref = [layer_input(model, ids, autocast=True).cpu() for ids in precision_tokens]
    dolma, (means, maxes, argmaxes) = run_set(model, sae, docs["tokens"], autocast=True, keep_doc_stats=True)
    checks["check2_4_5_dolma_setup1"] = dolma

    # Check 11 (row 22): the same numbers on 50 held-out Pile docs
    checks["check11_pile_setup1"], _ = run_set(model, sae, pile_tokens, autocast=True)

    # Check 3 (row 12, P13): setup (3) full fp32, then setup (2) bf16 weights. The stored weights are bf16,
    # so casting the fp32 copy back to bf16 recovers them
    setup3 = compare_setup(model, sae, precision_tokens, x_ref, autocast=False)
    model.to(torch.bfloat16)
    setup2 = compare_setup(model, sae, precision_tokens, x_ref, autocast=False)
    checks["check3_precision_vs_setup1"] = {"docs": len(precision_rows), "setup2_bf16_weights": setup2,
                                            "setup3_full_fp32": setup3}

    # Check 4 (P14) and check 7 (row 15): where do concepts peak, and how long are their top docs
    lengths = docs["length"].to_numpy()
    fires = maxes > 0
    firing = fires.any(0)
    top_doc = maxes.argmax(0)
    top_pos = argmaxes[top_doc, np.arange(maxes.shape[1])]
    checks["check4_concepts_peaking_at_position_0"] = round(float((top_pos[firing] == 0).mean()), 4)
    checks["check7_lengths"] = {
        "sample_length_quantiles_10_50_90": np.quantile(lengths, [0.1, 0.5, 0.9]).round(0).tolist(),
        "top_doc_length_quantiles_10_50_90": np.quantile(lengths[top_doc[firing]], [0.1, 0.5, 0.9]).round(0).tolist(),
    }

    # Check 9 (P15): firing rate per concept -> expected firing docs per subset (0.2 N rate) for candidate N and k
    rate = fires.mean(0)
    prefix = rate[: config.PREFIX_WIDTH]
    checks["check9_firing"] = {
        "concepts_never_firing_in_pilot": int((~firing).sum()),
        "prefix_never_firing_in_pilot": int((prefix == 0).sum()),
        "prefix_rate_quantiles_10_50_90": np.quantile(prefix, [0.1, 0.5, 0.9]).round(4).tolist(),
        "prefix_share_with_k_docs_per_subset": {
            f"k={k}": {f"N={n}": round(float((config.VAL_FRACTION * n * prefix >= k).mean()), 3)
                       for n in config.CANDIDATE_N}
            for k in config.CANDIDATE_K
        },
    }

    np.savez(out_dir / "doc_stats.npz", doc_id=docs["doc_id"].to_numpy(), length=lengths,
             means=means, maxes=maxes, argmaxes=argmaxes)
    path = config.RESULTS / f"{args.run}_pilot_checks.json"
    path.write_text(json.dumps(checks, indent=2))
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
