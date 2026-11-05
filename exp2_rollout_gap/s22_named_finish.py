"""Finisher of the named run (design.md G73): writes the cost row, the report and the findings, then commits and pushes. No API.

Usage: python s22_named_finish.py
Runs after the labels and noise jobs whatever their state. Reads results/full_post_named_*.json and the ledger. Writes
notes/api_costs.md, notes/tunnel_reports.md, design.md. Names and numbers only: no document text enters these files.
"""
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = HERE / "results"
LEDGER = Path("/orcd/pool/005/angela_h/exp2/full_post/labels/named/ledger.jsonl")
CELLS = ["random_over", "random_under", "random_middle", "extreme_over", "extreme_under_unfiltered", "extreme_under_filtered"]
MARK = "Exp 2 names per model, check and noise rerun (G70-G73)"
FILES = ["exp2_rollout_gap/design.md", "exp2_rollout_gap/results/full_post_named_names.json", "exp2_rollout_gap/results/full_post_named_extremes.md",
         "exp2_rollout_gap/results/full_post_named_summary.json", "exp2_rollout_gap/results/full_post_named_summary.md",
         "exp2_rollout_gap/results/full_post_named_selection_summary.json", "exp2_rollout_gap/results/full_post_named_check.json",
         "exp2_rollout_gap/results/full_post_named_noise_summary.json", "exp1_concept_coverage/results/full_examples_summary_exp2named_examples_named.json",
         "notes/name_cache.json", "notes/api_costs.md", "notes/tunnel_reports.md"]


def load(name):
    path = RESULTS / name
    return json.loads(path.read_text()) if path.exists() else None


def spent():
    """Latest ledger entry per tag; pending entries are submissions with no saved result, counted at their worst case."""
    last = {}
    for line in open(LEDGER):
        e = json.loads(line)
        last[e["tag"]] = e
    return sum(e["usd"] for e in last.values()), [t for t, e in last.items() if e.get("pending")]


def cost_row(usd, today):
    path = ROOT / "notes" / "api_costs.md"
    text = path.read_text()
    if "G62-G73" in text:
        return
    total = float(re.search(r"\*\*Total\*\* \| \| \*\*([0-9.]+)\*\*", text).group(1))
    row = (f"| {today} | Exp 2 names per model and class (G62-G73) | Dolma names of selected concepts, rollout names and quizzes of the check | Opus 5.5, Sonnet 5.5 | {usd:.2f} | "
           "`exp2_rollout_gap/results/full_post_named_summary.json`, pool `exp2/full_post/labels/named/ledger.jsonl` |\n")
    text = re.sub(r"\| \| \*\*Total\*\* \| \| \*\*[0-9.]+\*\*", lambda _: f"{row}| | **Total** | | **{total + usd:.2f}**", text)
    path.write_text(text)


def clean(t):
    return (t or "–").replace("|", "/").replace("\n", " ")


def report(usd, pending, today_time):
    summary, noise, sel = load("full_post_named_summary.json"), load("full_post_named_noise_summary.json"), load("full_post_named_selection_summary.json")
    out = [f"\n## {today_time}: {MARK}\n\nWritten by the finisher job, with no session open.\n"]
    out.append(f"- Spent ${usd:.2f} of the $40 stop." + (f" Pending with no result: {pending}." if pending else ""))
    if sel:
        out.append(f"- Selection: {sel['entries']} list entries, {sel['distinct_concepts']} distinct concepts; {sel['new_names_in_this_run']} names written in this run ({sel['new_from_train']} from train windows, {sel['train_docs_named_under_40']} of those from under 40 docs), {sel['reused_names']} reused from earlier runs.")
    if summary is None:
        out.append("- Labels job left no summary: check `logs/exp2_named_labels_*.out`.")
    else:
        n = summary["counts"]
        out.append(f"- Names: {n['new_names_returned']} of {n['new_names_planned']} returned, {n['new_names_failed']} failed and left unnamed; {n['names_bought_not_selected']} names bought under G62-G69 are no longer selected and stay in the cache.")
        out.append(f"- Check: {n['check_entries']} entries, {n['check_distinct']} distinct concepts, {n['rollout_names_new']} rollout names, {n['quiz_prompts']} quiz prompts.")
        if summary["stopped"]:
            out.append(f"- Stopped: {summary['stopped']}. Results below are partial.")
        out.append("\nNames first, up to 3 per cell (full lists: `exp2_rollout_gap/results/full_post_named_summary.md`, windows on pool `exp2/full_post/named/check_examples.md`):\n")
        out.append("| cell | concept | model | Dolma name | rollout name | rollout docs |\n|---|---|---|---|---|---|")
        for g in ("base", "instruct"):
            for k in CELLS:
                for p in [p for p in summary["pairs"] if p["group"] == g and p["cell"] == k][:3]:
                    out.append(f"| {g} {k} | {p['concept']} | {p['model']} | {clean(p['dolma_name'])} | {clean(p['rollout_name'])} | {p['n_fire_model']} |")
        out.append("\nPaired gap on V windows, Dolma name minus rollout name:\n")
        out.append("| cell | drawn | scored | Dolma name | rollout name | gap [95%] | Dolma below 0.6 [95%] |\n|---|---|---|---|---|---|---|")
        tables = summary["tables"]
        for label, t in [(f"{g} {k}", tables["cells"][f"{g}_{k}"]) for g in ("base", "instruct") for k in CELLS] + list(tables["groups"].items()):
            out.append(f"| {label} | {t['drawn']} | {t['scored_pairs']} | {t['mean_dolma_name']} | {t['mean_rollout_name']} | {t['mean_gap']} {t['gap_ci95']} | {t['share_dolma_below_0_6']} {t['share_ci95']} |")
    if noise is None:
        out.append("\n- Noise job left no summary: check `logs/exp2_named_noise_*.out`.")
    else:
        out.append(f"\nNoise rerun: {noise['reruns']} reruns dropping {noise['drop']:.0%} of docs per set (share of a class or list that stays, median r spread):\n")
        out.append("| model | over stays | under stays | middle stays | over median r sd | under median r sd | unfiltered over list | unfiltered under list | filtered over list | filtered under list |\n|---|---|---|---|---|---|---|---|---|---|")
        for g, m in noise["models"].items():
            c, x = m["classes"], m["extreme_lists"]
            out.append(f"| {g} | {c['over']['mean_share_stays']} | {c['under']['mean_share_stays']} | {c['middle']['mean_share_stays']} | {c['over']['median_r_sd']} | {c['under']['median_r_sd']} | "
                       f"{x['extreme_unfiltered_over']['mean_overlap_with_baseline']} | {x['extreme_unfiltered_under']['mean_overlap_with_baseline']} | {x['extreme_filtered_over']['mean_overlap_with_baseline']} | {x['extreme_filtered_under']['mean_overlap_with_baseline']} |")
    out.append("\nReading of these numbers is left for the next session: nothing here has been checked by hand.\n")
    return "\n".join(out)


def findings(usd):
    path = HERE / "design.md"
    text = path.read_text()
    if "Findings of G70-G73" in text:
        return
    summary, noise = load("full_post_named_summary.json"), load("full_post_named_noise_summary.json")
    line = f"Findings of G70-G73 (finisher job, not checked by hand): spent ${usd:.2f}."
    if summary:
        g = summary["tables"]["groups"]
        line += " Mean paired gap, Dolma name minus rollout name: " + "; ".join(f"{k} {v['mean_gap']} {v['gap_ci95']}" for k, v in g.items()) + "."
    if noise:
        line += " Mean share staying in the under class over reruns: " + ", ".join(f"{k} {m['classes']['under']['mean_share_stays']}" for k, m in noise["models"].items()) + "."
    line += " Full tables: `results/full_post_named_summary.md`, `results/full_post_named_noise_summary.json`.\n\n"
    mark = "## Qualitative results (written 2026-10-21"
    path.write_text(text.replace(mark, line + mark, 1))


def git(*args):
    print("git", *args, flush=True)
    return subprocess.run(["git", "-C", str(ROOT), *args], check=False).returncode


def main():
    now = datetime.now()
    usd, pending = spent()
    log = ROOT / "notes" / "tunnel_reports.md"
    if MARK not in log.read_text():
        with open(log, "a") as f:
            f.write(report(usd, pending, now.strftime("%Y-%m-%d %H:%M")))
    cost_row(usd, now.strftime("%Y-%m-%d"))
    findings(usd)
    files = [f for f in FILES if (ROOT / f).exists()]
    git("add", *files)
    message = f"Exp 2 named run: names, check and noise results (G70-G73)\n\nSpent ${usd:.2f}. Written by the finisher job.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n"
    if git("commit", "-m", message, "--", *files) != 0:
        print("nothing new to commit, or the commit failed", flush=True)
    if git("pull", "--rebase", "--autostash") != 0 or git("push") != 0:
        raise SystemExit("push failed: the commit is local, results are on disk; push from a login node")
    print("pushed", flush=True)


if __name__ == "__main__":
    main()
