# Tunnel Claude reports

Newest at the bottom. No document text (Dolma, Pile or rollout windows) in this file (CLAUDE.md).

## 2026-11-01 15:50, Exp 2 full_post diagnostics: jobs submitted and running

Status: design rows G39-G46 and open items O4-O7 committed before any code ran (`1e97fe6`); code committed (`18251d0`). CPU jobs running, no results yet. Nothing goes to the Space.

Submitted (each as one copy on `mit_preemptable` and one on `mit_normal`; the first to start cancels the other, G26/G46; mail on END and FAIL):

| Job | Script | Covers | Outputs (new names) |
|---|---|---|---|
| `exp2_diag_post` 27579383 (`mit_normal`, running since 15:46) | `s09_diagnostics.py`, then `figures/make_diagnostics_figures.py` | Sheng-Yu's question (G40), items 1 (G41), 2 (G42), 8 (G44), bias-corrected Δ (G45) | `results/full_post_diagnostics.json`, `figures/full_post_<set>_scatter.png`, `figures/full_post_<set>_hist_shifted.png`, `DATA/full_post/diagnostics_gainers.md` (pool) |
| `exp2_len_lenmatch` 27579384 (`mit_normal`, running) | `s10_length.py --mode lenmatch` | Item 3: same length distribution in every set (G43) | `results/full_post_lenmatch_distribution_summary.json` |
| `exp2_len_min30` 27579385 (`mit_normal`, running) | `s10_length.py --mode min30` | Item 3: docs under 30 tokens dropped (G43) | `results/full_post_min30_distribution_summary.json` |
| `exp2_diag_summary` 27579386/27579387 (pending, after the three) | `s11_diagnostics_summary.py` | Short summary: answer to Sheng-Yu in 3-4 sentences + tables for items 1, 2, 3, 8 | `results/full_post_diagnostics_summary.md` |

Checks:
- s09 stops if the doc counts, any set's χ (max relative difference < 1e-9) or any slope (±1e-4) differ from the published `full_post`, so the diagnostics describe the same docs. At 15:49 the job had passed these checks and finished G40-G42; the G44 bootstrap was running.
- Small-input tests before submitting: the variance identity of G42 held to 1e-16; a pure shuffle gives shape share 0.
- Figures rendered on sft from the existing table.

Early hint (sft test figure from the existing table, not a job result): shifting the sft histogram of log10 χ by its median ratio (+0.29) overshoots the train bars on the right; shifting and rescaling to train's sd (sft 1.13 vs train 1.06) nearly matches them. So most of panel (c)'s width probably does not show in (b), which points to concepts trading places; the D_marg / D_pair split will measure it.

Deferred by Angela: items 4, 5 (BCa), 6, 7, recorded as open items O4-O7 in design.md with root-cause notes. Item 5 for now: Δ minus bootstrap bias next to every Δ (G45).

Next: when the summary job has written the md, check its numbers, rewrite the generated 3-4-sentence answer to Sheng-Yu, then commit and push the results.
