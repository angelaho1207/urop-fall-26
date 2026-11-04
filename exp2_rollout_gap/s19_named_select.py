"""Concepts to name per model and class, the check draw, and the check's rollout windows (design.md G62-G64). CPU only.

Usage: python s19_named_select.py
Reads DATA/full_post/distribution.parquet, DATA/full_post_noflag/distribution.parquet, exp1/full/firing_counts.parquet,
notes/name_cache.json and the full_post acts and rollouts.
Writes DATA/full_post/named/concepts.json, t1_concepts.json (read by s06's spec exp2_named), rollout_examples/ (pool:
windows hold text, G20) and results/full_post_named_selection_summary.json (ids and counts only).
"""
import json
import time

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np
import pandas as pd
from transformers import AutoTokenizer

import name_cache
from s06_examples import N_NAMING, WINDOW  # Exp 1 E1, E2
from s12_moved_windows import D_SAE, SETS, build_side, firing_counts, token_ids

CLASSES = ["over", "under", "middle"]  # F3's order
GROUPS = {"base": ["stage1", "main"], "instruct": ["sft", "dpo", "instruct"]}  # Angela
N_PER_CLASS, MIN_T1, MIN_V = 80, 40, 50  # G62; F2
N_CHECK, N_RESERVE = 20, 10  # G64
RUN = "full_post"
OUT = settings.DATA / RUN / "named"


def table_of(run):
    columns = ["concept", "chi_train", "in_slope"] + [f"chi_{g}" for g in SETS]
    table = pd.read_parquet(settings.DATA / run / "distribution.parquet", columns=columns)
    if not (table["concept"].to_numpy() == np.arange(D_SAE)).all():
        raise SystemExit(f"{run}: rows are not in concept order")
    return table


def classify(table, g):
    """G62: r over the slope concepts, then the lowest and highest 10% by rank (ties by concept id)."""
    chi_train, chi = table["chi_train"].to_numpy(), table[f"chi_{g}"].to_numpy()
    slope = np.flatnonzero(table["in_slope"].to_numpy())
    r = np.full(D_SAE, np.nan)
    with np.errstate(divide="ignore"):
        r[slope] = np.log(chi[slope] / chi_train[slope])  # chi = 0 gives -inf, the lowest rank
    order = slope[np.argsort(r[slope], kind="stable")]
    k = len(slope) // 10
    cls = np.full(D_SAE, "", dtype=object)
    cls[order[:k]], cls[order[k:-k]], cls[order[-k:]] = "under", "middle", "over"
    return r, cls, {"slope_concepts": int(len(slope)), "class_size": int(k), "chi_zero": int((chi[slope] == 0).sum())}


def finite(x):
    return None if not np.isfinite(x) else round(float(x), 4)


def main():
    t0 = time.time()
    table, noflag = table_of(RUN), table_of(f"{RUN}_noflag")
    if not (table["in_slope"].to_numpy() == noflag["in_slope"].to_numpy()).all():
        raise SystemExit("slope concepts differ between full_post and noflag")
    fires = pd.read_parquet(config.DATA / "full" / "firing_counts.parquet", columns=["n_T1", "n_V"])
    testable = (fires["n_T1"].to_numpy() >= MIN_T1) & (fires["n_V"].to_numpy() >= MIN_V)
    n_fire = {g: firing_counts(g) for g in SETS}
    print("firing counts done", round(time.time() - t0), flush=True)

    # G62: the draw per model and class
    rows, by_model = [], {}
    for i, g in enumerate(SETS):
        r, cls, info = classify(table, g)
        r_nf, cls_nf, info_nf = classify(noflag, g)
        by_model[g] = {**info, "chi_zero_noflag": info_nf["chi_zero"], "testable": {}, "same_class_noflag": {}}
        for j, c_name in enumerate(CLASSES):
            pool = np.flatnonzero((cls == c_name) & testable)
            by_model[g]["testable"][c_name] = int(len(pool))
            if len(pool) < N_PER_CLASS:
                raise SystemExit(f"{g} {c_name}: only {len(pool)} testable concepts")
            pick = np.sort(np.random.default_rng([config.SEED, 62, i, j]).choice(pool, size=N_PER_CLASS, replace=False))
            by_model[g]["same_class_noflag"][c_name] = int((cls_nf[pick] == c_name).sum())
            rows += [{"concept": int(c), "model": g, "class": c_name, "r": finite(r[c]), "class_noflag": cls_nf[c], "r_noflag": finite(r_nf[c]),
                      "chi_train": float(table.at[c, "chi_train"]), "chi_model": float(table.at[c, f"chi_{g}"]),
                      "n_T1": int(fires.at[c, "n_T1"]), "n_V": int(fires.at[c, "n_V"]), "n_fire_model": int(n_fire[g][c])} for c in pick]

    # G63: what the cache already holds
    cache = name_cache.load()
    distinct = sorted({row["concept"] for row in rows})
    reused = {c: name_cache.dolma(cache, c) for c in distinct if name_cache.dolma(cache, c)}
    new = [c for c in distinct if c not in reused]
    new_set = set(new)

    # G64: ordered candidates per (group, class); the first 20 with a returned T1 name are fixed later by s20
    cells, excluded = [], {}
    for gi, (group, models) in enumerate(GROUPS.items()):
        for ci, c_name in enumerate(CLASSES):
            mine = [row for row in rows if row["model"] in models and row["class"] == c_name and row["concept"] in new_set]
            eligible = {}
            for row in mine:
                if row["n_fire_model"] >= N_NAMING:
                    eligible.setdefault(row["concept"], []).append(row["model"])
            excluded[f"{group}_{c_name}"] = len({row["concept"] for row in mine} - set(eligible))
            ids = sorted(eligible)
            order = np.random.default_rng([config.SEED, 64, gi, ci]).permutation(len(ids))
            ordered = []
            for k in order[:N_CHECK + N_RESERVE]:
                c = ids[k]
                model = str(np.random.default_rng([config.SEED, 64, gi, ci, c]).choice(eligible[c]))
                ordered.append({"concept": c, "model": model})
            cells.append({"group": group, "class": c_name, "group_index": gi, "class_index": ci, "eligible": len(ids), "order": ordered})
            print(group, c_name, "eligible", len(ids), flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "rollout_examples").mkdir(exist_ok=True)
    (OUT / "t1_concepts.json").write_text(json.dumps(new))
    (OUT / "concepts.json").write_text(json.dumps({"rows": rows, "new_t1": new, "reused": {str(c): e for c, e in reused.items()}, "cells": cells}, indent=0))

    # G64: rollout naming windows of the check candidates
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    piece = {}

    def text_of(i):
        if i not in piece:
            piece[i] = tokenizer.decode([i])
        return piece[i]

    for g in SETS:
        cs = sorted({e["concept"] for cell in cells for e in cell["order"] if e["model"] == g})
        if not cs:
            continue
        plan, keys, doc_len = build_side(g, cs, naming_only=True)
        used = sorted({it["doc"] for c in cs for it in plan[c]["naming"]})
        ids_of = token_ids(g, keys, doc_len, used, tokenizer)
        for c in cs:
            windows = [{"doc_id": str(keys[it["doc"]][2]), "start": it["start"], "group": it["group"], "max": round(it["max"], 4),
                        "ids": [int(i) for i in ids_of[it["doc"]][it["start"]:it["start"] + WINDOW]],
                        "texts": [text_of(int(i)) for i in ids_of[it["doc"]][it["start"]:it["start"] + WINDOW]],
                        "acts": [round(float(a), 4) for a in it["acts"]]} for it in plan[c]["naming"]]
            ex = {"concept": c, "set": g, "n_firing": {"rollout": plan[c]["n_firing"]}, "max_by_subset": {"rollout": plan[c]["max"]}, "naming": {"rollout": windows}}
            (OUT / "rollout_examples" / f"{g}_{c}.json").write_text(json.dumps(ex, ensure_ascii=False))
        print(g, len(cs), "rollout windows", round(time.time() - t0), flush=True)

    sources = {}
    for e in reused.values():
        sources[f"{e['source']}, {e['windows']}"] = sources.get(f"{e['source']}, {e['windows']}", 0) + 1
    summary = {"by_model": by_model, "entries": len(rows), "distinct_concepts": len(distinct), "new_t1_names": len(new), "reused_names": len(reused),
               "reused_by_source": sources, "selected_by_n_models": {str(n): int(v) for n, v in zip(*np.unique(np.unique([row["concept"] for row in rows], return_counts=True)[1], return_counts=True))},
               "check_excluded_under_40_rollout_docs": excluded, "check_eligible": {f"{c['group']}_{c['class']}": c["eligible"] for c in cells},
               "seconds": round(time.time() - t0)}
    (settings.RESULTS / f"{RUN}_named_selection_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
