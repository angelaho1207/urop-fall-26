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

## 2026-11-01 15:55, Exp 2 item 3: `full_post_lenmatch` finished (job 27579384, 4 min)

Every set subsampled to the same length distribution: 5,461 docs per set (bins [1,30) 49, [30,100) 225, [100,300) 1,266, [300,1024) 2,664, [1024] 1,257). V limits the two short bins (only 49 V docs under 30 tokens); instruct_no_loops and sft_no_loops limit the two long bins.

| set | Δ full_post (bias-corrected) | Δ lenmatch (bias-corrected) [basic 95%] | median ln ratio, lenmatch | χ slope / firing-share slope, lenmatch |
|---|---|---|---|---|
| stage1 | +0.0312 (+0.0291) | +0.0365 (+0.0348) [+0.0263, +0.0430] | −0.118 | 1.041 / 1.032 |
| main | −0.0136 (−0.0160) | −0.0107 (−0.0110) [−0.0190, −0.0028] | −0.225 | 0.994 / 0.957 |
| sft | −0.0338 (−0.0422) | −0.0358 (−0.0406) [−0.0490, −0.0326] | −0.673 | 0.968 / 0.933 |
| dpo | −0.0339 (−0.0382) | −0.0366 (−0.0373) [−0.0453, −0.0300] | −0.428 | 0.968 / 0.892 |
| instruct | −0.0268 (−0.0326) | −0.0282 (−0.0305) [−0.0383, −0.0230] | −0.462 | 0.976 / 0.920 |

V under lenmatch: slope 1.004, firing-share slope 1.012, median ln ratio −0.021.

Reading: matching lengths leaves Δ, its sign and the median offset nearly unchanged (sft median −0.67 before and after), so short rollouts do not explain the offset or Δ. The firing-share vs χ gap (deferred O4) also stays after matching (dpo 0.892 vs 0.968), so length is not its cause either. With matched lengths most bootstrap biases of Δ are smaller (dpo 0.0008 vs 0.0043 in full_post; sft 0.0048 vs 0.0084); the cause is not checked. Still running: diagnostics (27579383), min30 (27579385); the summary job follows.
