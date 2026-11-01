"""Pilot report for the post-trained generators (design.md G30-G36). CPU only.

Usage: python s06_post_report.py
Reads DATA/pilot_post/<generator>/{rollouts,acts} (s01-s02), results/pilot_post_* summaries (s01-s03), and full/'s
stage1 and main rollouts and acts with Exp 1's V acts for the projected full_post doc counts (G36).
Writes DATA/pilot_post/pilot_report.md (rollout text, pool only: G20) and results/pilot_post_report.json (counts).
Exit code 0 if the gate passes (every new generator under 20% empty rollouts, 0 special ids in the SAE input), 3 if not.
"""
import json
import sys

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np
import pandas as pd
from transformers import AutoTokenizer

from s03_distribution import degeneration, lengths
from s03_pilot import tokenize  # Exp 1

NEW = ["sft", "dpo", "instruct"]
MAX_EMPTY = 0.2  # G36 gate
N_SHOWN = 10
PUBLISHED = {"doc": 9753, "0": 9753, "1": 6121, "2": 4580, "3": 3389}  # results/full_distribution_summary.json
SCOPES = [("doc", 0)] + [(str(w), a) for w, (a, _) in enumerate(settings.WINDOWS)]


def read_rollouts(run, g):
    return pd.concat([pd.read_parquet(p) for p in sorted((settings.DATA / run / g / "rollouts").glob("part_?????.parquet"))],
                     ignore_index=True)


def eligible(n_tokens):
    """G16: docs reaching each scope (whole doc: any token; window w: more tokens than its start)."""
    n = np.asarray(n_tokens)
    return {key: int((n > start).sum()) for key, start in SCOPES}


def main():
    run = "pilot_post"
    run_dir = settings.DATA / run
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    dist = json.loads((settings.RESULTS / f"{run}_distribution_summary.json").read_text())
    report = {"run": run, "generators": {}}
    md = [f"# Exp 2 pilot, post-trained generators (design.md G30-G36)\n"]
    gate = True

    projected_new = {}
    for g in NEW:
        rolls = read_rollouts(run, g).set_index("rollout_id")
        roll_sum = json.loads((settings.RESULTS / f"{run}_{g}_rollouts_summary.json").read_text())
        act_sum = json.loads((settings.RESULTS / f"{run}_{g}_activation_summary.json").read_text())
        n = len(rolls)
        empty = act_sum["empty_generated"] + act_sum["empty_after_special_drop"]  # G3, G34
        acts = lengths(sorted((run_dir / g / "acts").glob("part_?????.npz")), lambda ids: np.ones(len(ids), dtype=bool))
        flagged = set(rolls.index[rolls["ids"].map(lambda x: degeneration(settings.encoder_ids(run, x))) >= settings.DEGEN_THRESHOLD])
        passed = empty / n < MAX_EMPTY and act_sum["special_ids_in_sae_input"] == 0
        gate &= passed
        # G36: share of generated rollouts reaching each scope, scaled to the full run's 10,000
        projected_new[g] = {name: {k: round(v / n * settings.N_ROLLOUTS) for k, v in eligible(sub).items()}
                            for name, sub in [(g, acts), (f"{g}_no_loops", acts[~acts.index.isin(flagged)])]}
        report["generators"][g] = {
            "repo": roll_sum["repo"], "commit": roll_sum["commit"], "rollouts": n,
            "empty_generated": act_sum["empty_generated"], "empty_after_special_drop": act_sum["empty_after_special_drop"],
            "empty_share": round(empty / n, 4),
            "stop_id_counts": roll_sum["stop_id_counts"],
            "special_ids_generated": act_sum["special_ids_generated"],
            "rollouts_with_special_ids": act_sum["rollouts_with_special_ids"],
            "special_ids_generated_by_id": act_sum["special_ids_generated_by_id"],
            "special_ids_in_sae_input": act_sum["special_ids_in_sae_input"],
            "retokenized_different": act_sum["retokenized_different"],
            "encoded_length_quantiles": {str(q): int(acts.quantile(q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
            "tokens_per_second_by_gpu": roll_sum.get("tokens_per_second_by_gpu"),
            "degeneration": dist["degeneration"].get(g), "flagged": len(flagged), "gate_passed": passed,
        }

    # G36: base sets of full_post, counted exactly: V and stage1 from their acts; main from full/'s rollouts after the
    # G34 drop, re-tokenized as s02 does; no-loop versions with the G14 threshold
    docs = pd.read_parquet(settings.EXP1_RUN / "docs.parquet", columns=["doc_id", "subset"])
    v_ids = set(docs.loc[docs["subset"] == "V", "doc_id"])
    base = {"V": eligible(lengths(sorted((settings.EXP1_RUN / "acts").glob("part_?????.npz")),
                                  lambda ids: np.array([d in v_ids for d in ids])))}
    for g in ["stage1", "main"]:
        rolls = read_rollouts("full", g)
        ids = rolls["ids"].map(lambda x: settings.encoder_ids("full_post", x))
        n_tok = ids.map(lambda x: len(tokenize(tokenizer, tokenizer.decode(x))[0]) if len(x) else 0)
        loop = ids.map(degeneration).astype(float) >= settings.DEGEN_THRESHOLD
        base[g], base[f"{g}_no_loops"] = eligible(n_tok), eligible(n_tok[~loop])
    every = {**base, **{k: v for p in projected_new.values() for k, v in p.items()}}
    projected = {key: min(c[key] for c in every.values()) for key, _ in SCOPES}
    smallest = {key: min(every, key=lambda s: every[s][key]) for key, _ in SCOPES}
    report["projected_full_post_docs_per_scope"] = projected
    report["projected_smallest_set"] = smallest
    report["full_docs_per_scope"] = PUBLISHED
    report["eligible_docs_per_set"] = every
    report["check_V_spearman"] = dist["check_V"]["spearman_log_chi_V_vs_train"]
    report["gate_passed"] = bool(gate)

    # Markdown: counts first, then text to read
    md.append("\n## Counts per generator\n\n| | " + " | ".join(NEW) + " |\n|---|" + "---|" * len(NEW) + "\n")
    for key in ["commit", "rollouts", "empty_generated", "empty_after_special_drop", "empty_share", "stop_id_counts",
                "special_ids_generated", "rollouts_with_special_ids", "special_ids_generated_by_id",
                "special_ids_in_sae_input", "retokenized_different", "encoded_length_quantiles",
                "tokens_per_second_by_gpu", "flagged", "gate_passed"]:
        md.append(f"| {key} | " + " | ".join(str(report["generators"][g][key]) for g in NEW) + " |\n")
    md.append("\n## G16 doc counts per frame (whole doc, tokens 0-256, 256-512, 512-768, 768-1024)\n\n"
              "| | " + " | ".join(k for k, _ in SCOPES) + " |\n|---|" + "---|" * len(SCOPES) + "\n")
    md.append("| full (published) | " + " | ".join(f"{PUBLISHED[k]:,}" for k, _ in SCOPES) + " |\n")
    md.append("| full_post (projected) | " + " | ".join(f"{projected[k]:,} ({smallest[k]})" for k, _ in SCOPES) + " |\n")
    for name, c in every.items():
        md.append(f"| {name} | " + " | ".join(f"{c[k]:,}" for k, _ in SCOPES) + " |\n")
    md.append(f"\nCheck 6: Spearman of log χ_V vs log χ_train = {report['check_V_spearman']} (Exp 1 C3: 0.9918).\n")
    md.append(f"\n**Gate: {'PASSED' if gate else 'FAILED'}**\n")

    for g in NEW:
        rolls = read_rollouts(run, g).reset_index(drop=True)
        md.append(f"\n## {N_SHOWN} rollouts, {g} (full text as encoded, after the G34 drop)\n")
        pick = np.random.default_rng([1, 36]).choice(len(rolls), size=N_SHOWN, replace=False)
        flagged = [i for i in range(len(rolls))
                   if degeneration(settings.encoder_ids(run, rolls.at[i, "ids"])) >= settings.DEGEN_THRESHOLD]
        for title, rows in [("sample", pick), ("flagged as loops (G14)", flagged)]:
            md.append(f"\n### {g}: {title} ({len(rows)})\n")
            for i in rows:
                ids = list(rolls.at[i, "ids"])
                kept = settings.encoder_ids(run, ids)
                dropped = [t for t in ids if t >= settings.SPECIAL_MIN]
                score = degeneration(kept)
                md.append(f"\n**`{rolls.at[i, 'rollout_id']}`**: {len(ids)} generated tokens, stop id {rolls.at[i, 'stop_id']}, "
                          f"dropped special ids {dropped}, loop score {score:.2f}\n\n```\n{tokenizer.decode(kept)}\n```\n")

    (run_dir / "pilot_report.md").write_text("".join(md))
    (settings.RESULTS / f"{run}_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "eligible_docs_per_set"}, indent=1))
    print(run_dir / "pilot_report.md")
    sys.exit(0 if gate else 3)


if __name__ == "__main__":
    main()
