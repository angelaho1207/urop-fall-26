"""Build the Space data for the names section of the rollouts tab (design.md G76). CPU, seconds.

Usage: python s23_space_named.py
Reads only committed results files; recomputes nothing. Writes space/data/exp2_named.json (tables, check entries, counts) and
space/data/exp2_named_lists.json (all list entries with names, firing docs and noise figures). Names, ids and numbers only.
"""
import json
import re
from pathlib import Path

import settings

R = settings.RESULTS
SPACE = Path(__file__).resolve().parent.parent / "space" / "data"
MODELS = ["stage1", "main", "sft", "dpo", "instruct"]
NEAR_CUT = 63  # 50 / 0.8: below this, dropping 20% of docs usually takes a concept under the 50-doc filter
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I)
COST_KEY = re.compile(r"usd|spent|price|limit_", re.I)


def read(name):
    return json.loads((R / f"full_post_named_{name}.json").read_text())


def cost_keys(value, path=""):
    if isinstance(value, dict):
        return [f"{path}/{k}" for k in value if COST_KEY.search(k)] + [hit for k, v in value.items() for hit in cost_keys(v, f"{path}/{k}")]
    if isinstance(value, list):
        return [hit for v in value for hit in cost_keys(v, path)]
    return []


def main():
    summary, names, sel, noise = read("summary"), read("names"), read("selection_summary"), read("noise_summary")
    if summary["stopped"] is not None or len(summary["pairs"]) != 200:
        raise SystemExit("G76: expected a finished run with 200 check entries")

    extra = {(g, c["concept"], c["list"], c["class"]): c for g, m in noise["models"].items() for c in m["selected_concepts"]}
    rows = []
    for g in MODELS:
        for list_name, sides in names[g].items():
            for side, entries in sides.items():
                for x in entries:
                    n = extra[(g, x["concept"], list_name, side)]
                    rows.append({"model": g, "list": list_name, "class": side, "concept": x["concept"], "r": x["r"], "class_noflag": x["class_noflag"], "chi_train": round(x["chi_train"], 5), "chi_rollout": round(x["chi_model"], 5),
                                 "missing": x["missing_from_rollouts"], "n_T1": x["n_T1"], "n_V": x["n_V"], "train_docs": x["n_fire_train"], "rollout_docs": x["n_fire_model"], "name": x["name"], "source": x["source"],
                                 "in_check": x["in_check"], "r_sd": n["r_sd"], "r_lo": n["r_p2_5"], "r_hi": n["r_p97_5"], "stay_class": n["share_stays_in_class"], "stay_list": n["share_stays_in_list"]})
    if len(rows) != sel["entries"]:
        raise SystemExit(f"G76: {len(rows)} rows against {sel['entries']} entries")

    # G76: stability of the filtered under lists by rollout docs; the rerun keeps the 50-doc cut while docs shrink by 20%
    under = [r for r in rows if r["list"] == "extreme_filtered" and r["class"] == "under"]
    near = [r["stay_list"] for r in under if r["rollout_docs"] < NEAR_CUT]
    above = [r["stay_list"] for r in under if r["rollout_docs"] >= NEAR_CUT]
    filter_effect = {"near_cut_docs": NEAR_CUT, "entries": len(under), "near": len(near), "near_mean_stay": round(sum(near) / len(near), 3), "above": len(above), "above_mean_stay": round(sum(above) / len(above), 3)}
    texts = [r["name"] for r in rows] + [p["dolma_name"] for p in summary["pairs"]] + [p["rollout_name"] for p in summary["pairs"]]
    found = sorted({m for t in texts if t for m in EMAIL.findall(t)})
    out = {"run": "full_post", "sources": [f"results/full_post_named_{k}.json" for k in ("summary", "names", "selection_summary", "noise_summary")],
           "counts": summary["counts"], "tables": summary["tables"], "pairs": summary["pairs"],
           "noflag": summary["noflag_class_of_random_draws"], "selection": {k: v for k, v in sel.items() if k != "seconds"},
           "noise": {"reruns": noise["reruns"], "drop": noise["drop"], "train_docs": noise["train_docs"], "matched_docs": noise["matched_docs"], "filter_effect": filter_effect,
                     "models": {g: {k: m[k] for k in ("classes", "extreme_lists")} for g, m in noise["models"].items()}}}
    dollars = cost_keys(out)  # G83: no cost figure leaves for the public Space
    if dollars:
        raise SystemExit(f"G83: cost fields in the page data: {dollars}")
    (SPACE / "exp2_named.json").write_text(json.dumps(out, ensure_ascii=False))
    (SPACE / "exp2_named_lists.json").write_text(json.dumps(rows, ensure_ascii=False))
    print("rows", len(rows), "email-like strings in names:", found, "bytes", (SPACE / "exp2_named.json").stat().st_size, (SPACE / "exp2_named_lists.json").stat().st_size)


if __name__ == "__main__":
    main()
