"""Names for SAE concepts, written from their example windows (rows 17, N2-N4, N8, N13). Calls the Anthropic API.

Usage: python s07_names.py --run full --concepts pilot:20 --tag pilot [--dry-run]
Reads DATA/<run>/examples/<concept>.json (s06). Writes DATA/<run>/labels/<tag>/ (requests, raw results, names.json)
and results/<run>_naming_<tag>_summary.json. --dry-run builds every prompt, prints one, counts input tokens with the
free token counter and sends nothing.
"""
import argparse
import functools
import json
import math

import config
import numpy as np

import claude_batch
import prompts
from s06_examples import SUBSETS, pick_concepts

LABELER = "claude-opus-5-5"  # N2
THRESHOLD = 0.3  # N4: tokens above 0.3 x the window's max are marked (delphi explainer)
MAX_LISTED = 10  # N13b


@functools.cache
def tokenizer():
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)


def pieces_of(window):
    """N13g: per-token text rebuilt from the token ids, with split characters whole."""
    return prompts.token_pieces(tokenizer().convert_ids_to_tokens(window["ids"]))


def mark(pieces, check):
    """Wrap each run of consecutive tokens that pass check(i) in one pair of << >> (delphi _highlight). An empty piece
    (first part of a split character, N13g) never starts a run and does not end one."""
    out, i = "", 0
    while i < len(pieces):
        if check(i) and pieces[i]:
            out += "<<"
            while i < len(pieces) and (check(i) or not pieces[i]):
                out += pieces[i]
                i += 1
            out += ">>"
        else:
            out += pieces[i]
            i += 1
    return out


def naming_example(number, window, subset_max):
    """N4, N13: one numbered example line plus its Activations line (0-10 scale relative to the subset's max)."""
    pieces = pieces_of(window)
    acts = window["acts"]
    cut = THRESHOLD * max(acts)
    text = mark(pieces, lambda i: acts[i] > cut)
    listed = [(p, a) for p, a in zip(pieces, acts) if a > cut and p][:MAX_LISTED]  # "" = first part of a split char
    scaled = [min(10, max(0, math.ceil(10 * a / subset_max))) for _, a in listed]  # delphi normalize_activations
    line = "Activations: " + "".join(f'("{p}" : {n}), ' for (p, _), n in zip(listed, scaled))
    return f"Example {number}: {text}\n{line}"


def naming_request(concept, subset, ex):
    """The 40 windows in a seeded random order (N4), formatted and wrapped in the delphi prompt."""
    windows = ex["naming"][subset]
    order = np.random.default_rng([config.SEED, concept, SUBSETS.index(subset), 10]).permutation(len(windows))
    examples = "\n".join(naming_example(k + 1, windows[j], ex["max_by_subset"][subset]) for k, j in enumerate(order))
    system, messages = prompts.naming_messages(examples)
    return claude_batch.params(LABELER, system, messages, prompts.EXPLANATION_SCHEMA)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--concepts", required=True, help="as in s06, e.g. pilot:20")
    parser.add_argument("--tag", required=True, help="output folder under DATA/<run>/labels/, e.g. pilot")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_dir = config.DATA / args.run
    out_dir = run_dir / "labels" / args.tag

    requests = []
    for c in pick_concepts(args.concepts, run_dir):
        ex = json.loads((run_dir / "examples" / f"{int(c)}.json").read_text())
        for s in SUBSETS:
            if ex["naming"][s] is not None:  # untested concepts are named by N9, not here
                requests.append((f"naming-{int(c)}-{s}-0", naming_request(int(c), s, ex)))
    print(f"{len(requests)} naming requests")

    if args.dry_run:
        cid, p = requests[0]
        print(f"\n===== {cid}: system =====\n{p['system']}\n===== last user message =====\n{p['messages'][-1]['content']}")
        api = claude_batch.client()
        counts = [api.messages.count_tokens(model=p["model"], system=p["system"], messages=p["messages"]).input_tokens
                  for _, p in requests[:5]]
        print(f"\ninput tokens of the first {len(counts)} requests (free count): {counts}")
        return

    outcomes = claude_batch.send(requests, out_dir, f"naming_{args.tag}")
    names = {}
    for cid, o in outcomes.items():
        _, c, s, _ = cid.split("-")
        names.setdefault(c, {})[s] = {"explanation": (o["answer"] or {}).get("explanation"), "status": o["status"],
                                      "tested": True, "model": LABELER}
    (out_dir / "names.json").write_text(json.dumps(names, indent=1, ensure_ascii=False))
    summary = {"run": args.run, "tag": args.tag, "concepts": args.concepts, "requests": len(requests),
               "usage": claude_batch.usage_summary(outcomes, lambda cid: cid.split("-")[0])}
    (config.RESULTS / f"{args.run}_naming_{args.tag}_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
