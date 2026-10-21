"""Data for the Space tab "Rollouts" (design.md G10, G12): one frame for the whole doc and one per token window.

Usage: python s05_space.py --run full
Reads DATA/<run>/distribution.parquet and results/<run>_distribution_summary.json (from s03) and Exp 1's names.
Writes ../space/data/rollouts.json (gitignored, as Exp 1's T7).
"""
import argparse
import json

import settings  # first: puts Exp 1 on the path
import numpy as np
import pandas as pd

OUT = settings.RESULTS.parent.parent / "space" / "data" / "rollouts.json"
NAMES = settings.EXP1_RUN / "labels" / "faith" / "names.json"
STEP = 512  # ranks per band bin, as in figures/make_rollout_figure.py


def r4(x):
    return None if x is None or not np.isfinite(x) else float(f"{x:.4g}")


def band(values):
    """10th, 50th and 90th percentile of the positive values in each bin of STEP consecutive ranks."""
    out = {"lo": [], "mid": [], "hi": []}
    for v in np.array_split(values, int(np.ceil(len(values) / STEP))):
        v = v[v > 0]
        p = np.percentile(v, [10, 50, 90]) if len(v) else [np.nan] * 3
        for k, x in zip(out, p):
            out[k].append(r4(x))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, choices=["pilot", "full"])
    args = parser.parse_args()
    table = pd.read_parquet(settings.DATA / args.run / "distribution.parquet").sort_values("chi_train", ascending=False)
    table["rank"] = np.arange(1, len(table) + 1)
    summary = json.loads((settings.RESULTS / f"{args.run}_distribution_summary.json").read_text())
    sets = ["V"] + [g for g in settings.GENERATORS if f"chi_{g}" in table]

    edges = np.array(summary["bin_edges_log_chi_train"])
    centers = np.exp((edges[:-1] + edges[1:]) / 2)
    bin_rank = np.searchsorted(-table["chi_train"].to_numpy(), -centers).tolist()

    scopes = [("doc", "whole document", "")] + [(str(w), f"tokens {a}-{b}", f"_w{w}") for w, (a, b) in enumerate(settings.WINDOWS)]
    frames = []
    for key, label, suffix in scopes:
        frame = {"key": key, "label": label, "docs": summary["docs_per_scope"][key], "sets": {}}
        for s in sets:
            entry = summary["sets"][s] if key == "doc" else summary["sets"][s]["windows"][int(key)]
            frame["sets"][s] = {**band(table[f"chi_{s}{suffix}"].to_numpy()),
                                "ratio": entry["binned_median_log_ratio"], "slope": entry["slope_chi"]}
        frames.append(frame)

    names = json.loads(NAMES.read_text())
    named = []
    for c, v in names.items():
        row = table.loc[table["concept"] == int(c)].iloc[0]
        named.append({"c": int(c), "rank": int(row["rank"]), "train": r4(row["chi_train"]), "name": v["dolma"].split(". ")[0][:140],
                      "chi": {key: {s: r4(row[f"chi_{s}{suffix}"]) for s in sets} for key, _, suffix in scopes}})

    keep = np.unique(np.concatenate([np.arange(0, len(table), 64), [len(table) - 1]]))  # train curve, thinned
    data = {"run": args.run, "sets": sets, "frames": frames, "bin_rank": bin_rank,
            "band_rank": (np.arange(len(frames[0]["sets"]["V"]["mid"])) * STEP + STEP // 2).tolist(),
            "train": {"rank": table["rank"].to_numpy()[keep].tolist(),
                      "chi": [r4(x) for x in table["chi_train"].to_numpy()[keep]]},
            "delta": summary.get("delta_vs_V", {}), "named": named}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False))
    print(OUT, f"{OUT.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
