# Anthropic API costs (UROP)

Every paid API run, for reimbursement. Dollars come from each run's token counts at batch prices, so they are estimates of the charge: the Console's Usage and Billing pages are the proof.

| Date | Run | What it paid for | Models | USD | Record |
|---|---|---|---|---|---|
| 2026-10-18 | Exp 1 naming and quiz pilot (N11) | Names and quizzes for 20 concepts, to test prompts and cost | Opus 5.5, Sonnet 5.5 | 2.61 | `exp1_concept_coverage/results/full_*_pilot_summary.json` |
| 2026-10-18 | Exp 1 faithfulness run (F) | Names, quizzes and judge for 240 concepts | Opus 5.5, Sonnet 5.5 | 21.60 | `exp1_concept_coverage/results/faith_*_summary.json`; pool `exp1/full/labels/faith/ledger.jsonl` |
| 2026-10-18 | Exp 1 topic categories (plan B) | Category scheme and assignments for 240 concepts | Opus 5.5, Sonnet 5.5 | 1.48 | `exp1_concept_coverage/design.md` (Q rows, results); pool `exp1/full/labels/topics/ledger.jsonl` |
| 2026-11-01 | Exp 2 moved concepts (G47-G53) | Names, quizzes and judge for 61 concepts, plus the quiz resend | Opus 5.5, Sonnet 5.5 | 9.74 | `exp2_rollout_gap/results/full_post_moved_summary.json`; pool `exp2/full_post/labels/moved/ledger.jsonl` |
| 2026-11-05 | Exp 2 names per model and class (G62-G73) | Dolma names of selected concepts, rollout names and quizzes of the check | Opus 5.5, Sonnet 5.5 | 28.47 | `exp2_rollout_gap/results/full_post_named_summary.json`, pool `exp2/full_post/labels/named/ledger.jsonl` |
| | **Total** | | | **63.90** | |

Pool paths are under `/orcd/pool/005/angela_h/`.
