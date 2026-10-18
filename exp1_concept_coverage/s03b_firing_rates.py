"""Firing rates from the pilot, to set N (row 20, P23). CPU only.

Usage: python s03b_firing_rates.py --run pilot
Reads DATA/<run>/doc_stats.npz. Saves results/<run>_firing_rates.json.
The underrepresented set here is preliminary: Eq. 2 on the pilot docs, used only to size N.
"""
import argparse
import json

import config
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--run", required=True)
args = parser.parse_args()

stats = np.load(config.DATA / args.run / "doc_stats.npz", allow_pickle=True)
rate = (stats["maxes"] > 0).mean(0)  # share of docs where each concept fires at least once
coverage = stats["means"].mean(0)  # Eq. 2 numerator up to a constant: mean over docs of the per-doc mean
chi = coverage / coverage.mean()  # Eq. 2: normalize by the mean over concepts
nonmissing = chi >= np.exp(-5)  # row 14 main threshold
under = nonmissing & (chi <= np.quantile(chi[nonmissing], 0.10))  # row 14: bottom decile of non-missing

groups = {"all": np.ones_like(rate, bool), "prefix_2048": np.arange(len(rate)) < config.PREFIX_WIDTH,
          "preliminary_under": under}
result = {"run": args.run, "docs": int(len(stats["maxes"])),
          "never_fire": int((rate == 0).sum()), "chi_below_e^-5": int((~nonmissing).sum())}
for name, mask in groups.items():
    r = rate[mask]
    result[name] = {
        "concepts": int(mask.sum()),
        "rate_quantiles_10_50_90": np.quantile(r, [0.1, 0.5, 0.9]).round(4).tolist(),
        # Expected firing docs in one 20% subset is 0.2 * N * rate; share of concepts reaching k
        "share_with_k_docs_per_subset": {
            f"k={k}": {f"N={n}": round(float((config.VAL_FRACTION * n * r >= k).mean()), 3) for n in config.CANDIDATE_N}
            for k in config.CANDIDATE_K
        },
    }

(config.RESULTS / f"{args.run}_firing_rates.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
