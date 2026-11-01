# Tunnel Claude reports

Newest at the bottom. No document text (Dolma, Pile or rollout windows) in this file (CLAUDE.md).

## 2026-11-01 15:49, Exp 2 full_post diagnostics: jobs submitted and running

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

## 2026-11-01 15:50, Exp 2 item 3: `full_post_lenmatch` finished (job 27579384, 4 min)

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

## 2026-11-01 15:51, Exp 2 item 3: `full_post_min30` finished (job 27579385)

Docs under 30 tokens dropped from every set, then one doc count: 6,986 docs per set. V: slope 1.005, median ln ratio −0.007.

| set | Δ min30 (bias-corrected) [basic 95%] | median ln ratio, min30 |
|---|---|---|
| stage1 | +0.0357 (+0.0341) [+0.0265, +0.0418] | −0.119 |
| main | −0.0163 (−0.0180) [−0.0250, −0.0110] | −0.218 |
| sft | −0.0386 (−0.0457) [−0.0530, −0.0381] | −0.660 |
| dpo | −0.0416 (−0.0441) [−0.0508, −0.0376] | −0.437 |
| instruct | −0.0329 (−0.0371) [−0.0440, −0.0300] | −0.460 |

Reading: as with lenmatch, Δ keeps its sign and size, and the offsets barely move, so docs under 30 tokens do not drive either. Diagnostics job 27579383 is at the G44 bootstrap (dpo); then gainers, examples and figures; the summary job follows.

## 2026-11-01 16:05, Exp 2 full_post diagnostics: all results in

Diagnostics job 27579383 finished 15:54 (all three jobs on `mit_normal`, 4-9 min each). G39's checks passed: doc counts, χ (max relative difference 0) and slopes equal the published `full_post`. The summary job was cancelled while pending and `s11` was run on the login node (reads JSON, seconds). Full tables: `exp2_rollout_gap/results/full_post_diagnostics_summary.md`; findings also in design.md under G39-G46.

Answer to Sheng-Yu: panels (a)-(b) show each distribution without pairing concepts, while (c) pairs them, and most of what (c) shows is concepts trading places: sorting both distributions keeps only 14-27% of the per-concept squared distance (V 5%), so 73-86% of it cannot appear in (a)-(b). What does appear is a median shift of −0.05 to −0.29 in log10 and a spread 9-25% wider (sd of ln χ 1.86-2.13 vs train 1.70). "Most concepts appear less" follows from χ's fixed total: the concepts that rise hold 55-65% of the χ mass (26-43% in train), spread over thousands of concepts (top 30 gainers take 12-19% of the moved mass, top 1,000 take 60-68%). Length explains none of it (item 3).

| item | result |
|---|---|
| 1 χ mass | Mass moved (TV) 13-38% (V 2%); top-10 share 6-7% in every set; top 1,000 41% train, 43-49% rollouts. Largest gainers mostly concepts already common in train (1106, 1204) plus some rising from χ ≈ 3 (924, 982); two dpo/instruct gainers (70, 1902) sit at positions 0-3 for 21-30% of their activation and take 65-79% of their χ from docs under 30 tokens. No top-30 gainer has an Exp 1 name |
| 2 slope vs change | Trend describes 0.03-1.1% of the per-concept variance. Proposed companion statistic: excess dispersion, sd 0.53 (stage1), 0.83 (main), 1.31 (sft), 1.19 (dpo), 1.24 (instruct) in ln units, V 0 |
| 3 length | Δ and medians barely move: e.g. sft Δ −0.034 → −0.036 (lenmatch) → −0.039 (min30), median ln ratio −0.67 → −0.67 → −0.66 |
| 8 range | Correction to my review note: stage1's Δ stays positive in the middle 16 bins (+0.017 [+0.009, +0.023]), so it does not come from the rare end only. For main and the post-trained sets the middle bins give a negative Δ, the rare end adds to it and the top bin offsets it (without the rarest 3 bins Δ is −0.007 to +0.005; without the top bin −0.028 to −0.064) |
| 5 (partial) | Bias-corrected full_post Δ: stage1 +0.029, main −0.016, sft −0.042, dpo −0.038, instruct −0.033 |

New files: `results/full_post_diagnostics.json`, `results/full_post_{lenmatch,min30}_distribution_summary.json`, `results/full_post_diagnostics_summary.md`, 12 figures `figures/full_post_<set>_{scatter,hist_shifted}.png`; example windows on pool only (`DATA/full_post/diagnostics_gainers.md`). Nothing uploaded to the Space.

## 2026-11-01 16:30, Exp 2 plan: name and test the concepts that moved (design rows G47-G52), waiting for Angela's OK

1. Concepts: top 10 gainers + top 10 losers by χ mass change per rollout set (G41) = 100 (concept, set) entries = 41 distinct concepts (21 gainers, 22 losers), all slope concepts; plus 20 controls (4 per set, |ln ratio| ≤ 0.1 in that set). 61 concepts total.
2. One rollout set per concept: the selecting set where it moved most. All 100 pairs would cost about $16 expected, over the $15 stop.
3. Windows (CPU job, Exp 1 E1-E9 rules): 40 naming windows from Dolma V (all 9,955 docs) and 40 from that set's rollouts; quiz windows (50 firing + 50 non-firing) from docs disjoint from the naming docs on each side. Text stays on pool.
4. Labels as F1-F8: Opus 5.5 names (N4 prompt), Sonnet 5.5 detection quiz (N5), each name quizzed on both sides (4 quizzes per concept), balanced accuracy (N7).
5. Agreement (G50): names agree if both cross gaps (own name minus the other side's name, on each side's windows) are ≤ 0.13, the 95th percentile of Exp 1's F-run gap (sd 0.062). Gainers and losers compared with the controls' agree rate.
6. N10 judge on (Dolma name, rollout name) plus a negative control, reported but unvalidated (as in Exp 1), so it does not set the flag.
7. Cost: 122 names ≈ $1.34 + 4,880 quiz prompts ≈ $7.95 + 122 judge ≈ $0.18 = ≈ $9.5 expected (F-run per-request costs). Hard stop $15 by the F7 guard (spent + worst case of the next chunk ≤ $15), own ledger.
8. Runs as two sbatch jobs (windows, then labels with a dependency) so it finishes without the session; mail on END/FAIL.
9. Output: `results/full_post_moved_summary.json` and `.md` (per concept: both names, 4 scores, gaps, agree flag, judge); text and raw outputs on pool only.

## 2026-11-01 16:15, Exp 2 moved-concepts naming: jobs submitted, pending

G47 updated (Angela): 4 controls per set, each an unmoved concept (|ln ratio| ≤ 0.1 in that set, slope concept, testable on both sides) within ±500 χ_train ranks of a randomly drawn moved concept of that set. Code committed (`46bebbe`).

| job | id | state |
|---|---|---|
| windows (s12) | 27582716 `mit_normal`, 27582717 `mit_preemptable` | pending (first to start cancels the other) |
| labels (s13, paid, $15 guard) | 27582718 `mit_normal`, 27582719 `mit_preemptable` | waiting on the windows job |

Concepts: 61 by construction (41 moved + 20 controls); expected cost ≈ $9.5 (122 names, 4,880 quiz prompts, 122 judge requests at F-run per-request costs). Final count of concepts testable on both sides, and the cost from it, will be appended when the windows job ends.
