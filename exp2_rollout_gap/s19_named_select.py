"""Concepts to name per model, the check draw, and every window the labels job needs (design.md G70, G71). CPU only.

Usage: python s19_named_select.py
Reads DATA/full_post/distribution.parquet, DATA/full_post_noflag/distribution.parquet, exp1/full/firing_counts.parquet,
notes/name_cache.json, the G62 draws (named/concepts_g69.json, copied once from concepts.json) and the acts and texts.
Writes DATA/full_post/named/concepts.json, t1_concepts.json (read by s06's spec exp2_named), train_examples/,
rollout_examples/, quiz_windows/ (pool: windows hold text, G20) and results/full_post_named_selection_summary.json
(ids and counts only).
"""
import json
import shutil
import time

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np
import pandas as pd
from transformers import AutoTokenizer

import name_cache
from s05_coverage import MISSING  # Exp 1: e^-5
from s06_examples import WINDOW  # Exp 1 E1
from s12_moved_windows import D_SAE, SETS, build_side, build_v_quiz, firing_counts, token_ids

CLASSES = ["over", "under", "middle"]  # F3's order
GROUPS = {"base": ["stage1", "main"], "instruct": ["sft", "dpo", "instruct"]}  # Angela
N_PER_CLASS, N_EXTREME, MIN_FILTER_DOCS = 80, 50, 50  # G70
N_RESERVE = 10  # G71
CELLS = [("random", "over", 20), ("random", "under", 20), ("random", "middle", 20),
         ("extreme", "over", 20), ("extreme", "under_unfiltered", 10), ("extreme", "under_filtered", 10)]  # G71
OLD_MIN_T1, OLD_MIN_V = 40, 50  # G62's pool, used only to keep its purchased names (G70)
RUN = "full_post"
OUT = settings.DATA / RUN / "named"


def table_of(run):
    columns = ["concept", "chi_train", "in_slope"] + [f"chi_{g}" for g in SETS] + (["n_fire_train"] if run == RUN else [])
    table = pd.read_parquet(settings.DATA / run / "distribution.parquet", columns=columns)
    if not (table["concept"].to_numpy() == np.arange(D_SAE)).all():
        raise SystemExit(f"{run}: rows are not in concept order")
    return table


def classify(chi_train, chi):
    """G70: r over the concepts with chi_train >= e^-5, then the lowest and highest 10% by rank (ties by concept id).
    Returns r (nan where missing), class ("" where missing) and the concepts in rank order."""
    keep = np.flatnonzero(chi_train >= MISSING)
    r = np.full(D_SAE, np.nan)
    with np.errstate(divide="ignore"):
        r[keep] = np.log(chi[keep] / chi_train[keep])  # chi = 0 gives -inf, the lowest rank
    order = keep[np.argsort(r[keep], kind="stable")]
    k = len(keep) // 10
    cls = np.full(D_SAE, "", dtype=object)
    cls[order[:k]], cls[order[k:-k]], cls[order[-k:]] = "under", "middle", "over"
    return r, cls, order


def extremes(order, fire_train, fire_model):
    """G70: the four extreme lists; order is the rank order from classify."""
    passing = order[(fire_train[order] >= MIN_FILTER_DOCS) & (fire_model[order] >= MIN_FILTER_DOCS)]
    return {("extreme_unfiltered", "over"): order[-N_EXTREME:], ("extreme_unfiltered", "under"): order[:N_EXTREME],
            ("extreme_filtered", "over"): passing[-N_EXTREME:], ("extreme_filtered", "under"): passing[:N_EXTREME]}


def old_class(table, g):
    """G62's rule, only to know the pool its draws came from."""
    slope = np.flatnonzero(table["in_slope"].to_numpy())
    with np.errstate(divide="ignore"):
        r = np.log(table[f"chi_{g}"].to_numpy()[slope] / table["chi_train"].to_numpy()[slope])
    order = slope[np.argsort(r, kind="stable")]
    k = len(slope) // 10
    cls = np.full(D_SAE, "", dtype=object)
    cls[order[:k]], cls[order[k:-k]], cls[order[-k:]] = "under", "middle", "over"
    return cls


def random_draw(members, pool, old_draws, seed):
    """G70: a uniform 80-subset of members that keeps G62's draws where the statistics allow it. pool = members in G62's
    pool; old_draws = uniform draws from that pool (those still in the class). Returns the draw and how many were kept."""
    rng = np.random.default_rng(seed)
    rest = np.setdiff1d(members, pool)
    m = int(rng.hypergeometric(len(pool), len(rest), N_PER_CLASS))
    if m <= len(old_draws):
        inside, kept = rng.choice(old_draws, size=m, replace=False), m
    else:
        top_up = rng.choice(np.setdiff1d(pool, old_draws), size=m - len(old_draws), replace=False)
        inside, kept = np.concatenate([old_draws, top_up]), len(old_draws)
    return np.sort(np.concatenate([inside, rng.choice(rest, size=N_PER_CLASS - m, replace=False)])), kept


def finite(x):
    return None if not np.isfinite(x) else round(float(x), 4)


def quantiles(x):
    return np.percentile(x, [10, 50, 90]).round(1).tolist() if len(x) else None


def windows_of(items, keys, ids_of, text_of):
    return [{"doc_id": str(keys[it["doc"]][2]), "start": it["start"], "group": it["group"], "max": round(it["max"], 4),
             "ids": [int(i) for i in ids_of[it["doc"]][it["start"]:it["start"] + WINDOW]],
             "texts": [text_of(int(i)) for i in ids_of[it["doc"]][it["start"]:it["start"] + WINDOW]],
             "acts": [round(float(a), 4) for a in it["acts"]]} for it in items]


def main():
    t0 = time.time()
    if not (OUT / "concepts_g69.json").exists():
        shutil.copy(OUT / "concepts.json", OUT / "concepts_g69.json")  # the purchased draws; a rerun must not lose them
    old_rows = json.loads((OUT / "concepts_g69.json").read_text())["rows"]
    table, noflag = table_of(RUN), table_of(f"{RUN}_noflag")
    chi_train, fire_train = table["chi_train"].to_numpy(), table["n_fire_train"].to_numpy()
    fires = pd.read_parquet(config.DATA / "full" / "firing_counts.parquet", columns=["n_T1", "n_V"])
    n_t1, n_v = fires["n_T1"].to_numpy(), fires["n_V"].to_numpy()
    old_testable = (n_t1 >= OLD_MIN_T1) & (n_v >= OLD_MIN_V)
    n_fire = {g: firing_counts(g) for g in SETS}
    print("firing counts done", round(time.time() - t0), flush=True)

    rows, by_model = [], {}
    for i, g in enumerate(SETS):
        chi = table[f"chi_{g}"].to_numpy()
        r, cls, order = classify(chi_train, chi)
        r_nf, cls_nf, _ = classify(noflag["chi_train"].to_numpy(), noflag[f"chi_{g}"].to_numpy())
        was = old_class(table, g)
        info = {"ranked_concepts": int(len(order)), "missing_chi_train": int(D_SAE - len(order)), "class_size": int(len(order) // 10),
                "chi_zero_ranked": int((chi[order] == 0).sum()), "missing_from_rollouts_ranked": int((chi[order] < MISSING).sum()),
                "pass_filter": int(((fire_train[order] >= MIN_FILTER_DOCS) & (n_fire[g][order] >= MIN_FILTER_DOCS)).sum()), "kept_g62_draws": {}, "lists": {}}

        def row(c, list_name, side):
            return {"concept": int(c), "model": g, "list": list_name, "class": side, "class_rank": cls[c], "r": finite(r[c]), "class_noflag": cls_nf[c], "r_noflag": finite(r_nf[c]),
                    "chi_train": float(chi_train[c]), "chi_model": float(chi[c]), "missing_from_rollouts": bool(chi[c] < MISSING), "n_T1": int(n_t1[c]), "n_V": int(n_v[c]),
                    "n_fire_train": int(fire_train[c]), "n_fire_model": int(n_fire[g][c])}

        for j, c_name in enumerate(CLASSES):
            members = np.flatnonzero(cls == c_name)
            pool = np.flatnonzero((cls == c_name) & (was == c_name) & old_testable)
            drawn_old = np.array([x["concept"] for x in old_rows if x["model"] == g and x["class"] == c_name])
            if not np.isin(drawn_old, np.flatnonzero((was == c_name) & old_testable)).all():
                raise SystemExit(f"{g} {c_name}: a G62 draw lies outside G62's pool")
            pick, kept = random_draw(members, pool, np.intersect1d(drawn_old, pool), [config.SEED, 70, i, j])
            info["kept_g62_draws"][c_name] = kept
            rows += [row(c, "random", c_name) for c in pick]
        for (list_name, side), cs in extremes(order, fire_train, n_fire[g]).items():
            if len(cs) < N_EXTREME:
                raise SystemExit(f"{g} {list_name} {side}: only {len(cs)} concepts")
            rows += [row(c, list_name, side) for c in cs]
            info["lists"][f"{list_name}_{side}"] = {"median_train_docs": float(np.median(fire_train[cs])), "median_rollout_docs": float(np.median(n_fire[g][cs])),
                                                    "zero_rollout_docs": int((n_fire[g][cs] == 0).sum()), "outside_side_by_rank": int((cls[cs] != side).sum())}
        by_model[g] = info
        print(g, json.dumps(info), flush=True)

    # G70: what the cache already holds from earlier runs; this run's own names (G62-G69) are new names, never re-sent by s20
    cache = {c: [e for e in v if not e["source"].startswith("exp2 named")] for c, v in name_cache.load().items()}
    distinct = sorted({x["concept"] for x in rows})
    reused = {c: name_cache.dolma(cache, c) for c in distinct if name_cache.dolma(cache, c)}
    new = [c for c in distinct if c not in reused]
    new_set = set(new)
    train_named = [c for c in new if n_t1[c] < OLD_MIN_T1]  # G70: the 40 windows of E2 need 40 T1 firing docs
    t1_missing = [c for c in new if n_t1[c] >= OLD_MIN_T1 and not (config.DATA / "full" / "examples_named" / f"{c}.json").exists()]

    # G71: ordered candidates per (group, cell); s20 keeps the first n with a returned name
    cells = []
    for gi, (group, models) in enumerate(GROUPS.items()):
        for ci, (kind, c_name, n) in enumerate(CELLS):
            lists = {"random": ["random"], "extreme": ["extreme_unfiltered", "extreme_filtered"]}[kind]
            if c_name.startswith("under_"):
                lists = [f"extreme_{c_name.split('_')[1]}"]
            side = c_name.split("_")[0]
            mine = [x for x in rows if x["model"] in models and x["list"] in lists and x["class"] == side and x["concept"] in new_set]
            eligible = {}
            for x in mine:
                if x["model"] not in eligible.setdefault(x["concept"], []):
                    eligible[x["concept"]].append(x["model"])
            ids = sorted(eligible)
            ordered = []
            for k in np.random.default_rng([config.SEED, 71, gi, ci]).permutation(len(ids))[:n + N_RESERVE]:
                c = ids[k]
                ordered.append({"concept": c, "model": str(np.random.default_rng([config.SEED, 71, gi, ci, c]).choice(eligible[c]))})
            if len(ids) < n:
                raise SystemExit(f"{group} {kind} {c_name}: only {len(ids)} eligible")
            cells.append({"group": group, "kind": kind, "class": c_name, "n": n, "eligible": len(ids), "order": ordered})
            print(group, kind, c_name, "eligible", len(ids), flush=True)

    for sub in ("train_examples", "rollout_examples", "quiz_windows"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    (OUT / "t1_concepts.json").write_text(json.dumps(t1_missing))
    (OUT / "concepts.json").write_text(json.dumps({"rows": rows, "new": new, "train_named": train_named, "reused": {str(c): e for c, e in reused.items()}, "cells": cells}, indent=0))

    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    piece = {}

    def text_of(i):
        if i not in piece:
            piece[i] = tokenizer.decode([i])
        return piece[i]

    def naming_files(side, cs, folder, name_of):
        """Naming windows of one side (G48, G69, G70): 40 by rank group, every firing doc if fewer, None if there is none."""
        plan, keys, doc_len = build_side(side, cs, naming_only=True)
        used = sorted({it["doc"] for c in cs if plan[c]["naming"] for it in plan[c]["naming"]})
        ids_of = token_ids(side, keys, doc_len, used, tokenizer)
        for c in cs:
            items = plan[c]["naming"]
            ex = {"concept": c, "set": side, "n_firing": {"rollout": plan[c]["n_firing"]}, "max_by_subset": {"rollout": plan[c]["max"]},
                  "naming": {"rollout": windows_of(items, keys, ids_of, text_of) if items else None}}
            (OUT / folder / name_of(c)).write_text(json.dumps(ex, ensure_ascii=False))
        print(side, len(cs), "naming windows", round(time.time() - t0), flush=True)
        return {c: plan[c]["n_firing"] for c in cs}

    train_docs = naming_files("train", train_named, "train_examples", lambda c: f"{c}.json") if train_named else {}
    rollout_docs = {}
    for g in SETS:
        cs = sorted({e["concept"] for cell in cells for e in cell["order"] if e["model"] == g})
        if cs:
            rollout_docs[g] = naming_files(g, cs, "rollout_examples", lambda c, g=g: f"{g}_{c}.json")

    candidates = sorted({e["concept"] for cell in cells for e in cell["order"]})
    plan, keys, doc_len = build_v_quiz(candidates)
    used = sorted({it["doc"] for c in candidates for p in ("quiz_firing", "quiz_nonfiring") if plan[c][p] for it in plan[c][p]})
    ids_of = token_ids("V", keys, doc_len, used, tokenizer)
    for c in candidates:
        ex = {"concept": c, "set": "V", "n_firing": {"V": plan[c]["n_firing"]}, "max_by_subset": {"V": plan[c]["max"]},
              "quiz_firing": {"V": windows_of(plan[c]["quiz_firing"], keys, ids_of, text_of) if plan[c]["quiz_firing"] else None},
              "quiz_nonfiring": {"V": windows_of(plan[c]["quiz_nonfiring"], keys, ids_of, text_of) if plan[c]["quiz_nonfiring"] else None}}
        (OUT / "quiz_windows" / f"{c}.json").write_text(json.dumps(ex, ensure_ascii=False))
    print("V quiz windows", len(candidates), round(time.time() - t0), flush=True)

    sources = {}
    for e in reused.values():
        sources[f"{e['source']}, {e['windows']}"] = sources.get(f"{e['source']}, {e['windows']}", 0) + 1
    v_firing = [plan[c]["n_firing"] for c in candidates]
    train_counts = list(train_docs.values())
    summary = {"by_model": by_model, "entries": len(rows), "distinct_concepts": len(distinct), "new_names_in_this_run": len(new), "reused_names": len(reused),
               "reused_by_source": sources, "new_from_t1": len(new) - len(train_named), "new_from_train": len(train_named),
               "train_docs_named_under_40": sum(n < 40 for n in train_counts), "train_docs_quantiles_10_50_90": quantiles(train_counts),
               "t1_windows_to_build": len(t1_missing), "selected_by_n_models": {str(n): int(v) for n, v in zip(*np.unique(np.unique([x["concept"] for x in rows], return_counts=True)[1], return_counts=True))},
               "check_eligible": {f"{c['group']}_{c['kind']}_{c['class']}": c["eligible"] for c in cells},
               "check_candidates": len(candidates), "candidates_v_firing_under_30": sum(n < 30 for n in v_firing), "candidates_v_firing_zero": sum(n == 0 for n in v_firing),
               "candidates_no_nonfiring": sum(plan[c]["quiz_nonfiring"] is None for c in candidates),
               "candidates_rollout_zero": {g: sum(n == 0 for n in d.values()) for g, d in rollout_docs.items()},
               "candidates_rollout_under_40": {g: sum(n < 40 for n in d.values()) for g, d in rollout_docs.items()}, "seconds": round(time.time() - t0)}
    (settings.RESULTS / f"{RUN}_named_selection_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
