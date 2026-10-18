"""Pile vs Dolma faithfulness test (rows F1-F7). Calls the Anthropic API except in --dry-run and analyze.

Usage:
  python s11_faith.py count             # builds every request, counts input tokens (free endpoint), no sending
  python s11_faith.py names             # Pile name and Dolma name per concept (F4a, b)
  python s11_faith.py quiz              # detection quiz on Dolma web V, once per name, same windows (F4c)
  python s11_faith.py judge             # Pile name vs Dolma name, and the negative control (F4d)
  python s11_faith.py analyze           # F5 numbers (no API)
Windows come from DATA/full/examples_F (Dolma web T1, V) and DATA/pile/examples_F (Pile-CC), built by s06.
Everything the API returns is saved under DATA/full/labels/faith/; results/faith_*.json hold ids, counts, scores, costs.
Every submission passes the F7 guard: dollars already spent plus the worst case of the requests about to be sent
must stay at or below LIMIT_USD, or nothing is sent.
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor

import anthropic
import config
import numpy as np
import pandas as pd

import claude_batch
import prompts
from s06_examples import ALL_SUBSETS, pick_concepts
from s07_names import naming_request
from s08_quiz import JUDGE, MIN_ANSWERED, balanced_accuracy, quiz_requests

LIMIT_USD = 30.0  # F7: Angela's hard limit for the whole F run
CAPS = {"name": 1_000, "quiz": 200, "judge": 300}  # F7: max output tokens per request type
QUIZ_CHUNK = 1_600  # F7: quiz requests per submission (40 concepts x 2 names x 20 prompts)
SLACK_TOKENS = 300  # F7b: added to each quiz and judge input bound
OUT = config.DATA / "full" / "labels" / "faith"
NAME_SOURCES = {"pile": ("pile", "PileCC"), "dolma": ("full", "T1")}  # F2: run and subset each name is written from


def examples(run, c):
    return json.loads((config.DATA / run / "examples_F" / f"{c}.json").read_text())


def concepts():
    return [int(c) for c in pick_concepts("faith", config.DATA / "full")]


def name_requests():
    """F4a, b: one request per concept and name source, the N4 prompt on the 40 F2 windows."""
    out = []
    for c in concepts():
        for src, (run, subset) in NAME_SOURCES.items():
            p = naming_request(c, subset, examples(run, c), max_tokens=CAPS["name"])
            out.append((f"name{src}-{c}-{subset}-0", p))
    return out


def load_names():
    names = json.loads((OUT / "names.json").read_text())
    return {int(c): v for c, v in names.items()}


def quiz_request_list(names, placeholder=False):
    """F4c: both names quizzed on the same 100 Dolma web V windows (same seed, so same prompts apart from the name)."""
    out, key = [], {}
    for c in concepts():
        ex = examples("full", c)
        for src in NAME_SOURCES:
            name = "Placeholder name for token counting." if placeholder else names.get(c, {}).get(src)
            if name is None:
                continue  # a failed name is skipped and listed in the summary
            r, k = quiz_requests(c, "V", "detection", name, ex, False, purpose=f"quiz{src}", max_tokens=CAPS["quiz"])
            out += r
            key.update(k)
    return out, key


def judge_request_list(names, placeholder=False):
    """F4d: the true pair (Pile name, Dolma name) in seeded order, and a negative control: the Pile name vs the
    Dolma name of another sampled concept, drawn with default_rng([0, 6100]) as a permutation with no fixed point."""
    cs = concepts()
    rng = np.random.default_rng([config.SEED, 6100])
    while True:
        perm = rng.permutation(len(cs))
        if not np.any(perm == np.arange(len(cs))):
            break
    other = {c: cs[j] for c, j in zip(cs, perm)}
    out, key = [], {}
    for c in cs:
        get = (lambda cc, s: "Placeholder name.") if placeholder else (lambda cc, s: names.get(cc, {}).get(s))
        for kind, b_concept in (("true", c), ("control", other[c])):
            a, b = get(c, "pile"), get(b_concept, "dolma")
            if a is None or b is None:
                continue
            swap = bool(np.random.default_rng([config.SEED, c, 40, int(kind == "control")]).integers(2))
            system, messages = prompts.judge_messages(*((b, a) if swap else (a, b)))
            cid = f"judge{kind}-{c}-{b_concept}-0"
            out.append((cid, claude_batch.params(JUDGE, system, messages, prompts.JUDGE_SCHEMA, max_tokens=CAPS["judge"])))
            key[cid] = {"concept": c, "kind": kind, "other": b_concept, "swapped": swap}
    return out, key


def count_tokens(requests):
    """Input tokens per request from the free counting endpoint, cached in OUT/token_counts.json by custom_id."""
    path = OUT / "token_counts.json"
    cache = json.loads(path.read_text()) if path.exists() else {}
    todo = [(cid, p) for cid, p in requests if cid not in cache]
    api = claude_batch.client()

    def one(item):
        cid, p = item
        for attempt in range(8):
            try:
                n = api.messages.count_tokens(model=p["model"], system=p["system"], messages=p["messages"],
                                              output_config={"format": p["output_config"]["format"]}).input_tokens
                return cid, n
            except anthropic.RateLimitError:
                time.sleep(2 ** attempt)
        raise RuntimeError(f"token count failed for {cid}")

    with ThreadPoolExecutor(8) as pool:
        for i, (cid, n) in enumerate(pool.map(one, todo)):
            cache[cid] = n
            if i % 500 == 499:
                path.write_text(json.dumps(cache))
    path.write_text(json.dumps(cache))
    return cache


def input_bounds(requests, key, stage):
    """F7b: an upper bound on each quiz or judge request's input tokens without counting all 9,600 quiz prompts.
    Input = fixed prompt text and windows (largest count over the placeholder sample from `count`) + the name(s),
    and a name has at most as many tokens as its naming response's output tokens; plus SLACK_TOKENS."""
    counted = json.loads((OUT / "token_counts.json").read_text())
    base = max(n for cid, n in counted.items() if cid.startswith(f"placeholder_{stage}"))
    name_out = json.loads((OUT / "name_output_tokens.json").read_text())

    def name_tokens(c, src):
        sub = NAME_SOURCES[src][1]
        return name_out[f"name{src}-{c}-{sub}-0"]
    out = {}
    for cid, _ in requests:
        if stage == "quiz":
            src, c = cid.split("-")[0][len("quiz"):], cid.split("-")[1]
            out[cid] = base + name_tokens(c, src) + SLACK_TOKENS
        else:
            k = key[cid]
            out[cid] = base + name_tokens(k["concept"], "pile") + name_tokens(k["other"], "dolma") + SLACK_TOKENS
    return out


def spent():
    path = OUT / "ledger.jsonl"
    return sum(json.loads(line)["usd"] for line in open(path)) if path.exists() else 0.0


def make_guard(counts):
    def guard(requests):
        missing = [cid for cid, _ in requests if cid not in counts]
        if missing:
            raise RuntimeError(f"{len(missing)} requests have no token count; run `count` first")
        worst = sum(claude_batch.worst_case(p, counts[cid]) for cid, p in requests)
        print(f"guard: spent ${spent():.2f} + worst case ${worst:.2f} for {len(requests)} requests "
              f"(limit ${LIMIT_USD:.0f})", flush=True)
        if spent() + worst > LIMIT_USD:
            raise RuntimeError("stopped by the F7 guard: this submission could take the run over the limit")
    return guard


def send(requests, tag, counts):
    """Send through the guard and record the dollars actually used in the ledger."""
    outcomes = claude_batch.send(requests, OUT, tag, guard=make_guard(counts))
    usage = claude_batch.usage_summary(outcomes, lambda cid: cid.split("-")[0])
    with open(OUT / "ledger.jsonl", "a") as f:
        f.write(json.dumps({"tag": tag, "usd": sum(u["usd"] for u in usage.values()), "time": time.time()}) + "\n")
    return outcomes, usage


def write_summary(name, data):
    (config.RESULTS / f"faith_{name}_summary.json").write_text(json.dumps(data, indent=2))
    print(json.dumps({k: v for k, v in data.items() if k not in ("scores", "pairs")}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["count", "names", "quiz", "judge", "analyze"])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    if args.stage == "count":
        names_r = name_requests()
        quiz_r, _ = quiz_request_list({}, placeholder=True)
        judge_r, _ = judge_request_list({}, placeholder=True)
        counts = count_tokens(names_r)  # names are final; quiz and judge counts use placeholder names, see F7b
        sample_q = [quiz_r[i] for i in np.random.default_rng([config.SEED, 6200]).choice(len(quiz_r), 200, replace=False)]
        counts_q = count_tokens([(f"placeholder_{cid}", p) for cid, p in sample_q])  # keys placeholder_quiz...
        counts_j = count_tokens([(f"placeholder_{cid}", p) for cid, p in judge_r[:20]])  # keys placeholder_judge...
        q = np.array([counts_q[f"placeholder_{cid}"] for cid, _ in sample_q])
        j = np.array([counts_j[f"placeholder_{cid}"] for cid, _ in judge_r[:20]])
        n = np.array([counts[cid] for cid, _ in names_r])
        report = {"requests": {"name": len(names_r), "quiz": len(quiz_r), "judge": len(judge_r)},
                  "input_tokens": {"name_mean": float(n.mean()), "name_max": int(n.max()),
                                   "quiz_placeholder_sample_mean": float(q.mean()), "quiz_placeholder_sample_max": int(q.max()),
                                   "judge_placeholder_mean": float(j.mean())},
                  "worst_case_usd": {"name": round(sum(claude_batch.worst_case(p, counts[cid]) for cid, p in names_r), 2)}}
        print(json.dumps(report, indent=2))
        print(f"\n===== sample naming prompt ({names_r[1][0]}), last user message =====\n{names_r[1][1]['messages'][-1]['content'][:1500]}")
        return

    if args.stage == "names":
        requests = name_requests()
        counts = json.loads((OUT / "token_counts.json").read_text())
        outcomes, usage = send(requests, "names", counts)
        names = {}
        for cid, o in outcomes.items():
            purpose, c, subset, _ = cid.split("-")
            names.setdefault(c, {})[purpose[len("name"):]] = (o["answer"] or {}).get("explanation")
        (OUT / "names.json").write_text(json.dumps(names, indent=1, ensure_ascii=False))
        (OUT / "name_output_tokens.json").write_text(json.dumps(  # F7b: bounds a name's length in later prompts
            {cid: (o["usage"] or {}).get("output_tokens", CAPS["name"]) for cid, o in outcomes.items()}))
        statuses = {s: sum(o["status"] == s for o in outcomes.values()) for s in {o["status"] for o in outcomes.values()}}
        write_summary("names", {"requests": len(requests), "statuses": statuses, "usage": usage, "spent_total": spent()})
        return

    names = load_names()
    if args.stage in ("quiz", "judge"):
        requests, key = (quiz_request_list if args.stage == "quiz" else judge_request_list)(names)
        counts = input_bounds(requests, key, args.stage)  # F7b
        chunk = QUIZ_CHUNK if args.stage == "quiz" else len(requests)
        outcomes, usage = {}, {}
        for i in range(0, len(requests), chunk):
            o, u = send(requests[i:i + chunk], f"{args.stage}_{i // chunk}", counts)
            outcomes.update(o)
            for t, v in u.items():
                usage.setdefault(t, []).append(v)
        rows = []
        for cid, o in outcomes.items():
            if args.stage == "judge":
                rows.append({"custom_id": cid, **key[cid], "same": (o["answer"] or {}).get("same"), "status": o["status"]})
                continue
            answers = (o["answer"] or {}).get("answers")
            ok = o["status"] == "ok" and answers is not None and len(answers) == len(key[cid])
            purpose, c, _, k = cid.split("-")
            rows += [{"name": purpose[len("quiz"):], "concept": int(c), "prompt": int(k), **w,
                      "answer": a if ok else None, "status": o["status"] if o["status"] != "ok" or ok else "wrong_number"}
                     for w, a in zip(key[cid], answers if ok else [None] * len(key[cid]))]
        pd.DataFrame(rows).to_parquet(OUT / f"{args.stage}_answers.parquet", index=False)
        statuses = {s: sum(o["status"] == s for o in outcomes.values()) for s in {o["status"] for o in outcomes.values()}}
        write_summary(args.stage, {"requests": len(requests), "statuses": statuses, "usage": usage, "spent_total": spent()})
        return

    analyze()


def analyze():
    """F5: per class, mean detection score of each name, the paired gap with a bootstrap 95% interval, and the
    judge's 'same' rate for true pairs and negative controls. No API."""
    sample = pd.read_parquet(config.DATA / "full" / "faith_sample.parquet").set_index("concept")["class_web"]
    a = pd.read_parquet(OUT / "quiz_answers.parquet")
    scores = {}
    for (name, c), g in a.groupby(["name", "concept"]):
        done = g[g["answer"].notna()]
        ok = len(done) >= MIN_ANSWERED * len(g)
        scores.setdefault(int(c), {})[name] = balanced_accuracy(done.to_dict("records")) if ok else None
    table = pd.DataFrame([{"concept": c, "class": sample[c], "pile": v.get("pile"), "dolma": v.get("dolma")}
                          for c, v in scores.items()])
    out = {"classes": {}}
    for cls, g in table.groupby("class"):
        paired = g.dropna(subset=["pile", "dolma"])
        gap = (paired["dolma"] - paired["pile"]).to_numpy()
        rng = np.random.default_rng(config.SEED)
        boots = [rng.choice(gap, len(gap)).mean() for _ in range(10_000)]
        out["classes"][cls] = {"concepts_scored": int(len(paired)), "pile_name_mean": round(float(paired["pile"].mean()), 4),
                               "dolma_name_mean": round(float(paired["dolma"].mean()), 4),
                               "gap_mean": round(float(gap.mean()), 4),
                               "gap_ci95": [round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)]}
    judge_path = OUT / "judge_answers.parquet"
    if judge_path.exists():
        j = pd.read_parquet(judge_path)
        j["class"] = j["concept"].map(sample)
        out["judge_same_rate"] = {f"{cls}_{kind}": round(float(g["same"].dropna().mean()), 4)
                                  for (cls, kind), g in j.groupby(["class", "kind"])}
        out["judge_note"] = "used only if the judge passes N10 (Angela's 100 labels, kappa >= 0.6)"
    out["scores"] = table.to_dict("records")
    write_summary("analysis", out)


if __name__ == "__main__":
    main()
