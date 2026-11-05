"""Concepts that moved, and their example windows on both sides (design.md G47, G48, G52). CPU only.

Usage: python s12_moved_windows.py
Reads DATA/full_post/distribution.parquet (s03), Exp 1's V acts and doc texts, and the full_post acts and rollouts.
Writes DATA/full_post/moved/examples/<concept>.json and DATA/full_post/moved/concepts.json (pool: windows hold text,
G20) and results/full_post_moved_windows_summary.json (ids and counts only).
"""
import json
import time

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np
import pandas as pd
from transformers import AutoTokenizer

from s03_pilot import tokenize  # Exp 1
from s06_examples import (ALL_SUBSETS, GROUPS, N_NAMING, N_NONFIRING_CANDIDATES, N_QUIZ, NAMING_PER_GROUP, QUIZ_PER_GROUP, WINDOW,
                          rank_groups, window_start)  # Exp 1 E1, E2, E9
from s06_examples import PURPOSES as S06_PURPOSES  # Exp 1 E6

D_SAE = 65_536
SETS = ["stage1", "main", "sft", "dpo", "instruct"]
SIDE_SEED = {"V": 10, **{g: 11 + i for i, g in enumerate(SETS)}, "train": 16}  # G48; train: G70
PURPOSE = {"naming": 0, "quiz_firing": 1, "quiz_nonfiring": 2}  # Exp 1 E6
N_TOP = 10  # G47: gainers and losers per set
N_CONTROLS, RANK_WINDOW, NEAR_ONE = 4, 500, 0.1  # G47 (Angela's change)
MIN_FIRING = N_NAMING + N_QUIZ  # G47, G48: 40 naming + 50 quiz docs, disjoint
RUN = "full_post"
OUT = settings.DATA / RUN / "moved"
LISTED = ("concept", "set", "kind", "matched_to", "rank_train", "ln_ratio", "n_fire_V", "n_fire_set", "testable_V", "testable_set")


def side_parts(side):
    """(part path, mask of the side's docs in that part) for Dolma V, Dolma train (G70) or one rollout set."""
    if side in ("V", "train"):
        docs = pd.read_parquet(settings.EXP1_RUN / "docs.parquet", columns=["doc_id", "subset"])
        mine = set(docs.loc[(docs["subset"] == "V") == (side == "V"), "doc_id"])
        parts = sorted((settings.EXP1_RUN / "acts").glob("part_?????.npz"))
        return [(p, lambda ids: np.array([d in mine for d in ids])) for p in parts]
    return [(p, lambda ids: np.ones(len(ids), dtype=bool)) for p in sorted((settings.DATA / RUN / side / "acts").glob("part_?????.npz"))]


def firing_counts(side):
    """Docs per concept with a non-zero Eq. 1 mean, over every doc of the side (G47 testability)."""
    n = np.zeros(D_SAE, dtype=np.int64)
    for path, mask_of in side_parts(side):
        with np.load(path, allow_pickle=True) as z:
            keep = mask_of(z["doc_id"])
            doc = np.repeat(np.arange(len(keep)), z["doc_active"])
            n += np.bincount(z["doc_latent_ids"][keep[doc]].astype(np.int64), minlength=D_SAE)
    return n


def select(table, n_fire):
    """G47: moved concepts (one set each) and rank-matched controls."""
    chi_train = table["chi_train"].to_numpy()
    rank = np.empty(D_SAE, dtype=np.int64)
    rank[np.argsort(-chi_train, kind="stable")] = np.arange(1, D_SAE + 1)
    sel = table["in_slope"].to_numpy()
    entries = []
    for g in SETS:
        gain = table[f"chi_{g}"].to_numpy() - chi_train
        entries += [(int(c), g, "gainer", float(gain[c])) for c in np.argsort(-gain, kind="stable")[:N_TOP]]
        entries += [(int(c), g, "loser", float(gain[c])) for c in np.argsort(gain, kind="stable")[:N_TOP]]
    chosen = {}
    for c, g, kind, gain in entries:  # the set where the concept moved most among those that selected it
        if c not in chosen or abs(gain) > abs(chosen[c]["mass_change"]):
            chosen[c] = {"concept": c, "set": g, "kind": kind, "mass_change": gain}
    moved = set(chosen)
    redraws = {}
    for i, g in enumerate(SETS):
        rng = np.random.default_rng([config.SEED, 47, i])
        mine = [c for c, gg, _, _ in entries if gg == g]
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.abs(np.log(table[f"chi_{g}"].to_numpy() / chi_train))
        pool = sel & (ratio <= NEAR_ONE) & (n_fire["V"] >= MIN_FIRING) & (n_fire[g] >= MIN_FIRING)
        pool[list(moved)] = False
        got, redraws[g] = [], 0
        for _ in range(1000):
            if len(got) == N_CONTROLS:
                break
            m = int(rng.choice(mine))
            cand = np.flatnonzero(pool & (np.abs(rank - rank[m]) <= RANK_WINDOW))
            cand = cand[~np.isin(cand, got)]
            if len(cand) == 0:
                redraws[g] += 1
                continue
            c = int(rng.choice(cand))
            got.append(c)
            chosen[c] = {"concept": c, "set": g, "kind": "control", "matched_to": m,
                         "mass_change": float(table.at[c, f"chi_{g}"] - chi_train[c])}
        if len(got) < N_CONTROLS:
            raise SystemExit(f"G47: only {len(got)} controls for {g}")
    for c, v in chosen.items():
        g = v["set"]
        v.update({"rank_train": int(rank[c]), "chi_train": float(chi_train[c]), "chi_set": float(table.at[c, f"chi_{g}"]),
                  "ln_ratio": float(np.log(table.at[c, f"chi_{g}"] / chi_train[c])) if table.at[c, f"chi_{g}"] > 0 else None,
                  "n_fire_V": int(n_fire["V"][c]), "n_fire_set": int(n_fire[g][c]),
                  "testable_V": bool(n_fire["V"][c] >= MIN_FIRING), "testable_set": bool(n_fire[g][c] >= MIN_FIRING)})
    return sorted(chosen.values(), key=lambda v: v["concept"]), redraws, len(entries)


def side_entries(parts, concepts):
    """Doc-level entries of the given concepts on one side: doc keys, doc lengths, entry doc, concept, max, argmax."""
    selected = np.zeros(D_SAE, dtype=bool)
    selected[concepts] = True
    keys, doc_len = [], []  # side-global doc index -> (part index, local index, doc id)
    e_doc, e_c, e_max, e_arg = [], [], [], []
    for k, (path, mask_of) in enumerate(parts):
        with np.load(path, allow_pickle=True) as z:
            ids = z["doc_id"]
            keep = mask_of(ids)
            local = np.flatnonzero(keep)
            glob = np.full(len(ids), -1)
            glob[local] = np.arange(len(keys), len(keys) + len(local))
            keys += [(k, int(j), ids[j]) for j in local]
            doc_len += [int(n) for n in z["doc_tokens"][local]]
            doc = np.repeat(np.arange(len(ids)), z["doc_active"])
            m = selected[z["doc_latent_ids"]] & keep[doc]
            e_doc.append(glob[doc[m]])
            e_c.append(z["doc_latent_ids"][m].astype(np.int64))
            e_max.append(z["doc_max"][m])
            e_arg.append(z["doc_argmax"][m].astype(np.int64))
    e_doc, e_c, e_max, e_arg = map(np.concatenate, (e_doc, e_c, e_max, e_arg))
    return keys, np.array(doc_len), e_doc, e_c, e_max, e_arg


def fill_acts(parts, keys, requests):
    """E5: the concept's activation at each token of each requested window, stored in the item."""
    by_part = {}
    for d, c, item in requests:
        by_part.setdefault(keys[d][0], []).append((d, c, item))
    for k, reqs in by_part.items():
        with np.load(parts[k][0], allow_pickle=True) as z:
            tok_start = np.concatenate([[0], np.cumsum(z["doc_tokens"])])
            entry_start = np.concatenate([[0], np.cumsum(z["tok_counts"], dtype=np.int64)])
            lat, val, tc = z["latent_ids"], z["values"], z["tok_counts"]
            for d, c, item in reqs:
                j = keys[d][1]
                t0 = tok_start[j] + item["start"]
                t1 = min(t0 + WINDOW, tok_start[j + 1])
                e0, e1 = entry_start[t0], entry_start[t1]
                tok = np.repeat(np.arange(t1 - t0), tc[t0:t1])
                hit = lat[e0:e1] == c
                acts = np.zeros(t1 - t0, dtype=np.float32)
                acts[tok[hit]] = val[e0:e1][hit]
                item["acts"] = acts


def build_side(side, concepts, naming_only=False):
    """G48: naming and held-out quiz windows for the given concepts on one side. Returns {concept: {...}}.
    naming_only (G64, G69): only naming windows: 40 as usual, or every firing doc if the concept has fewer than 40."""
    parts = side_parts(side)
    keys, doc_len, e_doc, e_c, e_max, e_arg = side_entries(parts, concepts)
    s_i = SIDE_SEED[side]
    plan, requests = {}, []
    for c in concepts:
        idx = np.flatnonzero(e_c == c)
        out = {"n_firing": int(len(idx)), "max": round(float(e_max[idx].max()), 4) if len(idx) else 0.0}
        plan[c] = out
        if len(idx) < (1 if naming_only else MIN_FIRING):
            out["naming"] = out["quiz_firing"] = out["quiz_nonfiring"] = None  # G47: side not testable
            continue
        order = idx[np.lexsort((e_doc[idx], e_max[idx]))]
        if naming_only and len(idx) < N_NAMING:  # G69: all of them, in rank order
            naming = [(int(e), g) for g, members in enumerate(np.array_split(order, GROUPS)) for e in members]
        else:
            naming = rank_groups(order, NAMING_PER_GROUP, np.random.default_rng([config.SEED, c, s_i, PURPOSE["naming"]]))
        named_docs = {int(e_doc[e]) for e, _ in naming}
        picks_by_purpose = [("naming", naming)]
        if not naming_only:
            rest = order[~np.isin(e_doc[order], list(named_docs))]  # G48: held out from naming
            quiz = rank_groups(rest, QUIZ_PER_GROUP, np.random.default_rng([config.SEED, c, s_i, PURPOSE["quiz_firing"]]))
            picks_by_purpose.append(("quiz_firing", quiz))
        for purpose, picks in picks_by_purpose:
            out[purpose] = []
            for e, g in picks:
                d = int(e_doc[e])
                item = {"doc": d, "group": g, "max": float(e_max[e]), "start": window_start(int(e_arg[e]), int(doc_len[d]))}
                out[purpose].append(item)
                requests.append((d, c, item))
        if naming_only:
            continue
        rng = np.random.default_rng([config.SEED, c, s_i, PURPOSE["quiz_nonfiring"]])
        pool = np.setdiff1d(np.arange(len(keys)), list(named_docs))
        out["quiz_nonfiring"] = []
        for d in rng.choice(pool, size=min(N_NONFIRING_CANDIDATES, len(pool)), replace=False):
            item = {"doc": int(d), "group": None, "max": 0.0, "start": int(rng.integers(0, max(int(doc_len[d]) - WINDOW, 0) + 1))}
            out["quiz_nonfiring"].append(item)
            requests.append((int(d), c, item))

    fill_acts(parts, keys, requests)
    for c in concepts:  # E4, E9: first 50 all-zero candidates
        if plan[c].get("quiz_nonfiring") is not None:
            kept = [it for it in plan[c]["quiz_nonfiring"] if not it["acts"].any()][:N_QUIZ]
            plan[c]["quiz_nonfiring"] = kept if len(kept) == N_QUIZ else None
    return plan, keys, doc_len


def build_v_quiz(concepts, per_group=3, n_nonfiring=30):
    """G71: V quiz windows per concept. Firing: per_group from each of the 10 rank groups, or every firing doc if the
    concept has fewer than 10 * per_group. Non-firing: the first n_nonfiring all-zero of 200 candidates (E4, E9).
    A side with no firing doc, or too few all-zero candidates, is None. Seeds as s06: E6, V is subset index 2."""
    parts = side_parts("V")
    keys, doc_len, e_doc, e_c, e_max, e_arg = side_entries(parts, concepts)
    v_i = ALL_SUBSETS.index("V")
    plan, requests = {}, []
    for c in concepts:
        idx = np.flatnonzero(e_c == c)
        out = {"n_firing": int(len(idx)), "max": round(float(e_max[idx].max()), 4) if len(idx) else 0.0, "quiz_firing": None}
        plan[c] = out
        if len(idx):
            order = idx[np.lexsort((e_doc[idx], e_max[idx]))]
            if len(idx) < GROUPS * per_group:
                picks = [(int(e), g) for g, members in enumerate(np.array_split(order, GROUPS)) for e in members]
            else:
                picks = rank_groups(order, per_group, np.random.default_rng([config.SEED, c, v_i, S06_PURPOSES["quiz_firing"]]))
            out["quiz_firing"] = []
            for e, g in picks:
                d = int(e_doc[e])
                item = {"doc": d, "group": g, "max": float(e_max[e]), "start": window_start(int(e_arg[e]), int(doc_len[d]))}
                out["quiz_firing"].append(item)
                requests.append((d, c, item))
        rng = np.random.default_rng([config.SEED, c, v_i, S06_PURPOSES["quiz_nonfiring"]])
        out["quiz_nonfiring"] = []
        for d in rng.choice(len(keys), size=min(N_NONFIRING_CANDIDATES, len(keys)), replace=False):
            item = {"doc": int(d), "group": None, "max": 0.0, "start": int(rng.integers(0, max(int(doc_len[d]) - WINDOW, 0) + 1))}
            out["quiz_nonfiring"].append(item)
            requests.append((int(d), c, item))
    fill_acts(parts, keys, requests)
    for c in concepts:
        kept = [it for it in plan[c]["quiz_nonfiring"] if not it["acts"].any()][:n_nonfiring]
        plan[c]["quiz_nonfiring"] = kept if len(kept) == n_nonfiring else None
    return plan, keys, doc_len


def token_ids(side, keys, doc_len, used, tokenizer):
    """Re-tokenized ids of the docs used, as s02/s04 encoded them, checked against the stored lengths."""
    ids_of = {}
    if side in ("V", "train"):
        docs = pd.read_parquet(settings.EXP1_RUN / "docs.parquet", columns=["doc_id", "text"]).set_index("doc_id")
        text_of = {d: docs.at[keys[d][2], "text"] for d in used}
    else:
        rolls = pd.concat([pd.read_parquet(p) for p in sorted((settings.DATA / RUN / side / "rollouts").glob("part_?????.parquet"))]).set_index("rollout_id")
        text_of = {d: tokenizer.decode(settings.encoder_ids(RUN, rolls.at[keys[d][2], "ids"])) for d in used}  # G34
    for d in used:
        ids = tokenize(tokenizer, text_of[d])[0]
        if len(ids) != doc_len[d]:
            raise SystemExit(f"{side} doc {keys[d][2]}: {len(ids)} tokens now vs {doc_len[d]} encoded")
        ids_of[d] = ids
    return ids_of


def main():
    t0 = time.time()
    table = pd.read_parquet(settings.DATA / RUN / "distribution.parquet")
    n_fire = {s: firing_counts(s) for s in ["V"] + SETS}
    print("firing counts done", round(time.time() - t0), flush=True)
    concepts, redraws, n_entries = select(table, n_fire)
    (OUT / "examples").mkdir(parents=True, exist_ok=True)
    (OUT / "concepts.json").write_text(json.dumps(concepts, indent=1))
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    piece = {}

    def text_of(i):
        if i not in piece:
            piece[i] = tokenizer.decode([i])
        return piece[i]

    files = {v["concept"]: {k: v[k] for k in v} | {"run": RUN, "n_firing": {}, "max_by_subset": {},
                                                     "naming": {}, "quiz_firing": {}, "quiz_nonfiring": {}} for v in concepts}
    short = {}
    for side in ["V"] + SETS:
        cs = [v["concept"] for v in concepts if side == "V" or v["set"] == side]
        if not cs:
            continue
        plan, keys, doc_len = build_side(side, cs)
        used = sorted({it["doc"] for c in cs for p in ("naming", "quiz_firing", "quiz_nonfiring") if plan[c].get(p) for it in plan[c][p]})
        ids_of = token_ids(side, keys, doc_len, used, tokenizer)
        label = "dolma" if side == "V" else "rollout"
        for c in cs:
            f = files[c]
            f["n_firing"][label], f["max_by_subset"][label] = plan[c]["n_firing"], plan[c]["max"]
            for p in ("naming", "quiz_firing", "quiz_nonfiring"):
                items = plan[c].get(p)
                if items is None:
                    short[f"{p}_{label}"] = short.get(f"{p}_{label}", 0) + 1
                    f[p][label] = None
                    continue
                f[p][label] = [{"doc_id": str(keys[it["doc"]][2]), "start": it["start"], "group": it["group"], "max": round(it["max"], 4),
                                "ids": [int(i) for i in ids_of[it["doc"]][it["start"]:it["start"] + WINDOW]],
                                "texts": [text_of(int(i)) for i in ids_of[it["doc"]][it["start"]:it["start"] + WINDOW]],
                                "acts": [round(float(a), 4) for a in it["acts"]]} for it in items]
        print(side, len(cs), "concepts", round(time.time() - t0), flush=True)
    for c, f in files.items():
        (OUT / "examples" / f"{c}.json").write_text(json.dumps(f, ensure_ascii=False))
    summary = {"entries": n_entries, "concepts": len(concepts),
               "by_kind": {k: sum(v["kind"] == k for v in concepts) for k in ("gainer", "loser", "control")},
               "by_set": {g: sum(v["set"] == g for v in concepts) for g in SETS},
               "control_redraws": redraws, "short": short,
               "testable_both_sides": sum(v["testable_V"] and v["testable_set"] for v in concepts),
               "concepts_list": [{k: v[k] for k in LISTED if k in v} for v in concepts],
               "seconds": round(time.time() - t0)}
    (settings.RESULTS / f"{RUN}_moved_windows_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "concepts_list"}, indent=1))


if __name__ == "__main__":
    main()
