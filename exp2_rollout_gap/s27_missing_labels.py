"""Names and themes of the missing concepts (design.md G90, G91, G93). Calls the API except where stated.

Usage: python s27_missing_labels.py check     # free: builds every name request, tests them, reports expected dollars, no paid call
       python s27_missing_labels.py run       # free key check, names, theme scheme, assignments, analysis; resumes from what is saved
       python s27_missing_labels.py analyze   # no API
       python s27_missing_labels.py publish   # no API: cost row, report, commit of named files, push
Reads DATA/full_post/missing/ (s26). Writes requests, raw answers and the ledger to DATA/full_post/labels/missing/ (pool: they
hold text) and results/full_post_missing_{check.json,names.json,summary.json,summary.md} (ids, names, numbers). New names also go to
notes/name_cache.json. Every submission passes the F7 guard (s13.send) with the G93 limit.
"""
import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np

import claude_batch  # Exp 1
import missing_lists as ml
import name_cache
import prompts  # Exp 1 Q2, Q3: schema and the unclear category
import s13_moved_labels as s13  # the F7 guard, ledger and batch recovery; pointed at this run's folder and limit below
from s07_names import LABELER  # Exp 1 N4
from s12_moved_windows import SETS

LIMIT_USD = 24.81  # G93, Angela: the account balance on 2026-11-06
RUN = "full_post"
IN = settings.DATA / RUN / "missing"
OUT = settings.DATA / RUN / "labels" / "missing"
R = settings.RESULTS
NAME_CHUNK, ASSIGN_CHUNK = 200, 500  # G67: the guard checks the spend between chunks
CAPS = {"scheme": 8_000, "assign": 300}  # Exp 1 Q2, Q3
THEME_MODELS = {"sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}  # Exp 1 Q3; Opus is primary
EXPECTED = {"name": (16.76 + 1.98 + 2.06) / (1509 + 179 + 199), "theme": 1.48 / 240}  # G93: dollars per name (full_post_named_summary.json) and per themed concept (Exp 1)
ROOT = Path(__file__).resolve().parent.parent
LISTS = ["random", "extreme_unfiltered", "extreme_filtered"]
s13.OUT, s13.LIMIT_USD = OUT, LIMIT_USD

# G91: Exp 1's Q2 and Q3 wording, with one description per concept in place of two
SCHEME_SYSTEM = "You organize descriptions of features found by a sparse autoencoder trained on a language model. Each numbered item describes one feature."
SCHEME_USER = prompts.TOPIC_SCHEME_USER
ASSIGN_SYSTEM = "You assign a feature of a language model to one category. The feature is described by one description."
ASSIGN_USER = """Categories:
{categories}

Feature:
Description: {name}

Choose the single category that fits the feature best, and give its name in the "category" field of your JSON answer."""


def selection():
    return json.loads((IN / "concepts.json").read_text())


def example(folder, side, c):
    return json.loads((IN / folder / f"{side}_{c}.json").read_text())


def preflight():
    """G67: one free token count, so a bad key stops the job before any money moves."""
    n = claude_batch.client().messages.count_tokens(model=LABELER, messages=[{"role": "user", "content": "ping"}]).input_tokens
    print(f"key works: free token count returned {n}", flush=True)


# ---- requests ----
def name_requests(sel):
    """G90: every new name, in concept order; a concept with no firing doc (not expected, chi says it fires) is skipped and counted."""
    out, no_docs = [], []
    for c in sel["new_dolma"]:
        ex = example("train_examples", "train", c)
        if ex["naming"]["rollout"]:
            out.append((f"nameTrain-{c}-train-0", s13.naming_request(c, ex, "rollout"), len(ex["naming"]["rollout"])))
        else:
            no_docs.append(c)
    for c, g in sel["new_rollout"].items():
        ex = example("rollout_examples", g, c)
        if ex["naming"]["rollout"]:
            out.append((f"namerollout-{c}-{g}-0", s13.naming_request(int(c), ex, "rollout"), len(ex["naming"]["rollout"])))
        else:
            no_docs.append(int(c))
    return out, no_docs


def outcomes_of(pattern):
    out = {}
    for path in sorted(OUT.glob(f"outcomes_{pattern}.json")):
        out.update(json.loads(path.read_text()))
    return out


def new_names():
    """{concept: name} of this run's answers, and {(concept, kind, windows)} for the cache."""
    names, cache_rows = {}, []
    for cid, o in outcomes_of("names_*").items():
        name = (o.get("answer") or {}).get("explanation") if o["status"] == "ok" else None
        if name:
            _, c, third, _ = cid.split("-")
            names[int(c)] = name
            cache_rows.append((int(c), name, "dolma", "train all sources", "exp2 missing (G90)", None) if third == "train"
                              else (int(c), name, "rollout", f"rollouts {third}", "exp2 missing (G90)", third))
    return names, cache_rows


def all_names(sel):
    names, _ = new_names()
    names.update({int(c): e["name"] for c, e in sel["reused"].items()})
    return names


def theme_items(sel, names):
    """G91: distinct concepts of the random draws, shuffled; no list, model or id reaches the prompt."""
    cs = sorted({x["concept"] for x in sel["rows"] if x["list"] == "random" and x["concept"] in names})
    return [cs[i] for i in np.random.default_rng([config.SEED, 91]).permutation(len(cs))]


def scheme_request(items, names):
    text = "\n".join(f"{i}. {names[c]}" for i, c in enumerate(items, 1))
    messages = [{"role": "user", "content": SCHEME_USER.format(n=len(items), items=text, unclear=prompts.UNCLEAR)}]
    return [("scheme-0-all-0", claude_batch.params(THEME_MODELS["opus"], SCHEME_SYSTEM, messages, prompts.TOPIC_SCHEME_SCHEMA, max_tokens=CAPS["scheme"]))]


def assign_requests(items, names, categories):
    schema = prompts.topic_assign_schema(categories)
    cats = "\n".join(f"- {c['name']}: {c['definition']}" for c in categories)
    out = {m: [] for m in THEME_MODELS}
    for m, model in THEME_MODELS.items():
        for c in items:
            messages = [{"role": "user", "content": ASSIGN_USER.format(categories=cats, name=names[c])}]
            out[m].append((f"assign{m}-{c}-all-0", claude_batch.params(model, ASSIGN_SYSTEM, messages, schema, max_tokens=CAPS["assign"])))
    return out


# ---- stages ----
def stages(sel):
    reqs, _ = name_requests(sel)
    reqs = [(cid, p) for cid, p, _ in reqs]
    print(f"names to send: {len(reqs)}", flush=True)
    for i in range(0, len(reqs), NAME_CHUNK):
        tag, chunk = f"names_{i // NAME_CHUNK}", reqs[i:i + NAME_CHUNK]
        if s13.saved(tag) is None:
            s13.send(chunk, tag, s13.count_inputs(chunk))
        name_cache.add(new_names()[1])
    names = all_names(sel)

    items = theme_items(sel, names)
    print(f"concepts to theme: {len(items)}", flush=True)
    if s13.saved("scheme") is None:
        req = scheme_request(items, names)
        s13.send(req, "scheme", s13.count_inputs(req))
    o = s13.saved("scheme")["scheme-0-all-0"]
    if o["status"] != "ok":
        raise SystemExit(f"scheme request ended with {o['status']}")
    categories = o["answer"]["categories"]
    problems = ml.check_scheme(categories, prompts.UNCLEAR)
    (OUT / "scheme.json").write_text(json.dumps({"categories": categories, "problems": problems}, indent=1, ensure_ascii=False))
    if problems:
        raise SystemExit(f"scheme failed its checks: {problems}; no assignment sent")
    for m, chunk_all in assign_requests(items, names, categories).items():  # Exp 1 Q5: the guard checks the spend in between
        for i in range(0, len(chunk_all), ASSIGN_CHUNK):
            tag, chunk = f"assign_{m}_{i // ASSIGN_CHUNK}", chunk_all[i:i + ASSIGN_CHUNK]
            if s13.saved(tag) is None:
                s13.send(chunk, tag, s13.count_inputs(chunk))


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
    """G93: free. Every name request is built and tested; expected and worst-case dollars are reported; nothing is sent."""
    OUT.mkdir(parents=True, exist_ok=True)
    preflight()
    s13.recover()
    sel = selection()
    reqs, no_docs = name_requests(sel)
    last = lambda p: p["messages"][-1]["content"]  # noqa: E731
    holds = lambda p, n: f"Example {n}:" in last(p) and f"Example {n + 1}:" not in last(p)  # noqa: E731
    bad = [cid for cid, p, n in reqs if not (p["model"] == LABELER and p["max_tokens"] == s13.CAPS["name"] and p["output_config"]["effort"] == "high" and 1 <= n <= 40 and holds(p, n))]
    pairs = [(cid, p) for cid, p, _ in reqs]
    sample = [pairs[i] for i in np.random.default_rng([config.SEED, 93]).choice(len(pairs), size=min(50, len(pairs)), replace=False)] if pairs else []
    counted = s13.count_inputs(sample)
    worst_name = max((claude_batch.worst_case(p, counted[cid]) for cid, p in sample), default=0.0)

    # Themes with placeholder names of about 100 tokens, near the longest stored names, and a 12-category placeholder scheme.
    # The "check_" ids keep these counts out of the cache the paid run reads
    placeholder = {x["concept"]: "word " * 100 for x in sel["rows"]}
    items = theme_items(sel, placeholder)
    fake = [{"name": f"Category {i}", "definition": "x" * 120} for i in range(11)] + [{"name": prompts.UNCLEAR, "definition": "x" * 120}]
    scheme = scheme_request(items, placeholder)
    worst_scheme = claude_batch.worst_case(scheme[0][1], s13.count_inputs([("check_scheme", scheme[0][1])])["check_scheme"])
    worst_assign = {}
    for m, rs in assign_requests(items, placeholder, fake).items():
        worst_assign[m] = claude_batch.worst_case(rs[0][1], s13.count_inputs([(f"check_{m}", rs[0][1])])[f"check_{m}"]) if rs else 0.0

    # Guard path: spent so far at measured rates, then the worst case of each next submission on top of what precedes it (G73)
    n_names, n_themes = len(reqs), len(items)
    spent0 = s13.spent()
    after_names = spent0 + EXPECTED["name"] * n_names
    expected = after_names + EXPECTED["theme"] * n_themes
    path = [spent0 + EXPECTED["name"] * i + worst_name * min(NAME_CHUNK, n_names - i) for i in range(0, n_names, NAME_CHUNK)] + [after_names + worst_scheme]
    path += [expected + w * min(ASSIGN_CHUNK, n_themes) for w in worst_assign.values()]  # expected already holds all assignments, so this errs high
    report = {"spent_before_usd": round(spent0, 2), "limit_usd": LIMIT_USD, "names_to_send": n_names, "new_dolma": len(sel["new_dolma"]), "new_rollout": len(sel["new_rollout"]), "reused_names": len(sel["reused"]),
              "names_without_firing_doc": len(no_docs), "names_from_under_40_windows": sum(n < 40 for _, _, n in reqs), "concepts_to_theme": n_themes,
              "worst_usd_per_name": round(worst_name, 4), "worst_usd_scheme": round(worst_scheme, 3), "worst_usd_per_assignment": {m: round(w, 5) for m, w in worst_assign.items()},
              "expected_total_usd": round(expected, 2), "highest_spent_plus_worst_usd": round(max(path), 2) if path else 0.0, "failures": len(bad), "first_failures": bad[:10],
              "date_of_check": datetime.now().strftime("%Y-%m-%d %H:%M")}
    print(json.dumps(report, indent=1))
    (R / f"{RUN}_missing_check.json").write_text(json.dumps(report, indent=1))
    if bad or (path and max(path) > LIMIT_USD):
        raise SystemExit("check failed")
    print("check passed")


# ---- analysis (G89, G91, G92) ----
def assignments():
    """{concept: {"opus": category, "sonnet": category}} of the answers so far."""
    out = {}
    for cid, o in outcomes_of("assign_*").items():
        m, c, _, _ = cid.split("-")
        category = (o.get("answer") or {}).get("category") if o["status"] == "ok" else None
        if category:
            out.setdefault(int(c), {})[m[len("assign"):]] = category
    return out


def theme_table(rows, assigned, categories, seed):
    """G91: per model and direction, shares of the random draw, with the two robustness views."""
    out = {}
    for i, g in enumerate(SETS):
        for j, direction in enumerate(ml.DIRECTIONS):
            mine = [x for x in rows if x["model"] == g and x["direction"] == direction and x["list"] == "random" and assigned.get(x["concept"], {}).get("opus")]
            labels = [assigned[x["concept"]]["opus"] for x in mine]
            rng = np.random.default_rng([seed, i, j])
            agreed = [assigned[x["concept"]]["opus"] for x in mine if assigned[x["concept"]].get("opus") == assigned[x["concept"]].get("sonnet")]
            kept = [assigned[x["concept"]]["opus"] for x in mine if not x["v_agrees"]]
            out[f"{g}|{direction}"] = {"model": g, "direction": direction, "concepts": len(labels), "shares": ml.category_shares(labels, categories, rng),
                                       "concepts_agreed": len(agreed), "shares_agreed": ml.category_shares(agreed, categories, rng, n_boot=1),
                                       "concepts_without_v_agrees": len(kept), "shares_without_v_agrees": ml.category_shares(kept, categories, rng, n_boot=1)}
    return out


def clean(t):
    return (t or "–").replace("|", "/").replace("\n", " ")


def analyze(stop=None):
    sel = selection()
    names, _ = new_names()
    source = {c: ("exp2 missing (G90), train windows" if int(c) in {*sel["new_dolma"]} else f"exp2 missing (G90), rollouts {sel['new_rollout'].get(str(c))}") for c in names}
    source.update({int(c): f"{e['source']}, {e['windows']}" for c, e in sel["reused"].items()})
    named = all_names(sel)
    rows = [{**x, "name": named.get(x["concept"]), "name_source": source.get(x["concept"])} for x in sel["rows"]]
    (R / f"{RUN}_missing_names.json").write_text(json.dumps(rows, indent=0, ensure_ascii=False))

    scheme_path = OUT / "scheme.json"
    categories = json.loads(scheme_path.read_text())["categories"] if scheme_path.exists() else []
    cat_names = [c["name"] for c in categories]
    assigned = assignments()
    both = [v for v in assigned.values() if v.get("opus") and v.get("sonnet")]
    kappa, agreement = ml.cohen_kappa([v["opus"] for v in both], [v["sonnet"] for v in both], cat_names) if cat_names else (None, None)
    themes = theme_table(rows, assigned, cat_names, config.SEED) if cat_names else {}
    usage = claude_batch.usage_summary({cid: o for tag in ("names_*", "scheme", "assign_*") for cid, o in outcomes_of(tag).items()}, lambda cid: cid.split("-")[0])
    statuses = {}
    for o in outcomes_of("names_*").values():
        statuses[o["status"]] = statuses.get(o["status"], 0) + 1
    sel_summary = json.loads((R / f"{RUN}_missing_selection_summary.json").read_text())
    summary = {"stopped": stop, "spent_usd": round(s13.spent(), 2), "limit_usd": LIMIT_USD, "name_statuses": statuses, "names_returned": len(names), "names_planned": len(sel["new_dolma"]) + len(sel["new_rollout"]),
               "entries_without_name": sum(x["name"] is None for x in rows), "categories": categories, "concepts_themed": len(assigned), "kappa_opus_vs_sonnet": kappa, "agreement": agreement, "themes": themes,
               "usage": usage, "by_model": sel_summary["by_model"], "garbled": sel_summary["garbled"]}
    (R / f"{RUN}_missing_summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))

    md = [f"# Missing concepts per model (design.md G87-G93)\n\nNames first. Spent ${summary['spent_usd']:.2f} of ${LIMIT_USD}. Names are not scored in this run. \"Missing from Dolma\" means below e^-5 in our sample.\n" + (f"\nStopped: {stop}\n" if stop else "")]
    for direction in ml.DIRECTIONS:
        md.append(f"\n## {direction}\n")
        for g in SETS:
            for name in LISTS:
                mine = [x for x in rows if x["model"] == g and x["direction"] == direction and x["list"] == name]
                md.append(f"\n### {g}, {name} ({len(mine)})\n\n| concept | r | train docs | rollout docs | V agrees | name |\n|---|---|---|---|---|---|\n")
                md += [f"| {x['concept']} | {x['r']} | {x['n_fire_train']} | {x['n_fire_rollout']} | {'yes' if x['v_agrees'] else 'no'} | {clean(x['name'])} |\n" for x in mine]
    if cat_names:
        md.append(f"\n## Themes of the random draws\n\nCohen's kappa, Opus vs Sonnet: {kappa}; agreement {agreement}; {len(assigned)} concepts.\n\n")
        md += [f"- **{c['name']}**: {c['definition']}\n" for c in categories]
        md.append("\n| model | direction | concepts | " + " | ".join(cat_names) + " |\n|---|---|---|" + "---|" * len(cat_names) + "\n")
        for t in themes.values():
            md.append(f"| {t['model']} | {t['direction']} | {t['concepts']} | " + " | ".join(f"{t['shares'][c][0]} [{t['shares'][c][1]}, {t['shares'][c][2]}]" for c in cat_names) + " |\n")
    md.append("\n## Counts per model\n\n| model | direction | members | share of dictionary | V baseline | members V agrees | chi rollout 0 | pass present-side filter |\n|---|---|---|---|---|---|---|---|\n")
    for g in SETS:
        for direction in ml.DIRECTIONS:
            b = sel_summary["by_model"][g][direction]
            md.append(f"| {g} | {direction} | {b['members']} | {b['share_of_dictionary']} | {b['v_baseline_members']} | {b['members_v_agrees']} | {b['members_chi_rollout_zero']} | {b['members_pass_present_filter']} |\n")
    md.append("\n## Share of each list B concept's activation from garbled docs (G92)\n\n| model | share of docs flagged | all firing concepts, median | random, median | extreme unfiltered, median | extreme filtered, median |\n|---|---|---|---|---|---|\n")
    for g in SETS:
        b = sel_summary["garbled"][g]
        md.append(f"| {g} | {b['share_docs_flagged']} | {b['all_firing_concepts']['median']} | {b['random']['median']} | {b['extreme_unfiltered']['median']} | {b['extreme_filtered']['median']} |\n")
    (R / f"{RUN}_missing_summary.md").write_text("".join(md))
    print(json.dumps({k: summary[k] for k in ("stopped", "spent_usd", "name_statuses", "names_returned", "names_planned", "concepts_themed", "kappa_opus_vs_sonnet", "agreement")}, indent=1), flush=True)


# ---- publish (G93) ----
def git(*args):
    print("git", *args, flush=True)
    return subprocess.run(["git", "-C", str(ROOT), *args], check=False).returncode


def push(files, message):
    files = [f for f in files if (ROOT / f).exists()]
    git("add", *files)
    if git("commit", "-m", message + "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>", "--", *files) != 0:
        print("nothing new to commit, or the commit failed", flush=True)
    if git("pull", "--rebase", "--autostash") != 0 or git("push") != 0:
        raise SystemExit("push failed: the commit is local, results are on disk; push from a login node")
    print("pushed", flush=True)


def publish_check():
    """After the free job: counts only, so the paid job can be decided from the repo."""
    push([f"exp2_rollout_gap/results/{RUN}_missing_selection_summary.json", f"exp2_rollout_gap/results/{RUN}_missing_check.json"], "Exp 2 missing concepts: free selection and check (G87-G93)")


def publish():
    """After the paid job: cost row (CLAUDE.md), report, commit, push. No document text enters these files."""
    now = datetime.now()
    usd = s13.spent()
    path = ROOT / "notes" / "api_costs.md"
    text = path.read_text()
    if "G87-G93" not in text:
        total = float(re.search(r"\*\*Total\*\* \| \| \| \*\*([0-9.]+)\*\*", text).group(1))
        row = (f"| {now:%Y-%m-%d} | Exp 2 missing concepts (G87-G93) | Names of missing concepts in both directions, theme scheme and assignments | Opus 5.5, Sonnet 5.5 | {usd:.2f} | "
               f"`exp2_rollout_gap/results/{RUN}_missing_summary.json`, pool `exp2/full_post/labels/missing/ledger.jsonl` |\n")
        path.write_text(re.sub(r"\| \| \*\*Total\*\* \| \| \| \*\*[0-9.]+\*\*", lambda _: f"{row}| | **Total** | | | **{total + usd:.2f}**", text))
    summary = json.loads((R / f"{RUN}_missing_summary.json").read_text())
    report = [f"\n## {now:%Y-%m-%d %H:%M}, Exp 2 missing concepts: {'stopped' if summary['stopped'] else 'done'} (G87-G93)\n\n",
              f"Written by the labels job, not checked by hand. Spent ${usd:.2f} of ${LIMIT_USD}. Names {summary['names_returned']} of {summary['names_planned']} returned, {summary['concepts_themed']} concepts themed, kappa {summary['kappa_opus_vs_sonnet']}.",
              (f" Stopped: {summary['stopped']}." if summary["stopped"] else ""), f" Names and tables: `exp2_rollout_gap/results/{RUN}_missing_summary.md`.\n"]
    with open(ROOT / "notes" / "tunnel_reports.md", "a") as f:
        f.write("".join(report))
    push([f"exp2_rollout_gap/results/{RUN}_missing_{k}" for k in ("names.json", "summary.json", "summary.md")] + ["notes/name_cache.json", "notes/api_costs.md", "notes/tunnel_reports.md"],
         f"Exp 2 missing concepts: names and themes (G87-G93)\n\nSpent ${usd:.2f}. Written by the labels job.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["check", "run", "analyze", "publish", "publish_check"])
    {"check": check, "run": run, "analyze": analyze, "publish": publish, "publish_check": publish_check}[parser.parse_args().stage]()
