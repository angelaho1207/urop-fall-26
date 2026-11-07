"""Names of the coverage lists, analysis, cost row and report (design.md G98, G99). Calls the API except where stated.

Usage: python s30_coverage_labels.py check     # free: builds and tests every name request, reports expected dollars; stops on any error
       python s30_coverage_labels.py run       # free key check, names, analysis; resumes from what is saved
       python s30_coverage_labels.py analyze   # no API
       python s30_coverage_labels.py publish   # no API: cost row, report, commit of named files, push
Reads DATA/full_post/coverage/ (s29). Writes requests, raw answers and the ledger to DATA/full_post/labels/coverage/ (pool) and
results/full_post_coverage_{check.json,names.json,summary.json,summary.md}. New names also go to notes/name_cache.json.
"""
import argparse
import json
import re
from datetime import datetime

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np

import claude_batch  # Exp 1
import name_cache
import s27_missing_labels as s27  # preflight, git push
import s13_moved_labels as s13  # the F7 guard, ledger and batch recovery; pointed at this run's folder and limit below
from s07_names import LABELER  # Exp 1 N4
from s12_moved_windows import SETS

LIMIT_USD = 11.14  # G99, Angela: Console balance on 2026-11-07
RUN = "full_post"
IN = settings.DATA / RUN / "coverage"
OUT = settings.DATA / RUN / "labels" / "coverage"
R = settings.RESULTS
NAME_CHUNK = 200  # G67
EXPECTED_NAME = (3.9326 + 5.6993) / 995  # G99: dollars per name measured in the missing run (G93)
SET_ORDER = ["train"] + SETS
LISTS = ["top", "zero", "bottom"]
SOURCE = "exp2 coverage (G98)"
s13.OUT, s13.LIMIT_USD = OUT, LIMIT_USD


def selection():
    return json.loads((IN / "concepts.json").read_text())


def example(folder, side, c):
    return json.loads((IN / folder / f"{side}_{c}.json").read_text())


def name_requests(sel):
    """G98: every new name, Dolma names first, in concept order."""
    out, no_docs = [], []
    jobs = [("train_examples", "train", c, f"nameTrain-{c}-train-0") for c in sel["new_dolma"]]
    jobs += [("rollout_examples", g, int(c), f"namerollout-{c}-{g}-0") for c, g in sel["new_rollout"].items()]
    for folder, side, c, cid in jobs:
        ex = example(folder, side, c)
        if ex["naming"]["rollout"]:
            out.append((cid, s13.naming_request(int(c), ex, "rollout"), len(ex["naming"]["rollout"])))
        else:
            no_docs.append(int(c))
    return out, no_docs


def outcomes():
    out = {}
    for path in sorted(OUT.glob("outcomes_names_*.json")):
        out.update(json.loads(path.read_text()))
    return out


def new_names():
    """{(concept, kind): name} of this run's answers, and the rows for the cache."""
    names, cache_rows = {}, []
    for cid, o in outcomes().items():
        name = (o.get("answer") or {}).get("explanation") if o["status"] == "ok" else None
        if name:
            _, c, third, _ = cid.split("-")
            kind = "dolma" if third == "train" else "rollout"
            names[(int(c), kind)] = name
            cache_rows.append((int(c), name, "dolma", "train all sources", SOURCE, None) if kind == "dolma" else (int(c), name, "rollout", f"rollouts {third}", SOURCE, third))
    return names, cache_rows


def check():
    """G99: free. Every name request is built and tested; expected and worst-case dollars are reported; nothing is sent."""
    OUT.mkdir(parents=True, exist_ok=True)
    s27.preflight()
    s13.recover()
    sel = selection()
    reqs, no_docs = name_requests(sel)
    last = lambda p: p["messages"][-1]["content"]  # noqa: E731
    holds = lambda p, n: f"Example {n}:" in last(p) and f"Example {n + 1}:" not in last(p)  # noqa: E731
    bad = [cid for cid, p, n in reqs if not (p["model"] == LABELER and p["max_tokens"] == s13.CAPS["name"] and p["output_config"]["effort"] == "high" and 1 <= n <= 40 and holds(p, n))]
    rows = sel["rows"]
    per_set = {s: {k: sum(x["set"] == s and x["list"] == k for x in rows) for k in LISTS} for s in SET_ORDER}
    bad += [f"{s} {k}: {n}" for s, d in per_set.items() for k, n in d.items() if k != "zero" and n != 10]
    pairs = [(cid, p) for cid, p, _ in reqs]
    counted = s13.count_inputs(pairs)
    worst = sum(claude_batch.worst_case(p, counted[cid]) for cid, p in pairs)
    spent0 = s13.spent()
    report = {"spent_before_usd": round(spent0, 2), "limit_usd": LIMIT_USD, "names_to_send": len(reqs), "new_dolma": len(sel["new_dolma"]), "new_rollout": len(sel["new_rollout"]),
              "reused_names": len(sel["reused_dolma"]) + len(sel["reused_rollout"]), "names_without_firing_doc": len(no_docs), "names_from_under_40_windows": sum(n < 40 for _, _, n in reqs),
              "list_sizes": per_set, "expected_total_usd": round(spent0 + EXPECTED_NAME * len(reqs), 2), "highest_spent_plus_worst_usd": round(spent0 + worst, 2),
              "failures": len(bad), "first_failures": bad[:10], "date_of_check": datetime.now().strftime("%Y-%m-%d %H:%M")}
    print(json.dumps(report, indent=1))
    (R / f"{RUN}_coverage_check.json").write_text(json.dumps(report, indent=1))
    if bad or spent0 + worst > LIMIT_USD:
        raise SystemExit("check failed")
    print("check passed")


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    s27.preflight()
    s13.recover()
    sel = selection()
    reqs = [(cid, p) for cid, p, _ in name_requests(sel)[0]]
    try:
        for i in range(0, len(reqs), NAME_CHUNK):
            tag, chunk = f"names_{i // NAME_CHUNK}", reqs[i:i + NAME_CHUNK]
            if s13.saved(tag) is None:
                s13.send(chunk, tag, s13.count_inputs(chunk))
            name_cache.add(new_names()[1])
    except SystemExit as stop:  # the guard: analyze what came back, then fail so the mail says so
        print(stop, flush=True)
        analyze(stop=str(stop))
        raise
    analyze()


def clean(t):
    return (t or "–").replace("|", "/").replace("\n", " ")


def analyze(stop=None):
    sel = selection()
    new, _ = new_names()
    dolma = {int(c): (e["name"], f"{e['source']}, {e['windows']}") for c, e in sel["reused_dolma"].items()}
    rollout = {int(c): (e["name"], f"{e['source']}, {e['windows']}") for c, e in sel["reused_rollout"].items()}
    dolma.update({c: (n, f"{SOURCE}, train windows") for (c, k), n in new.items() if k == "dolma"})
    rollout.update({c: (n, f"{SOURCE}, rollouts {sel['new_rollout'].get(str(c))}") for (c, k), n in new.items() if k == "rollout"})
    rows = []
    for x in sel["rows"]:
        name, source = (dolma if x["set"] == "train" or x["list"] == "zero" else rollout).get(x["concept"], (None, None))
        rows.append({**x, "name": name, "name_source": source})
    (R / f"{RUN}_coverage_names.json").write_text(json.dumps(rows, indent=0, ensure_ascii=False))
    selection_summary = json.loads((R / f"{RUN}_coverage_selection_summary.json").read_text())
    statuses = {}
    for o in outcomes().values():
        statuses[o["status"]] = statuses.get(o["status"], 0) + 1
    summary = {"stopped": stop, "spent_usd": round(s13.spent(), 2), "limit_usd": LIMIT_USD, "name_statuses": statuses, "entries_without_name": sum(x["name"] is None for x in rows),
               **{k: selection_summary[k] for k in ("docs", "zero_counts", "zero_fire_outside_matched", "mean_share_staying", "rebuilt_lists_differ", "jaccard_with_dolma_train")},
               "usage": claude_batch.usage_summary(outcomes(), lambda cid: cid.split("-")[0])}
    (R / f"{RUN}_coverage_summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))

    label = {"top": "Top 10 by χ", "zero": "Every concept with χ = 0", "bottom": "Bottom 10 by χ, among χ ≥ e^-5"}
    md = [f"# Coverage lists per set (design.md G95-G99)\n\nNames first. Spent ${summary['spent_usd']:.2f} of ${LIMIT_USD}. Names are not scored. "
          "\"stays\" is the share of 100 reruns (20% of docs dropped) in which the concept stays in its list.\n" + (f"\nStopped: {stop}\n" if stop else "")]
    for s in SET_ORDER:
        md.append(f"\n## {s} ({selection_summary['docs'][s]:,} docs)\n")
        for k in LISTS:
            mine = [x for x in rows if x["set"] == s and x["list"] == k]
            if k == "zero" and not mine:
                md.append(f"\n### {label[k]}: none\n")
                continue
            extra = "fires outside matched docs" if k == "zero" else "stays"
            md.append(f"\n### {label[k]} ({len(mine)})\n\n| rank | concept | χ | {extra} | name |\n|---|---|---|---|---|\n")
            md += [f"| {x['rank']} | {x['concept']} | {x['chi']:.4g} | {('yes' if x['fires_outside_matched'] else 'no') if k == 'zero' else x['stays']} | {clean(x['name'])} |\n" for x in mine]
    md.append("\n## Stability and overlap\n\n| set | χ = 0 concepts | of those, firing outside matched docs | top 10 mean share staying | bottom 10 mean share staying | Jaccard with Dolma train, top | Jaccard with Dolma train, bottom |\n|---|---|---|---|---|---|---|\n")
    for s in SET_ORDER:
        j = selection_summary["jaccard_with_dolma_train"].get(s, {})
        md.append(f"| {s} | {selection_summary['zero_counts'][s]} | {selection_summary['zero_fire_outside_matched'].get(s, '–')} | {selection_summary['mean_share_staying'][s]['top']} | {selection_summary['mean_share_staying'][s]['bottom']} | {j.get('top', '–')} | {j.get('bottom', '–')} |\n")
    (R / f"{RUN}_coverage_summary.md").write_text("".join(md))
    print(json.dumps({k: summary[k] for k in ("stopped", "spent_usd", "name_statuses", "entries_without_name", "mean_share_staying", "jaccard_with_dolma_train")}, indent=1), flush=True)


def publish():
    """After the job: cost row (CLAUDE.md), report, commit, push. No document text enters these files."""
    now = datetime.now()
    usd = s13.spent()
    path = s27.ROOT / "notes" / "api_costs.md"
    text = path.read_text()
    if "G95-G99" not in text:
        total = float(re.search(r"\*\*Total\*\* \| \| \| \*\*([0-9.]+)\*\*", text).group(1))
        row = (f"| {now:%Y-%m-%d} | Exp 2 coverage lists (G95-G99) | Names of the top 10, bottom 10 and chi = 0 concepts of Dolma train and each model | Opus 5.5 | {usd:.2f} | "
               f"`exp2_rollout_gap/results/{RUN}_coverage_summary.json`, pool `exp2/full_post/labels/coverage/ledger.jsonl` |\n")
        path.write_text(re.sub(r"\| \| \*\*Total\*\* \| \| \| \*\*[0-9.]+\*\*", lambda _: f"{row}| | **Total** | | | **{total + usd:.2f}**", text))
    summary = json.loads((R / f"{RUN}_coverage_summary.json").read_text())
    report = (f"\n## {now:%Y-%m-%d %H:%M}, Exp 2 coverage lists: {'stopped' if summary['stopped'] else 'done'} (G95-G99)\n\n"
              f"Written by the job, not checked by hand. Spent ${usd:.2f} of ${LIMIT_USD}. Mean share of each list staying over 100 reruns: {summary['mean_share_staying']}. "
              f"Jaccard with Dolma train: {summary['jaccard_with_dolma_train']}." + (f" Stopped: {summary['stopped']}." if summary["stopped"] else "") + f" Names and tables: `exp2_rollout_gap/results/{RUN}_coverage_summary.md`.\n")
    with open(s27.ROOT / "notes" / "tunnel_reports.md", "a") as f:
        f.write(report)
    s27.push([f"exp2_rollout_gap/results/{RUN}_coverage_{k}" for k in ("selection_summary.json", "check.json", "names.json", "summary.json", "summary.md")] + ["notes/name_cache.json", "notes/api_costs.md", "notes/tunnel_reports.md"],
             f"Exp 2 coverage lists: names, stability and overlap (G95-G99)\n\nSpent ${usd:.2f}. Written by the job.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["check", "run", "analyze", "publish"])
    {"check": check, "run": run, "analyze": analyze, "publish": publish}[parser.parse_args().stage]()
