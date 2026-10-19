"""Topic categories of the 240 named concepts (rows Q1-Q6). Calls the Anthropic API except in count and analyze.

Usage:
  python s13_topics.py count      # builds the scheme request, counts its tokens (free), prints it; sends nothing
  python s13_topics.py scheme     # one Opus request: the category scheme (Q2)
  python s13_topics.py assign     # one request per concept and model, Sonnet and Opus (Q3)
  python s13_topics.py analyze    # Q4 numbers (no API)
Every submission passes a guard: dollars already spent on plan B plus the worst case of the submission must stay at
or below LIMIT_USD (Q5).
"""
import argparse
import json
import time

import config
import numpy as np
import pandas as pd

import claude_batch
import prompts
from s11_faith import count_tokens

LIMIT_USD = 3.00  # Q5
CAPS = {"scheme": 8_000, "assign": 300}  # Q2, Q3
MODELS = {"sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}  # Q3; Opus is primary
OUT = config.DATA / "full" / "labels" / "topics"
NAMES = config.DATA / "full" / "labels" / "faith" / "names.json"


def items():
    """Q1: (concept, Pile name, Dolma name) in a seeded order; the class and concept id are never shown."""
    names = json.loads(NAMES.read_text())
    cs = sorted(int(c) for c in names)
    order = np.random.default_rng([config.SEED, 7000]).permutation(len(cs))
    return [(cs[i], names[str(cs[i])]["pile"], names[str(cs[i])]["dolma"]) for i in order]


def scheme_request():
    system, messages = prompts.topic_scheme_messages([(a, b) for _, a, b in items()])
    return [("scheme-0-all-0", claude_batch.params(MODELS["opus"], system, messages, prompts.TOPIC_SCHEME_SCHEMA,
                                                   max_tokens=CAPS["scheme"]))]


def assign_requests(categories):
    schema = prompts.topic_assign_schema(categories)
    out = []
    for model in MODELS:
        for c, a, b in items():
            system, messages = prompts.topic_assign_messages(categories, a, b)
            out.append((f"assign{model}-{c}-all-0",
                        claude_batch.params(MODELS[model], system, messages, schema, max_tokens=CAPS["assign"])))
    return out


def spent():
    path = OUT / "ledger.jsonl"
    return sum(json.loads(line)["usd"] for line in open(path)) if path.exists() else 0.0


def send(requests, tag):
    counts = count_tokens(requests)  # exact input counts (free endpoint); at most 481 requests in plan B

    def guard(reqs):
        worst = sum(claude_batch.worst_case(p, counts[cid]) for cid, p in reqs)
        print(f"guard: spent ${spent():.2f} + worst case ${worst:.2f} for {len(reqs)} requests (limit ${LIMIT_USD:.2f})",
              flush=True)
        if spent() + worst > LIMIT_USD:
            raise RuntimeError("stopped by the Q5 guard")
    outcomes = claude_batch.send(requests, OUT, tag, guard=guard)
    usage = claude_batch.usage_summary(outcomes, lambda cid: cid.split("-")[0])
    with open(OUT / "ledger.jsonl", "a") as f:
        f.write(json.dumps({"tag": tag, "usd": sum(u["usd"] for u in usage.values()), "time": time.time()}) + "\n")
    return outcomes, usage


def check_scheme(cats):
    names = [c["name"] for c in cats]
    problems = []
    if not 8 <= len(cats) <= 12 + 1:
        problems.append(f"{len(cats)} categories (asked for 8-12 plus the unclear one)")
    if prompts.UNCLEAR not in names:
        problems.append("no 'Diffuse or unclear' category")
    if len(set(names)) != len(names):
        problems.append("duplicate names")
    return problems


def analyze():
    """Q4: per class shares with bootstrap intervals, differences vs middle, κ between runs, agreement-only shares."""
    cats = [c["name"] for c in json.loads((OUT / "scheme.json").read_text())["categories"]]
    a = pd.read_parquet(OUT / "assignments.parquet")
    cls = pd.read_parquet(config.DATA / "full" / "faith_sample.parquet").set_index("concept")["class_web"]
    a["cls"] = a["concept"].map(cls)
    both = a.dropna(subset=["opus", "sonnet"])
    po = (both["opus"] == both["sonnet"]).mean()
    pe = sum((both["opus"] == c).mean() * (both["sonnet"] == c).mean() for c in cats)
    rng = np.random.default_rng(config.SEED)
    out = {"categories": cats, "kappa_opus_vs_sonnet": round(float((po - pe) / (1 - pe)), 4),
           "agreement": round(float(po), 4), "concepts": int(len(a)), "share": {}, "diff_vs_middle": {},
           "share_agreed_only": {}}
    boots = {}
    for k in ("over", "under", "middle"):
        sub = a[a["cls"] == k]
        agreed = sub[sub["opus"] == sub["sonnet"]]
        out["share"][k], out["share_agreed_only"][k] = {}, {}
        for c in cats:
            flags = (sub["opus"] == c).to_numpy(float)
            b = flags[rng.integers(0, len(flags), (10_000, len(flags)))].mean(1)
            boots[(k, c)] = b
            out["share"][k][c] = [round(flags.mean(), 4), round(np.percentile(b, 2.5), 4), round(np.percentile(b, 97.5), 4)]
            out["share_agreed_only"][k][c] = round(float((agreed["opus"] == c).mean()), 4) if len(agreed) else None
    for k in ("over", "under"):
        out["diff_vs_middle"][k] = {}
        for c in cats:
            d = boots[(k, c)] - boots[("middle", c)]
            out["diff_vs_middle"][k][c] = [round(out["share"][k][c][0] - out["share"]["middle"][c][0], 4),
                                           round(np.percentile(d, 2.5), 4), round(np.percentile(d, 97.5), 4)]
    tt = pd.read_parquet(config.DATA / "full" / "token_types.parquet").set_index("concept")["dominant"]
    a["token_type"] = a["concept"].map(tt)
    out["category_by_token_type"] = pd.crosstab(a["opus"], a["token_type"]).to_dict("index")
    (config.RESULTS / "patterns_topics.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("kappa_opus_vs_sonnet", "agreement", "concepts")}, indent=1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["count", "scheme", "assign", "analyze"])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.stage == "count":
        req = scheme_request()
        counts = count_tokens(req)
        cid, p = req[0]
        print(f"===== scheme request: system =====\n{p['system']}\n===== user (first 1,500 characters) =====\n"
              f"{p['messages'][0]['content'][:1500]}\n...\n{p['messages'][0]['content'][-700:]}")
        print(f"\nscheme input tokens {counts[cid]}; worst case ${claude_batch.worst_case(p, counts[cid]):.2f}")
        fake = [{"name": f"Category {i}", "definition": "x" * 120} for i in range(11)] + [
            {"name": prompts.UNCLEAR, "definition": "x" * 120}]
        sample = assign_requests(fake)[:1] + assign_requests(fake)[240:241]
        sc = count_tokens([(f"placeholder_{cid}", p) for cid, p in sample])
        per = {cid: sc[f"placeholder_{cid}"] for cid, _ in sample}
        print(f"assignment input tokens with a placeholder scheme of 12 categories: {per}")
        print(f"===== one assignment request (placeholder scheme) =====\n{sample[0][1]['messages'][0]['content']}")
        return
    if args.stage == "scheme":
        outcomes, usage = send(scheme_request(), "scheme")
        o = outcomes["scheme-0-all-0"]
        if o["status"] != "ok":
            raise RuntimeError(f"scheme request ended with {o['status']}")
        cats = o["answer"]["categories"]
        print(json.dumps(cats, indent=1, ensure_ascii=False))
        problems = check_scheme(cats)
        print("scheme checks:", problems or "ok", "| usage", usage, "| spent", round(spent(), 4))
        (OUT / "scheme.json").write_text(json.dumps({"categories": cats, "problems": problems}, indent=1, ensure_ascii=False))
        return
    if args.stage == "assign":
        cats = json.loads((OUT / "scheme.json").read_text())["categories"]
        reqs, outcomes, usage = assign_requests(cats), {}, {}
        for model in MODELS:  # Q5: one submission per model, so the guard checks the spend in between
            o, u = send([(cid, p) for cid, p in reqs if cid.startswith(f"assign{model}-")], f"assign_{model}")
            outcomes.update(o)
            usage.update(u)
        rows = {}
        for cid, o in outcomes.items():
            model, c, _, _ = cid.split("-")
            rows.setdefault(int(c), {"concept": int(c)})[model[len("assign"):]] = (o["answer"] or {}).get("category")
        pd.DataFrame(list(rows.values())).to_parquet(OUT / "assignments.parquet", index=False)
        statuses = {s: sum(o["status"] == s for o in outcomes.values()) for s in {o["status"] for o in outcomes.values()}}
        print("statuses", statuses, "| usage", usage, "| spent", round(spent(), 4))
        return
    analyze()


if __name__ == "__main__":
    main()
