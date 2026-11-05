"""Names per model and class, and the check of Dolma names against rollout names (design.md G70, G71, G73). Calls the API.

Usage: python s20_named_labels.py check     # free: fetches a pending batch, rebuilds every request with placeholder names, tests them
       python s20_named_labels.py run       # free key check, remaining names, rollout names, quiz, analysis; resumes
       python s20_named_labels.py analyze   # no API
Reads DATA/full_post/named/ (s19) and exp1/full/examples_named/ (s06). Writes requests, raw answers and the ledger to
DATA/full_post/labels/named/ (pool: they hold text), DATA/full_post/named/check_examples.md (pool) and
results/full_post_named_{names.json,extremes.md,summary.json,summary.md} (ids, names, scores, costs). New names also go to notes/name_cache.json.
"""
import argparse
import json

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np

import claude_batch  # Exp 1
import name_cache
import s13_moved_labels as s13  # the F7 guard, ledger and batch recovery; pointed at this run's folder and limit below
from s07_names import LABELER, THRESHOLD, mark, naming_request, pieces_of  # Exp 1 N4
from s08_quiz import MIN_ANSWERED, PLACEHOLDER, SCORER, balanced_accuracy, quiz_requests  # Exp 1 N5, N7, F4c

LIMIT_USD = 40.0  # G73, Angela
NAME_CAP, QUIZ_CAP = 1_000, 1_000  # Exp 1 F7; G53
NAME_CHUNK, QUIZ_CHUNK = 200, 500  # G67
LOW_SCORE, N_BOOT = 0.6, 10_000  # G66
EXPECTED = {"name": 6.70 / 600, "quiz": 7.15 / 4280}  # G73: dollars per request, the first 600 names and G47's quiz
RUN = "full_post"
IN = settings.DATA / RUN / "named"
OUT = settings.DATA / RUN / "labels" / "named"
T1_EXAMPLES = config.DATA / "full" / "examples_named"
GROUP_ORDER = ["base", "instruct"]
CELL_ORDER = ["random_over", "random_under", "random_middle", "extreme_over", "extreme_under_unfiltered", "extreme_under_filtered"]
s13.OUT, s13.LIMIT_USD = OUT, LIMIT_USD


def selection():
    return json.loads((IN / "concepts.json").read_text())


def t1_example(c):
    return json.loads((T1_EXAMPLES / f"{c}.json").read_text())


def train_example(c):
    return json.loads((IN / "train_examples" / f"{c}.json").read_text())


def rollout_example(model, c):
    return json.loads((IN / "rollout_examples" / f"{model}_{c}.json").read_text())


def quiz_example(c):
    return json.loads((IN / "quiz_windows" / f"{c}.json").read_text())


def dolma_windows(c, train_named):
    return train_example(c)["naming"]["rollout"] if c in train_named else t1_example(c)["naming"]["T1"]


def preflight():
    """G67: one free token count, so a bad key stops the job before any money moves."""
    n = claude_batch.client().messages.count_tokens(model=LABELER, messages=[{"role": "user", "content": "ping"}]).input_tokens
    print(f"key works: free token count returned {n}", flush=True)


# ---- requests ----
def sent_cids():
    """G73: names sent under G62-G69 are never sent again, failed ones included."""
    sent = set()
    for path in OUT.glob("requests_names_t1_*.jsonl"):
        sent.update(json.loads(line)["custom_id"] for line in open(path))
    return sent


def name_cid(c, train_named):
    return f"nameTrain-{c}-train-0" if c in train_named else f"nameT1-{c}-T1-0"


def remaining_requests(sel):
    """The new names not sent yet, in concept order; stable across restarts because names_t1_* no longer changes."""
    sent, train_named = sent_cids(), set(sel["train_named"])
    out = []
    for c in sel["new"]:
        cid = name_cid(c, train_named)
        if cid not in sent:
            out.append((cid, s13.naming_request(c, train_example(c), "rollout") if c in train_named else naming_request(c, "T1", t1_example(c), max_tokens=NAME_CAP)))
    return out


def outcomes_of(*patterns):
    out = {}
    for pattern in patterns:
        for path in sorted(OUT.glob(f"outcomes_{pattern}.json")):
            out.update(json.loads(path.read_text()))
    return out


def dolma_outcomes():
    return outcomes_of("names_t1_*", "names_more_*")


def names_from(outcomes):
    """{(concept, third cid field): name} for the answers that returned one; the rest are counted by their status."""
    names = {}
    for cid, o in outcomes.items():
        name = (o.get("answer") or {}).get("explanation") if o["status"] == "ok" else None
        if name:
            _, c, third, _ = cid.split("-")
            names[(int(c), third)] = name
    return names


def new_names(sel):
    """This run's Dolma names of the selected concepts."""
    selected = set(sel["new"])
    return {c: n for (c, _), n in names_from(dolma_outcomes()).items() if c in selected}


def cache_add_dolma(outcomes):
    windows = {"T1": ("T1 all sources", "exp2 named (G63)"), "train": ("train all sources", "exp2 named (G70)")}
    name_cache.add((c, n, "dolma", *windows[third], None) for (c, third), n in names_from(outcomes).items())


def final_check(cells, names):
    """G71: per cell, the first n of the ordered list whose new name came back."""
    final = []
    for cell in cells:
        kept = [e for e in cell["order"] if e["concept"] in names][:cell["n"]]
        final += [{**e, "group": cell["group"], "kind": cell["kind"], "class": cell["class"], "cell": f"{cell['kind']}_{cell['class']}"} for e in kept]
    return final


def skipped_for_failed_name(cells, names):
    """G71: how many candidates each cell passed over because their new name did not come back."""
    out = {}
    for cell in cells:
        passed, kept = 0, 0
        for e in cell["order"]:
            if kept == cell["n"]:
                break
            kept += e["concept"] in names
            passed += e["concept"] not in names
        out[f"{cell['group']}_{cell['kind']}_{cell['class']}"] = passed
    return out


def build_quiz(final, names, rollout, longest_name):
    """F4c: both names on the same V windows; a Dolma name in two cells is quizzed once. Input bounds as F7b."""
    quiz, key, seen = [], {}, set()
    for e in final:
        c, model = e["concept"], e["model"]
        ex = quiz_example(c)
        if ex["quiz_nonfiring"]["V"] is None or ex["quiz_firing"]["V"] is None:
            continue  # G71: counted in analyze
        for purpose, name in (("qd", names[c]), (f"qr{model}", rollout.get((c, model)))):
            if name and (purpose, c) not in seen:
                seen.add((purpose, c))
                r, k = quiz_requests(c, "V", "detection", name, ex, False, purpose=purpose, max_tokens=QUIZ_CAP)
                quiz += r
                key.update(k)
    rng = np.random.default_rng([config.SEED, 67, 200])
    sample = [quiz[i] for i in rng.choice(len(quiz), size=min(200, len(quiz)), replace=False)]
    counted = s13.count_inputs([(f"sample_{cid}", p) for cid, p in sample])
    base = max(counted[f"sample_{cid}"] for cid, _ in sample)
    return quiz, key, {cid: base + longest_name + s13.SLACK_TOKENS for cid, _ in quiz}, base


# ---- stages ----
def stages(sel):
    """Remaining names, then the check's rollout names, then the quiz. Each saved submission is skipped on a restart."""
    cache_add_dolma(outcomes_of("names_t1_*"))
    reqs = remaining_requests(sel)
    print(f"names to send: {len(reqs)} of {len(sel['new'])} new", flush=True)
    for i in range(0, len(reqs), NAME_CHUNK):
        tag, chunk = f"names_more_{i // NAME_CHUNK}", reqs[i:i + NAME_CHUNK]
        if s13.saved(tag) is None:
            s13.send(chunk, tag, s13.count_inputs(chunk))
        cache_add_dolma(s13.saved(tag))
    names = new_names(sel)

    final = final_check(sel["cells"], names)
    cache = name_cache.load()
    rollout, cached_lengths, todo = {}, [], []
    for e in final:
        c, model = e["concept"], e["model"]
        ex, ro = quiz_example(c), rollout_example(model, c)
        e["no_firing_v"], e["no_nonfiring_v"] = ex["quiz_firing"]["V"] is None, ex["quiz_nonfiring"]["V"] is None
        e["no_rollout_docs"] = ro["naming"]["rollout"] is None
        hit = name_cache.rollout(cache, c, model)
        e["rollout_name_source"] = hit["source"] if hit else None if e["no_rollout_docs"] else "exp2 named (G71)"
        if hit:
            rollout[(c, model)] = hit["name"]
            cached_lengths.append(len(hit["name"]))
        elif not e["no_rollout_docs"]:
            cid = f"namerollout-{c}-{model}-0"
            if cid not in {t[0] for t in todo}:
                todo.append((cid, s13.naming_request(c, ro, "rollout")))
    (OUT / "check.json").write_text(json.dumps(final, indent=0))
    if todo and s13.saved("names_rollout") is None:
        s13.send(todo, "names_rollout", s13.count_inputs(todo))
    roll_out = s13.saved("names_rollout") or {}
    new_rollout = names_from(roll_out)
    name_cache.add((c, n, "rollout", f"rollouts {m}", "exp2 named (G71)", m) for (c, m), n in new_rollout.items())
    rollout.update(new_rollout)

    used = [(o.get("usage") or {}).get("output_tokens", NAME_CAP) for o in list(dolma_outcomes().values()) + list(roll_out.values()) if o["status"] == "ok"]
    quiz, key, bounds, _ = build_quiz(final, names, rollout, max(used + cached_lengths))
    (OUT / "quiz_key.json").write_text(json.dumps(key))
    for i in range(0, len(quiz), QUIZ_CHUNK):
        tag = f"quiz_{i // QUIZ_CHUNK}"
        if s13.saved(tag) is None:
            s13.send(quiz[i:i + QUIZ_CHUNK], tag, bounds)


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    preflight()
    s13.recover()
    try:
        stages(selection())
    except SystemExit as stop:  # the guard: analyze what came back, then fail so the mail says so
        print(stop, flush=True)
        analyze(stop=str(stop))
        raise
    analyze()


def check():
    """G73: free. Fetches a pending batch; every request still to send is rebuilt with placeholder names; nothing is sent."""
    OUT.mkdir(parents=True, exist_ok=True)
    preflight()
    s13.recover()
    sel = selection()
    train_named = set(sel["train_named"])
    last = lambda p: p["messages"][-1]["content"]  # noqa: E731
    holds = lambda p, n: f"Example {n}:" in last(p) and f"Example {n + 1}:" not in last(p)  # noqa: E731
    missing = [c for c in sel["new"] if c not in train_named and not (T1_EXAMPLES / f"{c}.json").exists()]
    if missing:
        raise SystemExit(f"{len(missing)} concepts lack T1 windows, first {missing[:5]}")
    reqs = remaining_requests(sel)
    print(f"new names: {len(sel['new'])} planned, {len(reqs)} to send, {len(train_named)} from train windows", flush=True)
    bad = []
    for cid, p in reqs:
        c = int(cid.split("-")[1])
        n = len(train_example(c)["naming"]["rollout"]) if c in train_named else 40
        if not (p["model"] == LABELER and p["max_tokens"] == NAME_CAP and p["output_config"]["effort"] == "high" and 1 <= n <= 40 and holds(p, n)):
            bad.append(cid)
    names = {c: PLACEHOLDER for c in sel["new"]}
    final = final_check(sel["cells"], names)
    per_cell = {}
    for e in final:
        per_cell[f"{e['group']}_{e['cell']}"] = per_cell.get(f"{e['group']}_{e['cell']}", 0) + 1
    print("check concepts per cell:", per_cell, flush=True)
    bad += [f"cell {cell['group']}_{cell['kind']}_{cell['class']}" for cell in sel["cells"] if per_cell.get(f"{cell['group']}_{cell['kind']}_{cell['class']}") != cell["n"]]
    roll_reqs, zero_docs = {}, 0
    for e in final:
        ro = rollout_example(e["model"], e["concept"])
        if ro["naming"]["rollout"] is None:
            zero_docs += 1
            continue
        cid, n = f"namerollout-{e['concept']}-{e['model']}-0", len(ro["naming"]["rollout"])
        roll_reqs[cid] = (s13.naming_request(e["concept"], ro, "rollout"), n)
    bad += [cid for cid, (p, n) in roll_reqs.items() if not (p["model"] == LABELER and p["max_tokens"] == NAME_CAP and 1 <= n <= 40 and holds(p, n))]
    counts = [n for _, n in roll_reqs.values()]
    print("rollout windows per check concept: under 40 in", sum(n < 40 for n in counts), "of", len(counts), "; fewest", min(counts), "; zero docs", zero_docs, flush=True)
    rollout = {(e["concept"], e["model"]): PLACEHOLDER + " B" for e in final if f"namerollout-{e['concept']}-{e['model']}-0" in roll_reqs}
    quiz, key, _, base = build_quiz(final, names, rollout, 0)
    by_id = dict(quiz)
    unscored = {"no_firing_v": len({e["concept"] for e in final if quiz_example(e["concept"])["quiz_firing"]["V"] is None}),
                "no_nonfiring_v": len({e["concept"] for e in final if quiz_example(e["concept"])["quiz_nonfiring"]["V"] is None})}
    bad += [cid for cid, p in quiz if not (p["model"] == SCORER and p["max_tokens"] == QUIZ_CAP and p["output_config"]["effort"] == "high" and holds(p, len(key[cid]) - 1))]
    fewer_firing = 0
    for c in {e["concept"] for e in final}:
        cids = sorted((cid for cid in key if cid.startswith(f"qd-{c}-")), key=lambda cid: int(cid.split("-")[-1]))
        mine = [w for cid in cids for w in key[cid]]
        if not mine:
            continue
        n_fire = sum(w["fires"] for w in mine)
        fewer_firing += n_fire < 30
        if not 1 <= n_fire <= 30 or len(mine) - n_fire != 30 or any(len(key[cid]) != 5 for cid in cids[:-1]) or len(key[cids[-1]]) > 5:
            bad.append(f"qd windows of {c}")
    for e in final:  # same prompt apart from the name, same windows
        for k in range(12):
            a, b = by_id.get(f"qd-{e['concept']}-V-{k}"), by_id.get(f"qr{e['model']}-{e['concept']}-V-{k}")
            if a is not None and b is not None and json.dumps(a).replace(PLACEHOLDER, "@") != json.dumps(b).replace(PLACEHOLDER + " B", "@"):
                bad.append(f"prompt pair {e['concept']}/{k}")
    # Guard path at measured rates (G73): spent so far, then the worst case of each next submission on top of what precedes it
    sample = [reqs[i] for i in np.random.default_rng([config.SEED, 67, 100]).choice(len(reqs), size=min(50, len(reqs)), replace=False)]
    token_counts = s13.count_inputs(sample)
    worst_name = max(claude_batch.worst_case(p, token_counts[cid]) for cid, p in sample)
    worst_quiz = claude_batch.worst_case(quiz[0][1], base + NAME_CAP + s13.SLACK_TOKENS)
    spent0 = s13.spent()
    spent_names = spent0 + EXPECTED["name"] * (len(reqs) + len(roll_reqs))
    path = max([spent0 + EXPECTED["name"] * i + worst_name * min(NAME_CHUNK, len(reqs) - i) for i in range(0, len(reqs), NAME_CHUNK)]
               + [spent0 + EXPECTED["name"] * len(reqs) + worst_name * len(roll_reqs)]
               + [spent_names + EXPECTED["quiz"] * i + worst_quiz * min(QUIZ_CHUNK, len(quiz) - i) for i in range(0, len(quiz), QUIZ_CHUNK)])
    report = {"spent_before_usd": round(spent0, 2), "names_to_send": len(reqs), "rollout_requests": len(roll_reqs), "quiz_prompts": len(quiz), "unscored_concepts": unscored,
              "concepts_under_30_firing_v": fewer_firing, "check_entries": len(final), "check_distinct": len({e["concept"] for e in final}), "quiz_base_input_tokens": base,
              "worst_usd_per_name": round(worst_name, 4), "worst_usd_per_quiz_prompt": round(worst_quiz, 5), "worst_usd_per_name_chunk": round(worst_name * NAME_CHUNK, 2),
              "worst_usd_per_quiz_chunk": round(worst_quiz * QUIZ_CHUNK, 2), "expected_total_usd": round(spent_names + EXPECTED["quiz"] * len(quiz), 2),
              "highest_spent_plus_worst_usd": round(path, 2), "failures": len(bad), "first_failures": bad[:10]}
    print(json.dumps(report, indent=1))
    (settings.RESULTS / f"{RUN}_named_check.json").write_text(json.dumps(report, indent=1))
    if bad or path > LIMIT_USD:
        raise SystemExit("check failed")
    print("check passed")


# ---- analysis (G66, G71) ----
def stats(rows, seed):
    """Means, paired gap and the share of Dolma names below 0.6, with bootstrap 95% intervals over concepts (F5)."""
    gaps = np.array([r["gap"] for r in rows if r["gap"] is not None])
    dolma = np.array([r["dolma_score"] for r in rows if r["dolma_score"] is not None])
    roll = [r["rollout_score"] for r in rows if r["rollout_score"] is not None]
    status = {}
    for r in rows:
        status[r["status"]] = status.get(r["status"], 0) + 1
    rng = np.random.default_rng(seed)

    def interval(values):
        if not len(values):
            return None
        means = values[rng.integers(0, len(values), (N_BOOT, len(values)))].mean(axis=1)
        return [round(float(np.percentile(means, 2.5)), 4), round(float(np.percentile(means, 97.5)), 4)]

    low = (dolma < LOW_SCORE).astype(float)
    return {"drawn": len(rows), "status": status, "scored_pairs": len(gaps), "dolma_scored": len(dolma),
            "mean_dolma_name": round(float(dolma.mean()), 4) if len(dolma) else None, "mean_rollout_name": round(float(np.mean(roll)), 4) if roll else None,
            "mean_gap": round(float(gaps.mean()), 4) if len(gaps) else None, "gap_ci95": interval(gaps),
            "share_dolma_below_0_6": round(float(low.mean()), 4) if len(low) else None, "share_ci95": interval(low)}


def scores():
    """N7 per (purpose, concept); answers from a failed prompt are dropped and counted. Empty before the quiz ran."""
    path = OUT / "quiz_key.json"
    key = json.loads(path.read_text()) if path.exists() else {}
    outcomes = outcomes_of("quiz_[0-9]*")
    rows = {}
    for cid, windows in key.items():
        o = outcomes.get(cid, {"status": "missing", "answer": None})
        answers = (o.get("answer") or {}).get("answers")
        ok = o["status"] == "ok" and answers is not None and len(answers) == len(windows)
        purpose, c, _, _ = cid.split("-")
        rows.setdefault((purpose, int(c)), []).extend({**w, "answer": a if ok else None} for w, a in zip(windows, answers if ok else [None] * len(windows)))
    out = {}
    for k, r in rows.items():
        done = [x for x in r if x["answer"] is not None]
        answered = len(done) >= MIN_ANSWERED * len(r)
        out[k] = {"answered": len(done), "score": round(float(balanced_accuracy(done)), 4) if answered else None}
    return out, outcomes


def clean(t):
    return (t or "–").replace("|", "/").replace("\n", " ")


def strongest(windows, n=5):
    lines = []
    for w in sorted(windows, key=lambda w: -w["max"])[:n]:
        acts, cut = w["acts"], THRESHOLD * max(w["acts"])
        lines.append("- " + mark(pieces_of(w), lambda i: acts[i] > cut))
    return lines


def analyze(stop=None):
    sel = selection()
    train_named = set(sel["train_named"])
    d_out, roll_out = dolma_outcomes(), s13.saved("names_rollout") or {}
    names = new_names(sel)
    cache = name_cache.load()
    check_path = OUT / "check.json"
    final = json.loads(check_path.read_text()) if check_path.exists() else []
    score, quiz_out = scores()
    info = {(r["concept"], r["model"]): r for r in sel["rows"]}

    def dolma_of(c):
        hit = sel["reused"].get(str(c))
        if hit:
            return hit["name"], f"{hit['source']}, {hit['windows']}"
        return names.get(c), ("exp2 named (G70), train all sources" if c in train_named else "exp2 named (G63), T1 all sources")

    # Names by model, list and class; firing docs per concept (G70)
    by_model = {}
    in_check = {(e["concept"], e["model"]) for e in final}
    keys = ("concept", "r", "class_rank", "class_noflag", "r_noflag", "chi_train", "chi_model", "missing_from_rollouts", "n_T1", "n_V", "n_fire_train", "n_fire_model")
    for r in sel["rows"]:
        name, source = dolma_of(r["concept"])
        by_model.setdefault(r["model"], {}).setdefault(r["list"], {}).setdefault(r["class"], []).append({**{k: r[k] for k in keys}, "name": name, "source": source, "in_check": (r["concept"], r["model"]) in in_check})
    (settings.RESULTS / f"{RUN}_named_names.json").write_text(json.dumps(by_model, indent=0, ensure_ascii=False))
    md = ["# Exp 2: extreme concepts per model (design.md G70)\n\nr = ln(chi_model / chi_train). Train docs and rollout docs are firing doc counts. Unfiltered: only e^-5 on chi_train. Filtered: at least 50 firing docs on both sides.\n"]
    for model, lists in by_model.items():
        for list_name in ("extreme_unfiltered", "extreme_filtered"):
            for side in ("over", "under"):
                md.append(f"\n## {model}, {side}, {list_name.split('_')[1]}\n\n| concept | r | train docs | rollout docs | missing from rollouts | name | name source |\n|---|---|---|---|---|---|---|\n")
                part = sorted(lists[list_name][side], key=lambda x: float("-inf") if x["r"] is None else x["r"], reverse=side == "over")  # strongest first; r is None when chi_model = 0
                for x in part:
                    md.append(f"| {x['concept']} | {x['r']} | {x['n_fire_train']} | {x['n_fire_model']} | {x['missing_from_rollouts']} | {clean(x['name'])} | {x['source']} |\n")
    (settings.RESULTS / f"{RUN}_named_extremes.md").write_text("".join(md))

    # Check pairs
    pairs = []
    for e in final:
        c, model = e["concept"], e["model"]
        d, ro = score.get(("qd", c), {}), score.get((f"qr{model}", c), {})
        hit = name_cache.rollout(cache, c, model)
        rname = hit["name"] if hit else None
        ds, rs = d.get("score"), ro.get("score")
        status = ("no_firing_V" if e["no_firing_v"] else "no_nonfiring_V" if e["no_nonfiring_v"] else "no_rollout_docs" if e["no_rollout_docs"] else "rollout_name_missing" if rname is None
                  else "not_quizzed" if not d or not ro else "too_few_answers" if None in (ds, rs) else "scored")
        x = info[(c, model)]
        q = quiz_example(c)
        firing_v = q["quiz_firing"]["V"]
        ro_w = rollout_example(model, c)["naming"]["rollout"]
        pairs.append({"group": e["group"], "cell": e["cell"], "concept": c, "model": model, "r": x["r"], "class_noflag": x["class_noflag"], "missing_from_rollouts": x["missing_from_rollouts"],
                      "n_fire_train": x["n_fire_train"], "n_fire_model": x["n_fire_model"], "n_V": x["n_V"], "quiz_firing_windows": len(firing_v) if firing_v else 0,
                      "dolma_docs_named": len(dolma_windows(c, train_named)), "rollout_docs_named": len(ro_w) if ro_w else 0, "dolma_name": names.get(c), "dolma_source": dolma_of(c)[1],
                      "rollout_name": rname, "rollout_name_source": e["rollout_name_source"], "dolma_score": ds, "rollout_score": rs, "gap": round(ds - rs, 4) if status == "scored" else None, "status": status})
    tables = {"cells": {}, "groups": {}, "pooled_cells": {}, "by_rollout_docs": {}, "by_missing_from_rollouts": {}}
    for gi, g in enumerate(GROUP_ORDER):
        for ki, kind in enumerate(("random", "extreme")):
            tables["groups"][f"{g}_{kind}"] = stats([p for p in pairs if p["group"] == g and p["cell"].startswith(kind)], [config.SEED, 71, gi, 100 + ki])
        for ci, k in enumerate(CELL_ORDER):
            mine = [p for p in pairs if p["group"] == g and p["cell"] == k]
            tables["cells"][f"{g}_{k}"] = stats(mine, [config.SEED, 71, gi, ci])
            for few, label_docs in ((1, "under_40_docs"), (0, "40_or_more_docs")):  # G69, G71
                part = [p for p in mine if (p["rollout_docs_named"] < 40) == bool(few)]
                if part:
                    tables["by_rollout_docs"][f"{g}_{k}_{label_docs}"] = stats(part, [config.SEED, 71, gi, ci, 1 + few])
            for flag, label_flag in ((1, "missing_from_rollouts"), (0, "above_e-5_in_rollouts")):
                part = [p for p in mine if p["missing_from_rollouts"] == bool(flag)]
                if part:
                    tables["by_missing_from_rollouts"][f"{g}_{k}_{label_flag}"] = stats(part, [config.SEED, 71, gi, ci, 3 + flag])
    for ci, k in enumerate(CELL_ORDER):
        tables["pooled_cells"][k] = stats([p for p in pairs if p["cell"] == k], [config.SEED, 71, 9, ci])

    # Counts and dollars
    label = lambda cid: "quiz" if cid.startswith("q") else cid.split("-")[0]  # noqa: E731
    usage = claude_batch.usage_summary({**d_out, **roll_out, **quiz_out}, label)
    sources = {}
    for hit in sel["reused"].values():
        sources[f"{hit['source']}, {hit['windows']}"] = sources.get(f"{hit['source']}, {hit['windows']}", 0) + 1
    crosstab = {}
    for r in sel["rows"]:
        if r["list"] == "random":
            k = f"{r['class']}->{r['class_noflag']}"
            crosstab.setdefault(r["model"], {})[k] = crosstab.setdefault(r["model"], {}).get(k, 0) + 1
    selected = set(sel["new"])
    summary = {"limit_usd": LIMIT_USD, "spent_usd": round(s13.spent(), 4), "stopped": stop, "usage": usage,
               "counts": {"entries": len(sel["rows"]), "distinct_concepts": len({r["concept"] for r in sel["rows"]}), "reused_dolma_names": len(sel["reused"]),
                          "reused_by_source": sources, "new_names_planned": len(sel["new"]), "new_names_returned": len(names), "new_names_failed": len(sel["new"]) - len(names),
                          "new_from_train_windows": len(train_named), "names_bought_not_selected": len({c for (c, _) in names_from(d_out)} - selected),
                          "check_entries": len(pairs), "check_distinct": len({p["concept"] for p in pairs}), "skipped_for_failed_name": skipped_for_failed_name(sel["cells"], names),
                          "rollout_names_new": len(names_from(roll_out)), "quiz_prompts": len(quiz_out)},
               "noflag_class_of_random_draws": crosstab, "tables": tables, "pairs": pairs}
    (settings.RESULTS / f"{RUN}_named_summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))

    md = [f"# Exp 2: names per model and class (design.md G70-G73)\n\nSpent ${summary['spent_usd']:.2f} of the ${LIMIT_USD:.0f} limit.{' Stopped: ' + stop if stop else ''}\n\n## Names side by side\n"]
    for g in GROUP_ORDER:
        for k in CELL_ORDER:
            md.append(f"\n### {g}, {k.replace('_', ' ')}\n\n| concept | model | r | noflag class | train docs | rollout docs | missing from rollouts | Dolma name | rollout name | V firing windows | Dolma score | rollout score | gap | status |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
            for p in [p for p in pairs if p["group"] == g and p["cell"] == k]:
                md.append(f"| {p['concept']} | {p['model']} | {p['r']} | {p['class_noflag']} | {p['n_fire_train']} | {p['n_fire_model']} | {p['missing_from_rollouts']} | {clean(p['dolma_name'])} | {clean(p['rollout_name'])} | {p['quiz_firing_windows']} | {p['dolma_score']} | {p['rollout_score']} | {p['gap']} | {p['status']} |\n")
    md.append("\n## Paired gap, Dolma name minus rollout name, on V windows\n\n| set | drawn | scored | unscored | Dolma name | rollout name | gap [95%] | Dolma names below 0.6 [95%] |\n|---|---|---|---|---|---|---|---|\n")
    rows_md = [(f"{g}, {k.replace('_', ' ')}", tables["cells"][f"{g}_{k}"]) for g in GROUP_ORDER for k in CELL_ORDER] + [(k.replace("_", " "), t) for k, t in tables["groups"].items()] + [(f"{k.replace('_', ' ')} (both groups)", t) for k, t in tables["pooled_cells"].items()]
    rows_md += [(k.replace("_", " "), t) for k, t in tables["by_rollout_docs"].items()] + [(k.replace("_", " "), t) for k, t in tables["by_missing_from_rollouts"].items()]
    for label_, t in rows_md:
        unscored = {s: n for s, n in t["status"].items() if s != "scored"}
        md.append(f"| {label_} | {t['drawn']} | {t['scored_pairs']} | {unscored or 0} | {t['mean_dolma_name']} | {t['mean_rollout_name']} | {t['mean_gap']} {t['gap_ci95']} | {t['share_dolma_below_0_6']} {t['share_ci95']} |\n")
    md.append("\nPooled rows count a concept drawn in both groups twice (G66).\n")
    (settings.RESULTS / f"{RUN}_named_summary.md").write_text("".join(md))

    # Qualitative look on pool only (G20): doc counts, both names and the strongest naming windows of each check concept
    text = ["# Check concepts: strongest naming windows (pool only, G20)\n"]
    for p in pairs:
        ro = rollout_example(p["model"], p["concept"])["naming"]["rollout"]
        text += [f"\n## {p['concept']} ({p['group']}, {p['cell']}, {p['model']})\n", f"Dolma name: {clean(p['dolma_name'])}, from {p['dolma_docs_named']} docs ({p['dolma_source']}); {p['n_fire_train']} train firing docs\n",
                 f"Rollout name: {clean(p['rollout_name'])}, from {p['rollout_docs_named']} docs; {p['n_fire_model']} rollout firing docs\n", "Dolma windows:"]
        text += strongest(dolma_windows(p["concept"], train_named)) + ["Rollout windows:"] + (strongest(ro) if ro else ["- none: no firing doc"])
    (IN / "check_examples.md").write_text("\n".join(text) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("pairs", "noflag_class_of_random_draws")}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["check", "run", "analyze"])
    {"check": check, "run": run, "analyze": analyze}[parser.parse_args().stage]()
