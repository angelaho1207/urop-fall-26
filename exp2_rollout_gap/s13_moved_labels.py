"""Name and quiz the concepts that moved, F-run style (design.md G49-G52). Calls the Anthropic API (Message Batches).

Usage: python s13_moved_labels.py run       # count, names, quiz, judge, analyze; resumes from what is saved
       python s13_moved_labels.py analyze   # no API
Reads DATA/full_post/moved/{concepts.json, examples/} (s12). Writes requests, raw results, names and answers to
DATA/full_post/labels/moved/ (pool: they hold text) and results/full_post_moved_summary.{json,md} (ids, names, scores,
costs). Every submission passes the F7 guard with LIMIT_USD = 15: dollars spent (a submission still in flight counts
at its worst case) plus the worst case of the requests about to be sent must stay at or below $15.
"""
import argparse
import json
import math
import sys
import time

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np

import claude_batch  # Exp 1
import prompts  # Exp 1
from s07_names import LABELER, naming_example  # Exp 1 N4
from s08_quiz import JUDGE, MIN_ANSWERED, PER_PROMPT, SCORER, balanced_accuracy, quiz_text  # Exp 1 N5, N7, N10
from s12_moved_windows import SIDE_SEED

LIMIT_USD = 15.0  # G51, Angela
CAPS = {"name": 1_000, "quiz": 200, "judge": 300}  # Exp 1 F7
QUIZ_CHUNK = 1_000  # G51
SLACK_TOKENS = 300  # Exp 1 F7b
AGREE_GAP = 0.13  # G50
RUN = "full_post"
IN = settings.DATA / RUN / "moved"
OUT = settings.DATA / RUN / "labels" / "moved"
SIDES = {"dolma": "V", "rollout": "R"}  # label in custom_ids


def concepts():
    return json.loads((IN / "concepts.json").read_text())


def examples(c):
    return json.loads((IN / "examples" / f"{c}.json").read_text())


def side_seed(ex, side):
    return SIDE_SEED["V"] if side == "dolma" else SIDE_SEED[ex["set"]]


# ---- requests (Exp 1 prompts and formatting; G49 seeds) ----
def naming_request(c, ex, side):
    windows = ex["naming"][side]
    order = np.random.default_rng([config.SEED, c, side_seed(ex, side), 10]).permutation(len(windows))
    text = "\n".join(naming_example(k + 1, windows[j], ex["max_by_subset"][side]) for k, j in enumerate(order))
    system, messages = prompts.naming_messages(text)
    return claude_batch.params(LABELER, system, messages, prompts.EXPLANATION_SCHEMA, max_tokens=CAPS["name"])


def quiz_requests(c, ex, side, name_src, name):
    """20 prompts of 5 held-out windows on one side; both names see the same windows in the same order (G49)."""
    firing, nonfiring = ex["quiz_firing"][side], ex["quiz_nonfiring"][side]
    windows = [(w, 1) for w in firing] + [(w, 0) for w in nonfiring]
    seed = [config.SEED, c, side_seed(ex, side), 20]
    order = np.random.default_rng(seed).permutation(len(windows))
    n_random = math.ceil(np.mean([sum(a > 0 for a in w["acts"]) for w in firing]))
    mark_rng = np.random.default_rng(seed + [1])
    texts = [quiz_text("detection", windows[j][0], n_random, mark_rng) for j in order]
    out, key = [], {}
    for k in range(math.ceil(len(order) / PER_PROMPT)):
        idx = range(k * PER_PROMPT, min((k + 1) * PER_PROMPT, len(order)))
        system, messages = prompts.quiz_messages("detection", name, "\n".join(f"Example {i}: {texts[j]}" for i, j in enumerate(idx)))
        cid = f"q{name_src[0]}-{c}-{SIDES[side]}-{k}"
        out.append((cid, claude_batch.params(SCORER, system, messages, prompts.ANSWERS_SCHEMA, max_tokens=CAPS["quiz"])))
        key[cid] = [{"doc_id": windows[order[j]][0]["doc_id"], "start": windows[order[j]][0]["start"], "fires": windows[order[j]][1]} for j in idx]
    return out, key


def judge_requests(names, cs):
    """N10 pairs: (Dolma name, rollout name) and a negative control with another concept's rollout name."""
    have = [c for c in cs if names.get(c, {}).get("dolma") and names.get(c, {}).get("rollout")]
    rng = np.random.default_rng([config.SEED, 47, 100])
    while True:
        perm = rng.permutation(len(have))
        if len(have) < 2 or not np.any(perm == np.arange(len(have))):
            break
    other = {c: have[j] for c, j in zip(have, perm)}
    out, key = [], {}
    for c in have:
        for kind, b in (("true", c), ("control", other[c])):
            a_name, b_name = names[c]["dolma"], names[b]["rollout"]
            swap = bool(np.random.default_rng([config.SEED, c, 47, int(kind == "control")]).integers(2))
            system, messages = prompts.judge_messages(*((b_name, a_name) if swap else (a_name, b_name)))
            cid = f"judge{kind}-{c}-{b}-0"
            out.append((cid, claude_batch.params(JUDGE, system, messages, prompts.JUDGE_SCHEMA, max_tokens=CAPS["judge"])))
            key[cid] = {"concept": c, "kind": kind, "other": b, "swapped": swap}
    return out, key


# ---- money (Exp 1 F7, F7b; G51) ----
def ledger():
    """Latest entry per tag: a submission in flight counts at its worst case until its actual cost replaces it."""
    path = OUT / "ledger.jsonl"
    last = {}
    for line in open(path) if path.exists() else []:
        e = json.loads(line)
        last[e["tag"]] = e
    return last


def spent():
    return sum(e["usd"] for e in ledger().values())


def count_inputs(requests):
    """Exact input tokens from the free counting endpoint, cached by custom_id."""
    path = OUT / "token_counts.json"
    cache = json.loads(path.read_text()) if path.exists() else {}
    api = claude_batch.client()
    for cid, p in requests:
        if cid in cache:
            continue
        for attempt in range(8):
            try:
                cache[cid] = api.messages.count_tokens(model=p["model"], system=p["system"], messages=p["messages"],
                                                       output_config={"format": p["output_config"]["format"]}).input_tokens
                break
            except Exception:  # rate limit or transient error
                time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"token count failed for {cid}")
    path.write_text(json.dumps(cache))
    return cache


def send(requests, tag, bounds):
    """Guard, record the worst case as pending, send, then record the actual dollars (G51)."""
    worst = sum(claude_batch.worst_case(p, bounds[cid]) for cid, p in requests)
    print(f"guard [{tag}]: spent ${spent():.2f} + worst case ${worst:.2f} for {len(requests)} requests (limit ${LIMIT_USD:.0f})", flush=True)
    if spent() + worst > LIMIT_USD:
        raise SystemExit(f"stopped by the $15 guard before {tag}")
    with open(OUT / "ledger.jsonl", "a") as f:
        f.write(json.dumps({"tag": tag, "usd": worst, "pending": True, "time": time.time()}) + "\n")
    outcomes = claude_batch.send(requests, OUT, tag)  # resubmits errored or expired once (N8)
    usage = claude_batch.usage_summary(outcomes, lambda cid: cid.split("-")[0])
    with open(OUT / "ledger.jsonl", "a") as f:
        f.write(json.dumps({"tag": tag, "usd": sum(u["usd"] for u in usage.values()), "time": time.time()}) + "\n")
    (OUT / f"outcomes_{tag}.json").write_text(json.dumps(outcomes))
    return outcomes


def saved(tag):
    path = OUT / f"outcomes_{tag}.json"
    return json.loads(path.read_text()) if path.exists() else None


def recover():
    """A submission recorded as pending without saved outcomes (the job stopped while waiting): fetch its batches
    instead of sending again, and record the actual dollars."""
    api = claude_batch.client()
    batches = [json.loads(line) for line in open(OUT / "batches.jsonl")] if (OUT / "batches.jsonl").exists() else []
    for tag, e in ledger().items():
        if not e.get("pending") or saved(tag) is not None:
            continue
        outcomes = {}
        for b in [b for b in batches if b["tag"] in (tag, f"{tag}_retry")]:
            while (batch := api.messages.batches.retrieve(b["batch_id"])).processing_status != "ended":
                time.sleep(claude_batch.POLL_SECONDS)
            for result in api.messages.batches.results(b["batch_id"]):
                o = claude_batch._outcome(result)
                if result.custom_id not in outcomes or o["status"] == "ok":
                    outcomes[result.custom_id] = o
        if not outcomes:
            continue
        usage = claude_batch.usage_summary(outcomes, lambda cid: cid.split("-")[0])
        with open(OUT / "ledger.jsonl", "a") as f:
            f.write(json.dumps({"tag": tag, "usd": sum(u["usd"] for u in usage.values()), "time": time.time(), "recovered": True}) + "\n")
        (OUT / f"outcomes_{tag}.json").write_text(json.dumps(outcomes))
        print(f"recovered {tag}: {len(outcomes)} results", flush=True)


# ---- stages ----
def run():
    OUT.mkdir(parents=True, exist_ok=True)
    recover()
    cs = [v["concept"] for v in concepts()]
    ex = {c: examples(c) for c in cs}

    # Names (G49): exact input counts
    name_reqs = [(f"name{side}-{c}-{SIDES[side]}-0", naming_request(c, ex[c], side))
                 for c in cs for side in SIDES if ex[c]["naming"][side] is not None]
    if saved("names") is None:
        counts = count_inputs(name_reqs)
        send(name_reqs, "names", counts)
    outcomes = saved("names")
    names, name_out = {}, {}
    for cid, o in outcomes.items():
        purpose, c, _, _ = cid.split("-")
        names.setdefault(int(c), {})[purpose[len("name"):]] = (o["answer"] or {}).get("explanation")
        name_out[cid] = (o["usage"] or {}).get("output_tokens", CAPS["name"])
    (OUT / "names.json").write_text(json.dumps(names, indent=1, ensure_ascii=False))

    # Quiz (G49): every available name on every testable side; bounds as F7b
    quiz, key = [], {}
    for c in cs:
        for side in SIDES:
            if ex[c]["quiz_firing"][side] is None or ex[c]["quiz_nonfiring"][side] is None:
                continue
            for src in SIDES:
                if names.get(c, {}).get(src):
                    r, k = quiz_requests(c, ex[c], side, src, names[c][src])
                    quiz += r
                    key.update(k)
    rng = np.random.default_rng([config.SEED, 47, 200])
    sample = [quiz[i] for i in rng.choice(len(quiz), size=min(200, len(quiz)), replace=False)]
    counted = count_inputs([(f"sample_{cid}", p) for cid, p in sample])  # F7b: 200 seeded prompts, names included
    base_q = max(counted[f"sample_{cid}"] for cid, _ in sample)
    longest_name = max(name_out.values())
    bounds = {cid: base_q + longest_name + SLACK_TOKENS for cid, _ in quiz}
    for i in range(0, len(quiz), QUIZ_CHUNK):
        tag = f"quiz_{i // QUIZ_CHUNK}"
        if saved(tag) is None:
            send(quiz[i:i + QUIZ_CHUNK], tag, bounds)
    (OUT / "quiz_key.json").write_text(json.dumps(key))

    # Judge (G49, N10)
    judge, jkey = judge_requests(names, cs)
    if saved("judge") is None and judge:
        counted = count_inputs([(f"sample_{cid}", p) for cid, p in judge[:20]])
        base_j = max(counted[f"sample_{cid}"] for cid, _ in judge[:20])
        send(judge, "judge", {cid: base_j + 2 * longest_name + SLACK_TOKENS for cid, _ in judge})
    (OUT / "judge_key.json").write_text(json.dumps(jkey))
    analyze()


def analyze():
    """G50: four scores per concept, cross gaps, agree flag, judge; per group shares."""
    info = {v["concept"]: v for v in concepts()}
    names = {int(c): v for c, v in json.loads((OUT / "names.json").read_text()).items()}
    key = json.loads((OUT / "quiz_key.json").read_text())
    outcomes = {}
    for path in sorted(OUT.glob("outcomes_quiz_*.json")):
        outcomes.update(json.loads(path.read_text()))
    rows = {}
    for cid, windows in key.items():
        o = outcomes.get(cid, {"status": "missing", "answer": None})
        answers = (o.get("answer") or {}).get("answers")
        ok = o.get("status") == "ok" and answers is not None and len(answers) == len(windows)
        src, c, side, _ = cid.split("-")
        rows.setdefault((int(c), src, side), []).extend({**w, "answer": a if ok else None} for w, a in zip(windows, answers if ok else [None] * len(windows)))
    score = {}
    for (c, src, side), r in rows.items():
        done = [x for x in r if x["answer"] is not None]
        score[(c, src, side)] = round(float(balanced_accuracy(done)), 4) if len(done) >= MIN_ANSWERED * len(r) else None
    judge = {}
    jkey = json.loads((OUT / "judge_key.json").read_text()) if (OUT / "judge_key.json").exists() else {}
    for cid, o in (saved("judge") or {}).items():
        judge.setdefault(jkey[cid]["concept"], {})[jkey[cid]["kind"]] = (o.get("answer") or {}).get("same")
    per = []
    for c, v in info.items():
        s = {f"{src}_name_on_{side}": score.get((c, src, side)) for src in ("qd", "qr") for side in ("V", "R")}
        s = {k.replace("qd", "dolma").replace("qr", "rollout").replace("_V", "_dolma").replace("_R", "_rollouts"): x for k, x in s.items()}
        gap_d = s["dolma_name_on_dolma"] - s["rollout_name_on_dolma"] if None not in (s["dolma_name_on_dolma"], s["rollout_name_on_dolma"]) else None
        gap_r = s["rollout_name_on_rollouts"] - s["dolma_name_on_rollouts"] if None not in (s["rollout_name_on_rollouts"], s["dolma_name_on_rollouts"]) else None
        agree = None if None in (gap_d, gap_r) else bool(gap_d <= AGREE_GAP and gap_r <= AGREE_GAP)
        per.append({**{k: v.get(k) for k in ("concept", "set", "kind", "rank_train", "ln_ratio", "mass_change")},
                    "dolma_name": names.get(c, {}).get("dolma"), "rollout_name": names.get(c, {}).get("rollout"), **s,
                    "gap_on_dolma": None if gap_d is None else round(gap_d, 4), "gap_on_rollouts": None if gap_r is None else round(gap_r, 4),
                    "agree": agree, "judge_same": judge.get(c, {}).get("true"), "judge_control_same": judge.get(c, {}).get("control")})
    groups = {}
    for kind in ("gainer", "loser", "control"):
        g = [p for p in per if p["kind"] == kind]
        flagged = [p["agree"] for p in g if p["agree"] is not None]
        groups[kind] = {"concepts": len(g), "scored": len(flagged), "agree_share": round(float(np.mean(flagged)), 4) if flagged else None,
                        "mean_gap_on_dolma": round(float(np.mean([p["gap_on_dolma"] for p in g if p["gap_on_dolma"] is not None] or [np.nan])), 4),
                        "mean_gap_on_rollouts": round(float(np.mean([p["gap_on_rollouts"] for p in g if p["gap_on_rollouts"] is not None] or [np.nan])), 4),
                        "judge_same_true": round(float(np.mean([p["judge_same"] for p in g if p["judge_same"] is not None] or [np.nan])), 4),
                        "judge_same_control": round(float(np.mean([p["judge_control_same"] for p in g if p["judge_control_same"] is not None] or [np.nan])), 4)}
    summary = {"limit_usd": LIMIT_USD, "spent_usd": round(spent(), 4), "agree_gap": AGREE_GAP, "groups": groups,
               "judge_note": "unvalidated (Exp 1 N10 hand labels skipped); not used for the agree flag (G50)", "concepts": per}
    (settings.RESULTS / f"{RUN}_moved_summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    md = [f"# Exp 2: names of the concepts that moved (design.md G47-G52)\n\nSpent ${summary['spent_usd']:.2f} of the ${LIMIT_USD:.0f} limit. "
          f"Agree = both cross gaps ≤ {AGREE_GAP} (G50). Judge unvalidated (G50).\n\n| group | concepts | scored | agree share | mean gap on Dolma | mean gap on rollouts | judge same (true / control) |\n|---|---|---|---|---|---|---|\n"]
    for k, g in groups.items():
        md.append(f"| {k} | {g['concepts']} | {g['scored']} | {g['agree_share']} | {g['mean_gap_on_dolma']} | {g['mean_gap_on_rollouts']} | {g['judge_same_true']} / {g['judge_same_control']} |\n")
    md.append("\n| concept | kind | set | rank | ln ratio | Dolma name | rollout name | D name on D | R name on D | R name on R | D name on R | agree | judge |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for p in sorted(per, key=lambda p: (p["kind"], p["set"], p["concept"])):
        clean = lambda t: (t or "–").replace("|", "/").replace("\n", " ")  # noqa: E731
        md.append(f"| {p['concept']} | {p['kind']} | {p['set']} | {p['rank_train']} | {p['ln_ratio'] if p['ln_ratio'] is None else round(p['ln_ratio'], 2)} | "
                  f"{clean(p['dolma_name'])} | {clean(p['rollout_name'])} | {p['dolma_name_on_dolma']} | {p['rollout_name_on_dolma']} | "
                  f"{p['rollout_name_on_rollouts']} | {p['dolma_name_on_rollouts']} | {p['agree']} | {p['judge_same']} |\n")
    (settings.RESULTS / f"{RUN}_moved_summary.md").write_text("".join(md))
    print(json.dumps({k: v for k, v in summary.items() if k != "concepts"}, indent=1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["run", "analyze"])
    args = parser.parse_args()
    run() if args.stage == "run" else analyze()
    sys.exit(0)
