"""Build the Space data for the "Exp 2 diagnostics" section of the Temp visualizations tab (design.md G61). CPU, seconds.

Usage: python s17_space_diag.py
Reads only committed results files and figures; recomputes nothing. Writes space/data/exp2_diagnostics.json and copies
figures/full_post_<set>_{scatter,hist_shifted}.png to space/data/exp2/ (sha256 checked after the copy).
"""
import hashlib
import json
import shutil
from pathlib import Path

import settings

HERE = Path(__file__).resolve().parent
R = settings.RESULTS
SPACE = HERE.parent / "space"
FIGURES = HERE / "figures"
SETS = ["V", "stage1", "main", "sft", "dpo", "instruct"]  # G61: no no-loop versions
GENERATORS = SETS[1:]
KINDS = ["gainer", "loser", "control"]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(name):
    return json.loads((R / name).read_text())


def table_a(diag):
    """G40 shape vs shuffle and G42 variance split, per set."""
    rows = []
    for s in SETS:
        x = diag["sets"][s]
        sv, vs = x["shape_vs_shuffle"], x["variance_split"]
        rows.append({"set": s, "shuffle_share": sv["shuffle_share"], "shape_share": sv["shape_share"],
                     "spearman": sv["spearman"], "var_r": vs["var_r"], "trend_share": vs["trend_share"],
                     "excess_dispersion_sd": x["excess_dispersion_sd"]})
    return rows


def table_b(moved):
    """G47-G53: group summary and each concept's two names, gaps and agree flag. No window text, no judge."""
    groups = [{"kind": k, **{f: moved["groups"][k][f] for f in
               ("concepts", "scored", "agree_share", "mean_gap_on_dolma", "mean_gap_on_rollouts")}} for k in KINDS]
    keep = ("concept", "set", "kind", "rank_train", "dolma_name", "rollout_name", "gap_on_dolma", "gap_on_rollouts", "agree")
    concepts = sorted(({k: c[k] for k in keep} for c in moved["concepts"]),
                      key=lambda c: (KINDS.index(c["kind"]), GENERATORS.index(c["set"]), c["concept"]))
    return {"agree_gap": moved["agree_gap"], "groups": groups, "concepts": concepts}


def table_c(diag, lenmatch, noflag, countctl):
    """G43, G58, G60: Δ vs V per rollout set under each doc choice."""
    def run(summary, docs):
        return {"docs": docs, "sets": {g: {k: summary["delta_vs_V"][g][k] for k in ("delta", "ci95_basic", "delta_bias_corrected")}
                                       for g in GENERATORS}}
    full = {"docs": diag["docs_per_scope"]["doc"],
            "sets": {g: {k: diag["full_post_delta_bias_corrected"][g][k] for k in ("delta", "ci95_basic", "delta_bias_corrected")}
                     for g in GENERATORS}}
    ctl = {"docs": countctl["docs"], "draws": countctl["seeds_done"],
           "sets": {g: {k: countctl["sets"][g]["delta_bias_corrected"][k] for k in ("control_mean", "control_sd", "control_min", "control_max")}
                    for g in GENERATORS}}
    if countctl["seeds_done"] != countctl["seeds_planned"]:
        raise SystemExit(f"G61: count control has {countctl['seeds_done']} of {countctl['seeds_planned']} seeds")
    return {"all_docs": full, "length_matched": run(lenmatch, lenmatch["sets"]["V"]["docs"]),
            "garbled_removed": run(noflag, noflag["docs"]), "count_control": ctl}


def main():
    diag = read("full_post_diagnostics.json")
    out = {
        "run": "full_post",
        "sources": ["results/full_post_diagnostics.json", "results/full_post_moved_summary.json",
                    "results/full_post_lenmatch_distribution_summary.json", "results/full_post_noflag_distribution_summary.json",
                    "results/full_post_countctl_summary.json"],
        "sets": SETS,
        "figures": {s: {"scatter": f"data/exp2/full_post_{s}_scatter.png", "hist_shifted": f"data/exp2/full_post_{s}_hist_shifted.png"}
                    for s in SETS},
        "shape_dispersion": table_a(diag),
        "moved": table_b(read("full_post_moved_summary.json")),
        "delta": table_c(diag, read("full_post_lenmatch_distribution_summary.json"),
                         read("full_post_noflag_distribution_summary.json"), read("full_post_countctl_summary.json")),
    }
    for s in SETS:
        for kind in ("scatter", "hist_shifted"):
            src, dst = FIGURES / f"full_post_{s}_{kind}.png", SPACE / out["figures"][s][kind]
            shutil.copyfile(src, dst)
            if sha256(src) != sha256(dst):
                raise SystemExit(f"G61: copy of {src.name} differs")
    path = SPACE / "data" / "exp2_diagnostics.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {path} ({path.stat().st_size:,} bytes) and {2 * len(SETS)} figures")


if __name__ == "__main__":
    main()
