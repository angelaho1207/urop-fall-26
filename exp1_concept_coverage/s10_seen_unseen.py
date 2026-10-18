"""Seen vs unseen check (row F8): does the SAE behave differently on rows it trained on? GPU, no API.

Usage: python s10_seen_unseen.py [--rows-per-group 2500]
Draws rows from the SAE's own training dataset: "seen" from parquet files 0-24 (rows below 869,700, all inside the
first 1B tokens that training read), "unseen" from files 40-63 (rows from 1,391,520). Each side is split into two
halves (A, B) so seen A vs seen B gives the noise floor. Runs the model and SAE as s04 does (bf16 weights, layer 16,
no BOS) on the stored token ids and saves per-group metrics to results/f8_seen_unseen.json and per-concept token
firing counts to DATA/f8/firing_counts.npz.
"""
import argparse
import json
import time

import config  # first: sets HF_HOME
import numpy as np
import pandas as pd
import torch
from huggingface_hub import hf_hub_download
from scipy.stats import spearmanr
from transformers import AutoModelForCausalLM, AutoTokenizer

from s03_pilot import DEVICE, VarianceExplained, layer_input, load_sae

SAE_DATA_ID = "chanind/pile-uncopyrighted-olmo-3-1024-abbrv-2B"  # runner_cfg.json dataset_path
SAE_DATA_REVISION = "e66fd5df0ef96d3a687e7addc1e77b1835fc5bcd"
N_FILES = 64
SEEN_FILES = range(0, 25)  # rows < 869,700; training read rows < about 1.03M
UNSEEN_FILES = range(40, 64)  # rows >= 1,391,520
D_SAE = 65_536
MIN_TOKENS = 40  # a concept enters a rate comparison only if it fires on at least 40 tokens in both groups
FLOOR_PERCENTILE = 95


def draw_rows(files, n, seed):
    """n rows drawn uniformly without replacement from the given parquet files, seeded; returns token id lists."""
    tables = []
    for i in files:
        path = hf_hub_download(SAE_DATA_ID, f"data/train-{i:05d}-of-{N_FILES:05d}.parquet", repo_type="dataset",
                               revision=SAE_DATA_REVISION, cache_dir=config.SCRATCH / "hf_sae_data")
        t = pd.read_parquet(path)
        t["file"] = i
        t["row_in_file"] = np.arange(len(t))
        tables.append(t)
    rows = pd.concat(tables, ignore_index=True)
    pick = np.random.default_rng(seed).choice(len(rows), size=n, replace=False)
    return rows.iloc[pick][["file", "row_in_file", "input_ids"]].reset_index(drop=True)


def run_group(model, sae, id_lists, special):
    """Pooled FVE and L0 over non-special tokens (training excluded special tokens), and token firing counts."""
    stats, fires = VarianceExplained(), torch.zeros(D_SAE, dtype=torch.int64, device=DEVICE)
    for ids in id_lists:
        ids = [int(t) for t in ids]
        keep = torch.tensor([t not in special for t in ids], device=DEVICE)
        with torch.no_grad():
            x = layer_input(model, ids, autocast=False)[keep]  # row 12: bf16 weights, no autocast (as s04)
            acts = sae.encode(x)
            stats.add(x, sae.decode(acts), acts)
            fires += (acts > 0).sum(0)
    return stats.result(), fires.cpu().numpy()


def compare(fa, ta, fb, tb):
    """Spearman of token firing rates and |log rate ratio| per concept, over concepts with enough firing in both."""
    ok = (fa >= MIN_TOKENS) & (fb >= MIN_TOKENS)
    ra, rb = fa[ok] / ta, fb[ok] / tb
    return {"concepts": int(ok.sum()), "spearman": round(float(spearmanr(ra, rb)[0]), 4)}, np.abs(np.log(ra / rb))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows-per-group", type=int, default=2500)
    args = parser.parse_args()
    n = args.rows_per_group
    t0 = time.time()
    seen = draw_rows(SEEN_FILES, 2 * n, [config.SEED, 8000, 0])
    unseen = draw_rows(UNSEEN_FILES, 2 * n, [config.SEED, 8000, 1])
    print(f"rows drawn in {time.time() - t0:.0f}s; lengths {set(seen['input_ids'].map(len)) | set(unseen['input_ids'].map(len))}",
          flush=True)
    groups = {"seen_A": seen[:n], "seen_B": seen[n:], "unseen_A": unseen[:n], "unseen_B": unseen[n:]}

    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    special = set(tokenizer.all_special_ids)
    sae = load_sae()
    model = AutoModelForCausalLM.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION,
                                                 dtype=getattr(torch, config.MODEL_DTYPE), device_map=DEVICE)
    model.eval()
    special_share = {g: float(np.mean([t in special for ids in r["input_ids"] for t in ids])) for g, r in groups.items()}

    metrics, fires = {}, {}
    for g, rows in groups.items():
        t1 = time.time()
        metrics[g], fires[g] = run_group(model, sae, rows["input_ids"], special)
        print(f"{g}: {metrics[g]} in {time.time() - t1:.0f}s", flush=True)

    tokens = {g: metrics[g]["tokens"] for g in groups}
    floor_stats, floor = compare(fires["seen_A"], tokens["seen_A"], fires["seen_B"], tokens["seen_B"])
    cut = float(np.percentile(floor, FLOOR_PERCENTILE))
    tests = {}
    for a, b in [("seen_A", "unseen_A"), ("seen_B", "unseen_B"), ("unseen_A", "unseen_B")]:
        s, d = compare(fires[a], tokens[a], fires[b], tokens[b])
        s["share_beyond_floor"] = round(float(np.mean(d > cut)), 4)  # about 0.05 if seen and unseen do not differ
        tests[f"{a}_vs_{b}"] = s
    out = {"dataset": SAE_DATA_ID, "revision": SAE_DATA_REVISION, "rows_per_group": n,
           "seen_files": [SEEN_FILES.start, SEEN_FILES.stop - 1], "unseen_files": [UNSEEN_FILES.start, UNSEEN_FILES.stop - 1],
           "special_token_share": special_share, "metrics": metrics,
           "floor_seen_A_vs_seen_B": {**floor_stats, f"abs_log_ratio_p{FLOOR_PERCENTILE}": round(cut, 4)},
           "comparisons": tests, "seconds": round(time.time() - t0)}
    (config.RESULTS / "f8_seen_unseen.json").write_text(json.dumps(out, indent=2))
    (config.DATA / "f8").mkdir(parents=True, exist_ok=True)
    np.savez(config.DATA / "f8" / "firing_counts.npz", **fires,
             **{f"{g}_rows": np.stack([groups[g]["file"], groups[g]["row_in_file"]]) for g in groups})
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
