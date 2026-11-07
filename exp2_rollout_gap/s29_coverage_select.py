"""Coverage lists per set: top 10, chi = 0, bottom 10 above e^-5, rerun stability, chi = 0 check, naming windows
(design.md G95-G98). CPU only.

Usage: python s29_coverage_select.py
Reads DATA/full_post/distribution.parquet, Exp 1's train acts and docs, each model's acts and rollouts, notes/name_cache.json.
Writes DATA/full_post/coverage/concepts.json and naming windows (pool: windows hold text, G20) and
results/full_post_coverage_selection_summary.json (ids, chi, shares and counts only).
"""
import json
import time

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np
import pandas as pd
from transformers import AutoTokenizer

import coverage_lists as cl
import diag_common as dc
import name_cache
from s03_distribution import choose
from s05_coverage import MISSING, chi  # Exp 1: e^-5 and Eq. 2
from s12_moved_windows import D_SAE, SETS, build_side, firing_counts, token_ids
from s19_named_select import windows_of
from s26_missing_select import rollout_entry

RUN = "full_post"
OUT = settings.DATA / RUN / "coverage"
R = settings.RESULTS
SET_ORDER = ["train"] + SETS  # set index for the G96 seeds


def doc_means():
    """Per-doc Eq. 1 means behind each set's published chi: Dolma train docs, and each model's matched docs (G16, G39)."""
    table = pd.read_parquet(settings.DATA / RUN / "distribution.parquet")
    docs = pd.read_parquet(settings.EXP1_RUN / "docs.parquet", columns=["doc_id", "subset"])
    paths, all_lengths = dc.set_lengths()
    chosen, _ = choose(all_lengths)
    out = {}
    train_ids = docs.loc[docs["subset"] != "V", "doc_id"].to_numpy()  # Exp 1: train = T1, T2 and train_rest
    exp1_parts = sorted((settings.EXP1_RUN / "acts").glob("part_?????.npz"))
    for s in SET_ORDER:
        means, _, _ = dc.read_means(exp1_parts, train_ids) if s == "train" else dc.read_means(paths[s], chosen[s]["doc"])
        dc.check_chi(s, means, table)  # G39: the same docs as the published chi
        out[s] = means
        print(s, means.shape, flush=True)
    return table, out


def main():
    t0 = time.time()
    if abs(MISSING - cl.EPSILON) > 1e-12:
        raise SystemExit("G95: cutoff differs from Exp 1")
    table, means = doc_means()
    n_fire = {g: firing_counts(g) for g in SETS}  # G97: all encoded rollouts
    fire_train = table["n_fire_train"].to_numpy()
    print("means and firing counts", round(time.time() - t0), flush=True)

    lists, stability = {}, {}
    for i, s in enumerate(SET_ORDER):
        m = means[s]
        expected = cl.lists_of(table[f"chi_{s}"].to_numpy())  # G95: lists from the published chi
        stays, mean_overlap, rebuilt = cl.rerun_stability(lambda w, m=m: np.asarray(m.T @ w).ravel(), m.shape[0], [config.SEED, cl.SEED_ROW, i], chi, expected)
        differ = [name for name in expected if not np.array_equal(rebuilt[name], expected[name])]  # summing order can split a near tie
        if differ:
            print(f"warning: {s} lists rebuilt from the docs differ from the published chi in {differ}", flush=True)
        lists[s], stability[s] = expected, {"stays": stays, "mean_share_staying": mean_overlap, "rebuilt_lists_differ": differ}
        print(s, {k: len(v) for k, v in expected.items()}, mean_overlap, round(time.time() - t0), flush=True)

    rows = []
    for s in SET_ORDER:
        chi_s = table[f"chi_{s}"].to_numpy()
        for name, cs in lists[s].items():
            for rank, c in enumerate(cs, 1):
                row = {"set": s, "list": name, "rank": rank, "concept": int(c), "chi": float(chi_s[c]), "chi_train": float(table.at[c, "chi_train"]), "n_fire_train": int(fire_train[c])}
                if s != "train":
                    row["n_fire_rollout_all"] = int(n_fire[s][c])
                if name in ("top", "bottom"):
                    row["stays"] = stability[s]["stays"][name][int(c)]
                if name == "zero":
                    row["fires_outside_matched"] = bool(n_fire[s][c] > 0)  # G97: matched docs give 0, so these are outside
                rows.append(row)
    overlap = {g: {name: cl.jaccard(lists[g][name], lists["train"][name]) for name in ("top", "bottom")} for g in SETS}

    # G98: Dolma text for Dolma's lists and every chi = 0 concept; rollout text for a model's top and bottom 10
    dolma_cs = sorted({x["concept"] for x in rows if x["set"] == "train" or x["list"] == "zero"})
    rollout_cs = sorted({x["concept"] for x in rows if x["set"] != "train" and x["list"] != "zero"})
    cache = name_cache.load()
    reused_dolma = {c: name_cache.dolma(cache, c) for c in dolma_cs if name_cache.dolma(cache, c)}
    reused_rollout = {c: rollout_entry(cache, c) for c in rollout_cs if rollout_entry(cache, c)}
    new_dolma = [c for c in dolma_cs if c not in reused_dolma]
    new_rollout = {}
    for c in rollout_cs:
        if c not in reused_rollout:
            models = sorted({x["set"] for x in rows if x["concept"] == c and x["set"] != "train" and x["list"] != "zero"}, key=SETS.index)
            new_rollout[c] = max(models, key=lambda g: n_fire[g][c])  # first model wins a tie

    for sub in ("train_examples", "rollout_examples"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    (OUT / "concepts.json").write_text(json.dumps({"rows": rows, "new_dolma": new_dolma, "new_rollout": {str(c): m for c, m in new_rollout.items()},
                                                   "reused_dolma": {str(c): e for c, e in reused_dolma.items()}, "reused_rollout": {str(c): e for c, e in reused_rollout.items()}}, indent=0))

    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    piece = {}

    def text_of(i):
        if i not in piece:
            piece[i] = tokenizer.decode([i])
        return piece[i]

    def naming_files(side, cs, folder):
        """G98: 40 windows by rank group, every firing doc if fewer (G69); file format as s19 and s26."""
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

    counts = [n for d in docs_named.values() for n in d.values()]
    summary = {"cutoff": cl.EPSILON, "list_size": cl.N_LIST, "reruns": cl.N_RERUNS, "drop": cl.DROP, "docs": {s: int(means[s].shape[0]) for s in SET_ORDER},
               "zero_counts": {s: len(lists[s]["zero"]) for s in SET_ORDER}, "zero_fire_outside_matched": {g: sum(x.get("fires_outside_matched", False) for x in rows if x["set"] == g and x["list"] == "zero") for g in SETS},
               "mean_share_staying": {s: stability[s]["mean_share_staying"] for s in SET_ORDER}, "rebuilt_lists_differ": {s: stability[s]["rebuilt_lists_differ"] for s in SET_ORDER}, "jaccard_with_dolma_train": overlap, "rows": rows,
               "new_dolma_names": len(new_dolma), "new_rollout_names": len(new_rollout), "reused_names": len(reused_dolma) + len(reused_rollout),
               "new_names_from_under_40_docs": sum(n < 40 for n in counts), "new_names_no_firing_doc": sum(n == 0 for n in counts), "seconds": round(time.time() - t0)}
    (R / f"{RUN}_coverage_selection_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()
