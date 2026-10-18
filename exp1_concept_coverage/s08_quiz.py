"""Quiz the T1 name on held-out windows, and judge whether two names match (rows 18, 21, N2, N5-N8, N10, N11, N15).

Usage:
  python s08_quiz.py quiz  --run full --concepts pilot:20 --tag pilot --subset T2 [--neighbour] [--dry-run]
  python s08_quiz.py judge --run full --concepts pilot:20 --tag pilot --pair T2 [--dry-run]
The T1 names come from DATA/<run>/labels/<tag>/names.json (s07). --subset V and --pair V touch V and need --final
("How V is protected"). Writes requests, raw results and per-window answers to DATA/<run>/labels/<tag>/ and counts,
scores and costs (no text) to results/<run>_<quiz|judge>_<tag>_<setting>_summary.json.
"""
import argparse
import json
import math

import config
import numpy as np

import claude_batch
import prompts
from s06_examples import QUIZ_SUBSETS, SUBSETS, pick_concepts
from s07_names import THRESHOLD, mark, pieces_of

SCORER = "claude-sonnet-5-5"  # N2
JUDGE = "claude-opus-5-5"  # N2
PER_PROMPT = 5  # N5
N_PER_SIDE = 50  # E3: 50 firing and 50 non-firing windows per quiz
MIN_ANSWERED = 0.9  # N7: a score needs at least 90 of 100 windows answered
KINDS = {"detection": 0, "fuzz": 1}
PLACEHOLDER = "Placeholder name used only to count tokens in a dry run."


def quiz_text(kind, window, n_random, rng):
    """N5: detection shows plain text. N6, N13c: fuzzing marks tokens >= 0.3 x the window max in firing windows and
    n_random uniformly drawn tokens in non-firing windows."""
    pieces = pieces_of(window)
    if kind == "detection":
        return "".join(pieces)
    acts = window["acts"]
    if max(acts) > 0:
        return mark(pieces, lambda i: acts[i] >= THRESHOLD * max(acts))
    nonempty = [i for i, p in enumerate(pieces) if p]
    chosen = set(rng.choice(nonempty, size=min(n_random, len(nonempty)), replace=False).tolist())
    return mark(pieces, lambda i: i in chosen)


def quiz_requests(c, subset, kind, explanation, ex, neighbour, purpose=None, max_tokens=claude_batch.MAX_TOKENS):
    """20 prompts of 5 windows for one concept, subset and quiz kind; returns requests and the window key.
    F4: the F run quizzes two names on the same windows (same seed) and labels them with its own purpose."""
    firing = ex["quiz_firing"][subset]
    nonfiring = ex["quiz_nonfiring_neighbour" if neighbour else "quiz_nonfiring"][subset]
    windows = [(w, 1) for w in firing] + [(w, 0) for w in nonfiring]
    n_random = math.ceil(np.mean([sum(a > 0 for a in w["acts"]) for w in firing]))  # delphi mean_n_activations_ceil
    seed = [config.SEED, c, SUBSETS.index(subset), 20 + KINDS[kind] + 10 * neighbour]
    order = np.random.default_rng(seed).permutation(len(windows))
    mark_rng = np.random.default_rng(seed + [1])
    texts = [quiz_text(kind, windows[j][0], n_random, mark_rng) for j in order]
    purpose = purpose or kind + ("_neighbour" if neighbour else "")
    requests, key = [], {}
    for k in range(math.ceil(len(order) / PER_PROMPT)):
        idx = range(k * PER_PROMPT, min((k + 1) * PER_PROMPT, len(order)))
        examples = "\n".join(f"Example {i}: {texts[j]}" for i, j in enumerate(idx))  # N13d: numbered from 0
        system, messages = prompts.quiz_messages(kind, explanation, examples)
        cid = f"{purpose}-{c}-{subset}-{k}"
        requests.append((cid, claude_batch.params(SCORER, system, messages, prompts.ANSWERS_SCHEMA, max_tokens=max_tokens)))
        key[cid] = [{"doc_id": windows[order[j]][0]["doc_id"], "start": windows[order[j]][0]["start"],
                     "fires": windows[order[j]][1]} for j in idx]
    return requests, key


def balanced_accuracy(rows):
    """N7: mean of the hit rate on firing windows and the correct-rejection rate on non-firing windows."""
    pos = [r["answer"] == 1 for r in rows if r["fires"] == 1]
    neg = [r["answer"] == 0 for r in rows if r["fires"] == 0]
    return (np.mean(pos) + np.mean(neg)) / 2 if pos and neg else None


def dry_run(requests):
    cid, p = requests[0]
    print(f"\n===== {cid}: system =====\n{p['system']}\n===== last user message =====\n{p['messages'][-1]['content']}")
    api = claude_batch.client()
    counts = [api.messages.count_tokens(model=p["model"], system=p["system"], messages=p["messages"]).input_tokens
              for _, p in requests[:5]]
    print(f"\ninput tokens of the first {len(counts)} requests (free count): {counts}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["quiz", "judge"])
    parser.add_argument("--run", required=True)
    parser.add_argument("--concepts", required=True, help="as in s06, e.g. pilot:20")
    parser.add_argument("--tag", required=True, help="folder under DATA/<run>/labels/ holding names.json")
    parser.add_argument("--subset", choices=QUIZ_SUBSETS, help="quiz: windows to quiz the T1 name on")
    parser.add_argument("--neighbour", action="store_true", help="quiz: N15 non-firing windows, detection only")
    parser.add_argument("--pair", choices=QUIZ_SUBSETS, help="judge: compare the T1 name with this subset's name")
    parser.add_argument("--final", action="store_true", help="required for anything that reads V")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    target = args.subset if args.mode == "quiz" else args.pair
    if target is None:
        parser.error("quiz needs --subset, judge needs --pair")
    if target == "V" and not args.final:
        parser.error("V is read only by the final run: add --final")
    if args.neighbour and (args.mode != "quiz" or target != "T2"):
        parser.error("neighbour windows exist for the T2 quiz only (N15)")
    run_dir = config.DATA / args.run
    out_dir = run_dir / "labels" / args.tag
    names_path = out_dir / "names.json"
    names = json.loads(names_path.read_text()) if names_path.exists() else {}
    if not names and not args.dry_run:
        raise FileNotFoundError(f"{names_path}: run s07 first")

    def name(c, s):
        return names.get(str(c), {}).get(s, {}).get("explanation") or (PLACEHOLDER if args.dry_run else None)

    requests, key, skipped = [], {}, {"no_name": [], "short_nonfiring": []}
    for c in map(int, pick_concepts(args.concepts, run_dir)):
        ex = json.loads((run_dir / "examples" / f"{c}.json").read_text())
        if args.mode == "judge":
            a, b = name(c, "T1"), name(c, target)
            if a is None or b is None:
                skipped["no_name"].append(c)
                continue
            swap = bool(np.random.default_rng([config.SEED, c, SUBSETS.index(target), 40]).integers(2))  # N10
            pair = (b, a) if swap else (a, b)
            system, messages = prompts.judge_messages(*pair)
            cid = f"judge-{c}-T1{target}-0"
            requests.append((cid, claude_batch.params(JUDGE, system, messages, prompts.JUDGE_SCHEMA)))
            key[cid] = {"swapped": swap}
            continue
        explanation = name(c, "T1")
        if explanation is None:
            skipped["no_name"].append(c)
            continue
        if args.neighbour and len(ex["quiz_nonfiring_neighbour"][target] or []) < N_PER_SIDE:
            skipped["short_nonfiring"].append(c)  # compared only on concepts with full sets under both settings
            continue
        for kind in (["detection"] if args.neighbour else KINDS):
            r, k = quiz_requests(c, target, kind, explanation, ex, args.neighbour)
            requests += r
            key.update(k)
    setting = (f"{args.mode}_T1{target}" if args.mode == "judge" else
               f"quiz_T1{target}" + ("_neighbour" if args.neighbour else ""))
    print(f"{len(requests)} requests ({setting}); skipped: {skipped}")
    if args.dry_run:
        dry_run(requests)
        return

    outcomes = claude_batch.send(requests, out_dir, f"{setting}_{args.tag}")
    summary = {"run": args.run, "tag": args.tag, "concepts": args.concepts, "setting": setting, "skipped": skipped,
               "usage": claude_batch.usage_summary(outcomes, lambda cid: cid.split("-")[0])}
    if args.mode == "judge":
        same = {cid: (o["answer"] or {}).get("same") for cid, o in outcomes.items()}
        with open(out_dir / f"judge_{setting}_{args.tag}.jsonl", "w") as f:
            for cid, s in same.items():
                f.write(json.dumps({"custom_id": cid, "same": s, **key[cid]}) + "\n")
        answered = [s for s in same.values() if s is not None]
        summary["judge"] = {"pairs": len(same), "answered": len(answered), "same": sum(answered)}
    else:
        rows, failed = [], {}
        for cid, o in outcomes.items():
            answers = (o["answer"] or {}).get("answers")
            if o["status"] != "ok" or answers is None or len(answers) != len(key[cid]):  # N7: dropped and counted
                failed[cid] = o["status"] if o["status"] != "ok" else "wrong_number_of_answers"
                answers = [None] * len(key[cid])
            purpose, c, subset, k = cid.split("-")
            rows += [{"purpose": purpose, "concept": int(c), **w, "answer": a} for w, a in zip(key[cid], answers)]
        with open(out_dir / f"answers_{setting}_{args.tag}.jsonl", "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)
        scores = {}
        for (purpose, c) in sorted({(r["purpose"], r["concept"]) for r in rows}):
            mine = [r for r in rows if r["purpose"] == purpose and r["concept"] == c]
            done = [r for r in mine if r["answer"] is not None]
            ok = len(done) >= MIN_ANSWERED * len(mine)
            scores.setdefault(str(c), {})[purpose] = {
                "windows": len(mine), "answered": len(done),
                "balanced_accuracy": round(balanced_accuracy(done), 4) if ok else None}
        summary["failed_prompts"] = failed
        summary["scores"] = scores
    path = config.RESULTS / f"{args.run}_{setting}_{args.tag}_summary.json"
    path.write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "scores"}, indent=2))


if __name__ == "__main__":
    main()
