"""Names per model and class, and the check of Dolma names against rollout names (design.md G63-G67). Calls the API.

Usage: python s20_named_labels.py check     # free: rebuilds every request with placeholder names and tests them
       python s20_named_labels.py run       # free key check, T1 names, rollout names, quiz, analysis; resumes
       python s20_named_labels.py analyze   # no API
Reads DATA/full_post/named/ (s19) and exp1/full/examples_named/ (s06). Writes requests, raw answers and the ledger to
DATA/full_post/labels/named/ (pool: they hold text), DATA/full_post/named/check_examples.md (pool) and
results/full_post_named_{names,summary}.* (ids, names, scores, costs). New names also go to notes/name_cache.json.
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

LIMIT_USD = 35.0  # G67, Angela
NAME_CAP, QUIZ_CAP = 1_000, 1_000  # Exp 1 F7; G53
NAME_CHUNK, QUIZ_CHUNK = 200, 500  # G67
N_CHECK, LOW_SCORE, N_BOOT = 20, 0.6, 10_000  # G64, G66
EXPECTED = {"name": 1.74 / 122, "quiz": 7.15 / 4280}  # G67: dollars per request, G47's run
RUN = "full_post"
IN = settings.DATA / RUN / "named"
OUT = settings.DATA / RUN / "labels" / "named"
T1_EXAMPLES = config.DATA / "full" / "examples_named"
GROUP_ORDER, CLASS_ORDER = ["base", "instruct"], ["over", "under", "middle"]
s13.OUT, s13.LIMIT_USD = OUT, LIMIT_USD


def selection():
    return json.loads((IN / "concepts.json").read_text())


def t1_example(c):
    return json.loads((T1_EXAMPLES / f"{c}.json").read_text())


def rollout_example(model, c):
    return json.loads((IN / "rollout_examples" / f"{model}_{c}.json").read_text())


def preflight():
    """G67: one free token count, so a bad key stops the job before any money moves."""
    n = claude_batch.client().messages.count_tokens(model=LABELER, messages=[{"role": "user", "content": "ping"}]).input_tokens
    print(f"key works: free token count returned {n}", flush=True)


# ---- requests ----
def t1_requests(new):
    out = []
    for c in new:
        ex = t1_example(c)
        if ex["naming"]["T1"] is not None:
            out.append((f"nameT1-{c}-T1-0", naming_request(c, "T1", ex, max_tokens=NAME_CAP)))
    return out


def outcomes_of(pattern):
    out = {}
    for path in sorted(OUT.glob(f"outcomes_{pattern}.json")):
        out.update(json.loads(path.read_text()))
    return out


def names_from(outcomes):
    """{(concept, third cid field): name} for the answers that returned one; the rest are counted by their status."""
    names = {}
    for cid, o in outcomes.items():
        name = (o.get("answer") or {}).get("explanation") if o["status"] == "ok" else None
        if name:
            _, c, third, _ = cid.split("-")
            names[(int(c), third)] = name
    return names


def final_check(cells, t1):
    """G64: the first 20 of each ordered list whose T1 name came back."""
    final = []
    for cell in cells:
        kept = [e for e in cell["order"] if e["concept"] in t1][:N_CHECK]
        final += [{**e, "group": cell["group"], "class": cell["class"]} for e in kept]
    return final


def skipped_for_failed_t1(cells, t1):
    """G64: how many candidates each cell passed over because their T1 name did not come back."""
    out = {}
    for cell in cells:
        passed, kept = 0, 0
        for e in cell["order"]:
            if kept == N_CHECK:
                break
            kept += e["concept"] in t1
            passed += e["concept"] not in t1
        out[f"{cell['group']}_{cell['class']}"] = passed
    return out


def build_quiz(final, t1, rollout, longest_name):
    """F4c: both names on the same V windows; a Dolma name in both groups is quizzed once. Input bounds as F7b."""
    quiz, key, seen = [], {}, set()
    for e in final:
        c, model = e["concept"], e["model"]
        ex = t1_example(c)
        if ex["quiz_nonfiring"]["V"] is None or ex["quiz_firing"]["V"] is None:
            continue  # E9: counted in analyze
        for purpose, name in (("qd", t1[c]), (f"qr{model}", rollout.get((c, model)))):
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
    """T1 names, then the check's rollout names, then the quiz. Each saved submission is skipped on a restart."""
    reqs = t1_requests(sel["new_t1"])
    for i in range(0, len(reqs), NAME_CHUNK):
        tag, chunk = f"names_t1_{i // NAME_CHUNK}", reqs[i:i + NAME_CHUNK]
        if s13.saved(tag) is None:
            s13.send(chunk, tag, s13.count_inputs(chunk))
        name_cache.add((c, n, "dolma", "T1 all sources", "exp2 named (G63)", None) for (c, _), n in names_from(s13.saved(tag)).items())
    t1_out = outcomes_of("names_t1_*")
    t1 = {c: n for (c, _), n in names_from(t1_out).items()}

    final = final_check(sel["cells"], t1)
    cache = name_cache.load()
    rollout, cached_lengths, todo = {}, [], []
    for e in final:
        c, model = e["concept"], e["model"]
        ex = t1_example(c)
        e["e9_short"] = ex["quiz_nonfiring"]["V"] is None
        hit = name_cache.rollout(cache, c, model)
        e["rollout_name_source"] = hit["source"] if hit else "exp2 named (G64)"
        if hit:
            rollout[(c, model)] = hit["name"]
            cached_lengths.append(len(hit["name"]))
        else:
            cid = f"namerollout-{c}-{model}-0"
            if cid not in {t[0] for t in todo}:
                todo.append((cid, s13.naming_request(c, rollout_example(model, c), "rollout")))
    (OUT / "check.json").write_text(json.dumps(final, indent=0))
    if todo and s13.saved("names_rollout") is None:
        s13.send(todo, "names_rollout", s13.count_inputs(todo))
    roll_out = s13.saved("names_rollout") or {}
    new_rollout = {(c, m): n for (c, m), n in names_from(roll_out).items()}
    name_cache.add((c, n, "rollout", f"rollouts {m}", "exp2 named (G64)", m) for (c, m), n in new_rollout.items())
    rollout.update(new_rollout)

    used = [(o.get("usage") or {}).get("output_tokens", NAME_CAP) for o in list(t1_out.values()) + list(roll_out.values()) if o["status"] == "ok"]
    quiz, key, bounds, _ = build_quiz(final, t1, rollout, max(used + cached_lengths))
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
    """G67: free. Every request rebuilt with placeholder names; nothing is sent."""
    OUT.mkdir(parents=True, exist_ok=True)
    preflight()
    sel = selection()
    reqs = t1_requests(sel["new_t1"])
    print(f"T1 naming requests: {len(reqs)} of {len(sel['new_t1'])} planned", flush=True)
    last = lambda p: p["messages"][-1]["content"]  # noqa: E731
    bad = [cid for cid, p in reqs if not (p["model"] == LABELER and p["max_tokens"] == NAME_CAP and p["output_config"]["effort"] == "high"
                                          and "Example 40:" in last(p) and "Example 41:" not in last(p))]
    t1 = {c: PLACEHOLDER for c in sel["new_t1"]}
    final = final_check(sel["cells"], t1)
    per_cell = {}
    for e in final:
        per_cell[f"{e['group']}_{e['class']}"] = per_cell.get(f"{e['group']}_{e['class']}", 0) + 1
    print("check concepts per cell:", per_cell, flush=True)
    roll_reqs = [(f"namerollout-{e['concept']}-{e['model']}-0", s13.naming_request(e["concept"], rollout_example(e["model"], e["concept"]), "rollout")) for e in final]
    n_windows = {f"namerollout-{e['concept']}-{e['model']}-0": len(rollout_example(e["model"], e["concept"])["naming"]["rollout"]) for e in final}
    bad += [cid for cid, p in roll_reqs if not (p["model"] == LABELER and p["max_tokens"] == NAME_CAP and 1 <= n_windows[cid] <= 40  # G69
                                                and f"Example {n_windows[cid]}:" in last(p) and f"Example {n_windows[cid] + 1}:" not in last(p))]
    print("rollout windows per check concept: under 40 in", sum(n < 40 for n in n_windows.values()), "of", len(n_windows), "; fewest", min(n_windows.values()), flush=True)
    rollout = {(e["concept"], e["model"]): PLACEHOLDER + " B" for e in final}
    quiz, key, _, base = build_quiz(final, t1, rollout, 0)
    by_id = dict(quiz)
    e9 = len({e["concept"] for e in final if t1_example(e["concept"])["quiz_nonfiring"]["V"] is None})
    bad += [cid for cid, p in quiz if not (p["model"] == SCORER and p["max_tokens"] == QUIZ_CAP and p["output_config"]["effort"] == "high"
                                           and "Example 4:" in last(p) and "Example 5:" not in last(p))]
    bad += [cid for cid, windows in key.items() if len(windows) != 5]
    for c in {e["concept"] for e in final}:
        mine = [w for cid, windows in key.items() if cid.startswith(f"qd-{c}-") for w in windows]
        if mine and (len(mine) != 100 or sum(w["fires"] for w in mine) != 50):
            bad.append(f"qd windows of {c}")
    for e in final:  # same prompt apart from the name, same windows
        for k in range(20):
            a, b = by_id.get(f"qd-{e['concept']}-V-{k}"), by_id.get(f"qr{e['model']}-{e['concept']}-V-{k}")
            if a is not None and (b is None or json.dumps(a).replace(PLACEHOLDER, "@") != json.dumps(b).replace(PLACEHOLDER + " B", "@")):
                bad.append(f"prompt pair {e['concept']}/{k}")
    # Guard path at expected rates (G67): the name bound uses counted inputs, the quiz bound assumes the longest name allowed
    sample = [reqs[i] for i in np.random.default_rng([config.SEED, 67, 100]).choice(len(reqs), size=min(50, len(reqs)), replace=False)]
    counts = s13.count_inputs(sample)
    worst_name = max(claude_batch.worst_case(p, counts[cid]) for cid, p in sample)
    worst_quiz = claude_batch.worst_case(quiz[0][1], base + NAME_CAP + s13.SLACK_TOKENS)
    spent_names = EXPECTED["name"] * (len(reqs) + len(roll_reqs))
    path = max([EXPECTED["name"] * i + worst_name * min(NAME_CHUNK, len(reqs) - i) for i in range(0, len(reqs), NAME_CHUNK)]
               + [EXPECTED["name"] * len(reqs) + worst_name * len(roll_reqs)]
               + [spent_names + EXPECTED["quiz"] * i + worst_quiz * min(QUIZ_CHUNK, len(quiz) - i) for i in range(0, len(quiz), QUIZ_CHUNK)])
    report = {"t1_requests": len(reqs), "rollout_requests": len(roll_reqs), "quiz_prompts": len(quiz), "e9_short_concepts": e9, "quiz_base_input_tokens": base,
              "worst_usd_per_name": round(worst_name, 4), "worst_usd_per_quiz_prompt": round(worst_quiz, 5), "worst_usd_per_name_chunk": round(worst_name * NAME_CHUNK, 2),
              "worst_usd_per_quiz_chunk": round(worst_quiz * QUIZ_CHUNK, 2), "expected_total_usd": round(spent_names + EXPECTED["quiz"] * len(quiz), 2),
              "highest_spent_plus_worst_usd": round(path, 2), "failures": len(bad), "first_failures": bad[:10]}
    print(json.dumps(report, indent=1))
    if bad or path > LIMIT_USD:
        raise SystemExit("check failed")
    print("check passed")


# ---- analysis (G66) ----
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
    t1_out, roll_out = outcomes_of("names_t1_*"), s13.saved("names_rollout") or {}
    t1 = {c: n for (c, _), n in names_from(t1_out).items()}
    cache = name_cache.load()
    check_path = OUT / "check.json"
    final = json.loads(check_path.read_text()) if check_path.exists() else []
    score, quiz_out = scores()
    info = {(r["concept"], r["model"]): r for r in sel["rows"]}

    # Names by model and class
    by_model = {}
    in_check = {(e["concept"], e["model"]) for e in final}
    for r in sel["rows"]:
        c = r["concept"]
        hit = sel["reused"].get(str(c))
        name, source = (hit["name"], f"{hit['source']}, {hit['windows']}") if hit else (t1.get(c), "exp2 named (G63), T1 all sources")
        by_model.setdefault(r["model"], {}).setdefault(r["class"], []).append({**{k: r[k] for k in ("concept", "r", "class_noflag", "r_noflag", "chi_train", "chi_model", "n_T1", "n_V", "n_fire_model")},
                                                                                "name": name, "source": source, "in_check": (c, r["model"]) in in_check})
    (settings.RESULTS / f"{RUN}_named_names.json").write_text(json.dumps(by_model, indent=0, ensure_ascii=False))

    # Check pairs
    pairs = []
    for e in final:
        c, model = e["concept"], e["model"]
        d = score.get(("qd", c), {})
        ro = score.get((f"qr{model}", c), {})
        hit = name_cache.rollout(cache, c, model)
        rname = hit["name"] if hit else None
        ds, rs = d.get("score"), ro.get("score")
        status = ("no_nonfiring_E9" if e["e9_short"] else "rollout_name_missing" if rname is None else "not_quizzed" if not d or not ro
                  else "too_few_answers" if None in (ds, rs) else "scored")
        pairs.append({"group": e["group"], "class": e["class"], "concept": c, "model": model, "r": info[(c, model)]["r"], "class_noflag": info[(c, model)]["class_noflag"],
                      "rollout_docs_named": len(rollout_example(model, c)["naming"]["rollout"]), "dolma_name": t1.get(c), "rollout_name": rname, "rollout_name_source": e["rollout_name_source"], "dolma_score": ds, "rollout_score": rs,
                      "gap": round(ds - rs, 4) if status == "scored" else None, "status": status})
    tables = {"cells": {}, "groups": {}, "classes": {}, "by_rollout_docs": {}}
    for gi, g in enumerate(GROUP_ORDER):
        tables["groups"][g] = stats([p for p in pairs if p["group"] == g], [config.SEED, 66, gi, 9])
        for ci, k in enumerate(CLASS_ORDER):
            tables["cells"][f"{g}_{k}"] = stats([p for p in pairs if p["group"] == g and p["class"] == k], [config.SEED, 66, gi, ci])
            for few, label_docs in ((1, "under_40_docs"), (0, "40_or_more_docs")):  # G69
                part = [p for p in pairs if p["group"] == g and p["class"] == k and (p["rollout_docs_named"] < 40) == bool(few)]
                if part:
                    tables["by_rollout_docs"][f"{g}_{k}_{label_docs}"] = stats(part, [config.SEED, 69, gi, ci, few])
    for ci, k in enumerate(CLASS_ORDER):
        tables["classes"][k] = stats([p for p in pairs if p["class"] == k], [config.SEED, 66, 9, ci])

    # Counts and dollars
    label = lambda cid: "quiz" if cid.startswith("q") else cid.split("-")[0]  # noqa: E731
    usage = claude_batch.usage_summary({**t1_out, **roll_out, **quiz_out}, label)
    sources = {}
    for hit in sel["reused"].values():
        sources[f"{hit['source']}, {hit['windows']}"] = sources.get(f"{hit['source']}, {hit['windows']}", 0) + 1
    crosstab = {}
    for r in sel["rows"]:
        k = f"{r['class']}->{r['class_noflag']}"
        crosstab.setdefault(r["model"], {})[k] = crosstab.setdefault(r["model"], {}).get(k, 0) + 1
    summary = {"limit_usd": LIMIT_USD, "spent_usd": round(s13.spent(), 4), "stopped": stop, "usage": usage,
               "counts": {"entries": len(sel["rows"]), "distinct_concepts": len({r["concept"] for r in sel["rows"]}), "reused_dolma_names": len(sel["reused"]),
                          "reused_by_source": sources, "new_t1_planned": len(sel["new_t1"]), "new_t1_returned": len(t1), "check_pairs": len(pairs),
                          "skipped_for_failed_t1": skipped_for_failed_t1(sel["cells"], t1),
                          "rollout_names_new": len(names_from(roll_out)), "quiz_prompts": len(quiz_out)},
               "noflag_class_of_selected": crosstab, "tables": tables, "pairs": pairs}
    (settings.RESULTS / f"{RUN}_named_summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))

    md = [f"# Exp 2: names per model and class (design.md G62-G68)\n\nSpent ${summary['spent_usd']:.2f} of the ${LIMIT_USD:.0f} limit.{' Stopped: ' + stop if stop else ''}\n\n## Names side by side\n"]
    for g in GROUP_ORDER:
        for k in CLASS_ORDER:
            md.append(f"\n### {g}, {k}\n\n| concept | model | r | noflag class | rollout docs | Dolma name | rollout name | Dolma score | rollout score | gap | status |\n|---|---|---|---|---|---|---|---|---|---|---|\n")
            for p in [p for p in pairs if p["group"] == g and p["class"] == k]:
                md.append(f"| {p['concept']} | {p['model']} | {p['r']} | {p['class_noflag']} | {p['rollout_docs_named']} | {clean(p['dolma_name'])} | {clean(p['rollout_name'])} | {p['dolma_score']} | {p['rollout_score']} | {p['gap']} | {p['status']} |\n")
    md.append("\n## Paired gap, Dolma name minus rollout name, on V windows\n\n| set | drawn | scored | unscored | Dolma name | rollout name | gap [95%] | Dolma names below 0.6 [95%] |\n|---|---|---|---|---|---|---|---|\n")
    for label_, t in [(f"{g}, {k}", tables["cells"][f"{g}_{k}"]) for g in GROUP_ORDER for k in CLASS_ORDER] + [(g, tables["groups"][g]) for g in GROUP_ORDER] + [(f"{k} (both groups)", tables["classes"][k]) for k in CLASS_ORDER] + [(k.replace("_", " "), t) for k, t in tables["by_rollout_docs"].items()]:
        unscored = {s: n for s, n in t["status"].items() if s != "scored"}
        md.append(f"| {label_} | {t['drawn']} | {t['scored_pairs']} | {unscored or 0} | {t['mean_dolma_name']} | {t['mean_rollout_name']} | {t['mean_gap']} {t['gap_ci95']} | {t['share_dolma_below_0_6']} {t['share_ci95']} |\n")
    md.append("\nPooled class rows count a concept drawn in both groups twice (G66).\n")
    (settings.RESULTS / f"{RUN}_named_summary.md").write_text("".join(md))

    # Qualitative look on pool only (G20): the strongest naming windows of each check concept
    text = ["# Check concepts: strongest naming windows (pool only, G20)\n"]
    for p in pairs:
        ex, ro = t1_example(p["concept"]), rollout_example(p["model"], p["concept"])
        text += [f"\n## {p['concept']} ({p['group']}, {p['class']}, {p['model']})\n", f"Dolma name: {clean(p['dolma_name'])}\n", f"Rollout name: {clean(p['rollout_name'])}, from {p['rollout_docs_named']} docs\n", "T1 windows (40 docs named):"]
        text += strongest(ex["naming"]["T1"]) + ["Rollout windows:"] + strongest(ro["naming"]["rollout"])
    (IN / "check_examples.md").write_text("\n".join(text) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("pairs", "noflag_class_of_selected")}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["check", "run", "analyze"])
    {"check": check, "run": run, "analyze": analyze}[parser.parse_args().stage]()
