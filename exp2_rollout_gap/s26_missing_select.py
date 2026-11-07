"""Missing concepts per model: lists, baseline counts, naming windows and the garbled measure (design.md G87-G92). CPU only.

Usage: python s26_missing_select.py
Reads DATA/full_post/distribution.parquet, the acts and rollouts of each model, Exp 1's docs and acts, notes/name_cache.json
and the G56 threshold. Writes DATA/full_post/missing/concepts.json and its naming windows (pool: windows hold text, G20)
and results/full_post_missing_selection_summary.json (ids and counts only).
"""
import json
import time

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np
import pandas as pd
from transformers import AutoTokenizer

import diag_common as dc
import missing_lists as ml
import name_cache
from s03_distribution import choose
from s05_coverage import MISSING  # Exp 1: e^-5
from s12_moved_windows import D_SAE, SETS, build_side, firing_counts, token_ids
from s15_garbled import read_nll
from s19_named_select import finite, windows_of

RUN = "full_post"
OUT = settings.DATA / RUN / "missing"
R = settings.RESULTS
SEED_ROW = 88  # G88


def rollout_entry(cache, c):
    """G90: any rollout name of the concept is the same kind of text, whichever model it came from."""
    return next((e for e in cache.get(str(c), []) if e["text"] == "rollout"), None)


def garbled_measure(rows):
    """G92: per model, each list B concept's share of its summed means from flagged docs, at the matched docs."""
    threshold = json.loads((R / f"{RUN}_garbled_threshold.json").read_text())["threshold_nats"]
    paths, all_lengths = dc.set_lengths()
    chosen, _ = choose(all_lengths)
    table = pd.read_parquet(settings.DATA / RUN / "distribution.parquet")
    out = {}
    for g in SETS:
        means, ids, _ = dc.read_means(paths[g], chosen[g]["doc"])
        dc.check_chi(g, means, table)  # G39: these are the docs behind the published chi
        nll = read_nll(g).reindex(ids)["nll_mean"].to_numpy()
        flagged = np.nan_to_num(nll, nan=-np.inf) > threshold
        total = np.asarray(means.sum(0)).ravel()
        share = ml.garbled_share(np.asarray(means[flagged].sum(0)).ravel(), total)
        out[g] = {"docs": int(len(ids)), "docs_flagged": int(flagged.sum()), "share_docs_flagged": round(float(flagged.mean()), 4),
                  "docs_without_nll": int(np.isnan(nll).sum()), "all_firing_concepts": ml.share_quantiles(share)}
        for name in ("random", "extreme_unfiltered", "extreme_filtered"):
            mine = [x for x in rows if x["model"] == g and x["direction"] == ml.DIRECTIONS[1] and x["list"] == name]
            for x in mine:
                x["garbled_share"] = finite(share[x["concept"]])
            out[g][name] = ml.share_quantiles([share[x["concept"]] for x in mine])
        print(g, "garbled measure", json.dumps(out[g]), flush=True)
    return out


def main():
    t0 = time.time()
    if abs(MISSING - ml.EPSILON) > 1e-12:
        raise SystemExit("G87: cutoff differs from Exp 1")
    table = pd.read_parquet(settings.DATA / RUN / "distribution.parquet")
    if not (table["concept"].to_numpy() == np.arange(D_SAE)).all():
        raise SystemExit("rows are not in concept order")
    chi_train, chi_v, fire_train = (table[k].to_numpy() for k in ("chi_train", "chi_V", "n_fire_train"))
    n_fire = {g: firing_counts(g) for g in SETS}
    print("firing counts done", round(time.time() - t0), flush=True)

    rows, by_model = [], {}
    for i, g in enumerate(SETS):
        chi = table[f"chi_{g}"].to_numpy()
        by_model[g] = {}
        for j, direction in enumerate(ml.DIRECTIONS):
            present = fire_train if j == 0 else n_fire[g]
            lists, members, r = ml.choose_lists(direction, chi_train, chi, present, [config.SEED, SEED_ROW, i, j])
            agrees = ml.v_agrees(direction, chi_v)
            by_model[g][direction] = {
                "members": int(len(members)), "share_of_dictionary": round(len(members) / D_SAE, 4), "v_baseline_members": int(len(ml.members_of(direction, chi_train, chi_v))),
                "members_v_agrees": int(agrees[members].sum()), "members_chi_rollout_zero": int((chi[members] == 0).sum()), "members_pass_present_filter": int((present[members] >= ml.MIN_PRESENT_DOCS).sum()),
                "list_sizes": {k: int(len(v)) for k, v in lists.items()},
                "median_firing_docs_present_side": {k: (float(np.median(present[v])) if len(v) else None) for k, v in lists.items()}}
            for name, cs in lists.items():
                rows += [{"concept": int(c), "model": g, "direction": direction, "list": name, "r": finite(r[c]), "chi_train": float(chi_train[c]), "chi_rollout": float(chi[c]), "chi_V": float(chi_v[c]),
                          "n_fire_train": int(fire_train[c]), "n_fire_rollout": int(n_fire[g][c]), "passes_present_filter": bool(present[c] >= ml.MIN_PRESENT_DOCS), "v_agrees": bool(agrees[c])} for c in cs]
        print(g, json.dumps(by_model[g]), flush=True)

    # G90: one name per concept and kind of text; a concept is in list A or list B, never both, since chi_train decides
    cache = name_cache.load()
    side_of = {x["concept"]: x["direction"] for x in rows}
    a_concepts = sorted(c for c, d in side_of.items() if d == ml.DIRECTIONS[0])
    b_concepts = sorted(c for c, d in side_of.items() if d == ml.DIRECTIONS[1])
    reused = {c: name_cache.dolma(cache, c) for c in a_concepts if name_cache.dolma(cache, c)}
    reused.update({c: rollout_entry(cache, c) for c in b_concepts if rollout_entry(cache, c)})
    new_dolma = [c for c in a_concepts if c not in reused]
    new_rollout = {}
    for c in b_concepts:
        if c not in reused:
            models = sorted({x["model"] for x in rows if x["concept"] == c}, key=SETS.index)
            new_rollout[c] = max(models, key=lambda g: n_fire[g][c])  # first model wins a tie

    for sub in ("train_examples", "rollout_examples"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    garbled = garbled_measure(rows)
    (OUT / "concepts.json").write_text(json.dumps({"rows": rows, "new_dolma": new_dolma, "new_rollout": {str(c): m for c, m in new_rollout.items()}, "reused": {str(c): e for c, e in reused.items()}}, indent=0))

    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    piece = {}

    def text_of(i):
        if i not in piece:
            piece[i] = tokenizer.decode([i])
        return piece[i]

    def naming_files(side, cs, folder):
        """G69, G70: 40 windows by rank group, every firing doc if fewer; file format as s19, read by s13.naming_request."""
        plan, keys, doc_len = build_side(side, cs, naming_only=True)
        used = sorted({it["doc"] for c in cs if plan[c]["naming"] for it in plan[c]["naming"]})
        ids_of = token_ids(side, keys, doc_len, used, tokenizer)
        for c in cs:
            items = plan[c]["naming"]
            ex = {"concept": c, "set": side, "n_firing": {"rollout": plan[c]["n_firing"]}, "max_by_subset": {"rollout": plan[c]["max"]},
                  "naming": {"rollout": windows_of(items, keys, ids_of, text_of) if items else None}}
            (OUT / folder / f"{side}_{c}.json").write_text(json.dumps(ex, ensure_ascii=False))
        print(side, len(cs), "naming windows", round(time.time() - t0), flush=True)
        return {c: plan[c]["n_firing"] for c in cs}

    docs_named = {}
    if new_dolma:
        docs_named["train"] = naming_files("train", new_dolma, "train_examples")
    for g in SETS:
        cs = sorted(c for c, m in new_rollout.items() if m == g)
        if cs:
            docs_named[g] = naming_files(g, cs, "rollout_examples")

    sources = {}
    for e in reused.values():
        key = f"{e['source']}, {e['windows']}"
        sources[key] = sources.get(key, 0) + 1
    counts = np.array([n for d in docs_named.values() for n in d.values()])
    summary = {"cutoff": ml.EPSILON, "by_model": by_model, "entries": len(rows), "distinct_concepts": len(side_of), "distinct_in_list_a": len(a_concepts), "distinct_in_list_b": len(b_concepts),
               "new_dolma_names": len(new_dolma), "new_rollout_names": len(new_rollout), "reused_names": len(reused), "reused_by_source": sources, "new_rollout_names_by_model": {g: sum(m == g for m in new_rollout.values()) for g in SETS},
               "new_names_from_under_40_docs": int((counts < 40).sum()) if len(counts) else 0, "new_names_no_firing_doc": int((counts == 0).sum()) if len(counts) else 0,
               "distinct_random_concepts": len({x["concept"] for x in rows if x["list"] == "random"}), "garbled": garbled, "seconds": round(time.time() - t0)}
    (R / f"{RUN}_missing_selection_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
