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

## 2026-11-01 16:22, Exp 2 moved-concepts naming: windows done, final count and cost

Windows job 27582717 finished 16:20 (149 s). Final selection (`results/full_post_moved_windows_summary.json`):
- 61 concepts: 20 gainers, 21 losers (counted by the kind in the set each concept was assigned to), 20 controls (4 per set, rank-matched, no redraws needed). By set: stage1 13, main 8, sft 19, dpo 10, instruct 11.
- All 61 fire in at least 90 docs on both sides, so all get both names (122 names).
- 10 concepts fire in nearly every doc, so fewer than 50 of their 200 non-firing candidates were all-zero windows (E9); the quiz is skipped on that side: 260, 446, 1106, 1321, 1831 (both sides), 983 (rollout side), 1362, 1483, 1546, 1593 (Dolma side). They keep their names and the judge but get no agree flag. 51 concepts are quizzed on both sides: 16 gainers, 16 losers, 19 controls.
- Final estimate: 122 names ≈ $1.34 + 4,280 quiz prompts ≈ $6.98 + 122 judge requests ≈ $0.18 = ≈ $8.5 (hard stop $15).

Labels job (27582718 / 27582719) is next in the queue.

## 2026-11-01 16:30, Exp 2 moved-concepts naming: labels job stopped, API key rejected; $0 spent

Labels job 27582718 started 16:21 and stopped at the first free token-count call: the API answers 401 `invalid x-api-key` (checked again from the login node, request `req_011Cgcv9NuFWfb5dKncygiye`). `~/.anthropic_key` exists (chmod 600, 109 bytes, last changed 2026-10-18 01:48), so the key itself was revoked or expired. Nothing was sent: `DATA/full_post/labels/moved/` is empty and no ledger exists, so $0 spent. The windows (s12) are done and stay valid.

Fix in s13 (committed): the token counter now retries only rate-limit, connection and server errors; any other error (such as an invalid key) stops at once instead of retrying.

Needed from Angela: a valid key in `~/.anthropic_key` (chmod 600). Then rerun the labels job: `cd exp2_rollout_gap && sbatch -p mit_normal sbatch/moved_labels.sbatch` (or tell tunnel Claude to submit it). Same $15 guard.

## 2026-11-01 16:41, Exp 2 moved-concepts naming: new key valid, labels job resubmitted

Angela replaced `~/.anthropic_key` (chmod 600, changed 16:38; the key was never shown to Claude). One free token-count call succeeded. Labels job resubmitted: 27585445 (`mit_normal`), 27585446 (`mit_preemptable`); first to start cancels the other. Same $15 guard; expected ≈ $8.5.

## 2026-11-01 17:06, Exp 2 moved-concepts naming: results

Labels job 27585445 finished 17:03. Spent $9.10 of $15 (names $1.74, quiz $7.15, judge $0.22); every batch request came back. Per-concept table (both names, 4 scores, gaps, agree, judge): `exp2_rollout_gap/results/full_post_moved_summary.md`. Findings added under G52 in design.md.

| group | concepts | scored | agree (G50, gaps ≤ 0.13) | agree, both own-name scores ≥ 0.6 (post hoc) | mean gap on Dolma / rollouts | judge same, true / mismatched pairs |
|---|---|---|---|---|---|---|
| gainers | 20 | 14 | 12 of 14 | 11 of 12 | 0.067 / 0.035 | 0.65 / 0.05 |
| losers | 21 | 16 | 13 of 16 | 6 of 9 | 0.012 / 0.040 | 0.75 / 0.10 |
| controls | 20 | 15 | 15 of 15 | 9 of 9 | 0.012 / 0.000 | 0.95 / 0.00 |

- Disagree: 670 (main gainer, gaps 0.18 / 0.16), 42804 (main gainer, 0.20 / 0.05), 85 (sft loser, 0.14 / 0.02), 842 (sft loser, −0.01 / 0.16), 1432 (instruct loser, 0.04 / 0.16).
- By eye: the top post-trained gainers are repetition loops, garbled text, document-start tokens and line breaks, and both sides give them the same name. Losers are diffuse prose features: fluent human web prose on the Dolma side, assistant-style or generic prose on the rollout side.
- 15 of 45 scored concepts have an own-name score below 0.6 on a side. For those the quiz has little power, so agreement there carries little weight.
- Unscored: 10 concepts lacked non-firing windows (s12). 6 more (70, 1902, 235, 1032, 1387, 2028; first-token, first-letter, word-piece and "of" concepts) lost more than 10 of 100 windows because 193 quiz prompts hit the 200-token output cap (F7). 2 refusals (3565, still scored).

Decision for Angela: re-send only the 195 failed quiz prompts with a 1,000-token cap, so the 6 surface concepts get scores? Worst case ≈ $1.45 (195 × [input bound × 1.1 + 1,000 output] at batch prices), so the total stays ≤ $10.6 under the $15 guard. This needs a new design row (G53, deviation from F7's cap) before it runs. Nothing is sent without a go.

## 2026-11-01 17:23, Exp 2: G53 resend submitted; garbled-rollout check plan (G54-G59)

G53 resend: 193 quiz prompts that hit the 200-token cap (the 2 refusals are not re-sent, so 193, not 195), rebuilt and checked against the saved quiz key, cap 1,000. Worst case $1.52 on top of $9.10 spent, same $15 guard. Jobs 27590332 (`mit_normal`) / 27590333 (`mit_preemptable`).

Garbled check plan (design.md G54-G59, committed before code):
- G54: per-doc mean NLL under the encoder model (main, pinned revision, bf16), on the ids the SAE saw; token 0 has no prediction (no BOS). Sets: all 9,955 V docs and every encoded rollout of stage1, main, sft, dpo, instruct.
- G55: 120 parts of 500 docs, lock-file workers (G21): 2 GPU workers on `mit_preemptable`, 1 on `mit_normal_gpu`; CPU finisher as two copies, resubmits workers if parts are missing, then runs the analysis; mail on END/FAIL. About 1-2 GPU hours, $0 API.
- G56: threshold = V's 99th percentile, written to a file before any rollout NLL is read; same rule for every set. Report share flagged, token-weighted share, NLL quantiles, plus short-doc share and overlap with G14 loops.
- G57: 10 random flagged + 10 just-below rollouts per post-trained set, in `DATA/full_post/garbled_examples.md` (pool only).
- G58: drop flagged docs from every set, one G16 count, then Δ vs V (bias-corrected), excess dispersion, median ln ratio, and the G41 top-10 gainers' new ranks; each next to its `full_post` value.
- G59: V's NLL is on text the model trained on, so the threshold sits lower than a held-out one would.

Also fixed: the G52 findings edit had cut the "Qualitative results" heading in design.md; restored.

## 2026-11-01 17:30, Exp 2: G53 resend results; garbled check running

G53 resend (job 27590332, 17:24-17:27): 193 of 193 prompts answered (largest answer 943 tokens). Spent $9.74 of $15 in all. `results/full_post_moved_summary.md` regenerated.

| group | scored | agree (G50) | agree, both own-name scores ≥ 0.6 (post hoc) |
|---|---|---|---|
| gainers | 16 of 20 | 13 of 16 | 12 of 13 |
| losers | 16 of 21 | 14 of 16 | 7 of 9 |
| controls | 19 of 20 | 18 of 19 | 12 of 13 |

- The 6 surface concepts: 70, 235, 1387, 2028 agree. 1902 (dpo gainer, gaps 0.19 / −0.10) and 1032 (stage1 control, −0.14 / 0.16) disagree.
- 10 already-scored concepts had 1-3 re-sent prompts; scores moved ≤ 0.025. One flag flipped: 85 (sft loser, gap on Dolma 0.138 → 0.12) now agrees.
- Disagreements now: 670, 42804, 1902, 842, 1432, 1032. Only 670 has both gaps > 0.13 (each name wins on its own side). For 1032 the rollout name beats the Dolma name on both sides, so the G50 flag there marks a better name, not a change of meaning.

Garbled check (G54-G59): 3 NLL workers running since 17:27 (27590760, 27590761 `mit_preemptable`; 27590762 `mit_normal_gpu`; L40S, 0.077 s/doc), 6 of 120 parts done, about 25 min left. Finisher 27590764 (`mit_normal`) is running and waiting; its copy 27590763 was cancelled. s15 was dry-run end to end on fake NLL values (outputs in scratch only) before submission.

## 2026-11-01 17:51, Exp 2 garbled check: job status

All 120 NLL parts are on disk (V and each of the 5 rollout sets: 20 of 20). The 3 workers ended without errors. Finisher 27590764 (`mit_normal`, running since 17:27) checks every 5 min, so s15 starts by about 17:56. Expected s15 run time: 10-15 min (the diagnostics job, with similar bootstrap work, took 8.7 min). Results expected around 18:10; mail on END/FAIL. No API cost.

## 2026-11-01 18:05, Exp 2 garbled-rollout check: results

Finisher 27590764 ran s15 17:52-17:57, no errors. Results: `exp2_rollout_gap/results/full_post_garbled_summary.md` (and `.json`, `full_post_garbled_threshold.json`, `full_post_noflag_distribution_summary.json`). Findings added under G59 in design.md. Examples for Angela: `DATA/full_post/garbled_examples.md` (pool only).

Threshold 3.816 nats (V's 99th percentile; V median 2.21).

| set | flagged | token-weighted | flagged, docs with 300+ tokens | Δ vs V bias-corrected, full_post → noflag | top 10 gainers still top 10 / top 30 |
|---|---|---|---|---|---|
| V | 1.0% | 0.8% | 0.5-0.8% | – | – |
| stage1 | 21.9% | 21.7% | 19-21% | +0.029 → +0.014 | 9 / 10 |
| main | 20.5% | 21.1% | 17-21% | −0.016 → −0.031 | 7 / 10 |
| sft | 23.4% | 22.3% | 21-24% | −0.042 → −0.044 | 7 / 9 |
| dpo | 24.4% | 19.6% | 18-21% | −0.038 → −0.042 | 7 / 8 |
| instruct | 8.3% | 2.3% | 1-2% | −0.033 → −0.041 | 7 / 8 |

- Short docs are flagged more in every set, but for stage1, main, sft and dpo long rollouts are flagged at 17-24% too. Instruct's flags are mostly short docs.
- The NLL flag and G14's loop flag pick different docs (at most 1.1% of flagged docs are loops): loops are predictable and score low NLL.
- By eye: random flagged sft and dpo rollouts are mostly garbled (mixed scripts, broken code, word salad). Some flagged instruct rollouts are short fluent questions or titles. The rollouts just below the threshold are also often garbled, so the rule misses some garbled text and catches some short fluent text.
- After the filter (5,751 docs per set): every Δ interval still excludes 0. Excess dispersion sd changes by ≤ 0.03 and median ln ratio by ≤ 0.02, so garbled docs do not explain the dispersion. Gainers that drop out: 2044 (the garbled-text concept) in sft, rank 7 → 38; document-start concepts 70 and 1902 in dpo and instruct, ranks 32-57.
- Open: the doc count fell from 7,985 to 5,751, and count alone moves Δ (G16). A random drop to 5,751 docs per set (no flag) would separate the count's share of the Δ change from the filter's. CPU only, about 5 min; needs a design row and Angela's go.

## 2026-11-01 18:15, Exp 2 doc-count control (G60): submitted

G60 (committed before code): 20 seeds; every set (V, 5 generators, their no-loop versions) drawn at random without the flag to 5,751 docs, then the same pipeline as noflag (`s15_garbled.measure`, refactored out of G58's inline code). One extra task reruns `measure()` on G58's docs and must reproduce the published noflag numbers exactly. Reported per set: bias-corrected Δ, raw Δ, excess dispersion sd, median ln ratio; full_post, noflag, control mean ± sd [min, max]; count effect = control mean − full_post, filter effect = noflag − control mean (in control sd).

Jobs: array 27595867 (tasks 0-19 seeds, task 20 check; `mit_normal`, 4 CPUs, 16 GB, 1 h), summary 27595869 after the array (`afterany`). Mail on END/FAIL for both. Expected about 5-10 min per task, $0.

## 2026-11-01 18:33, Exp 2 doc-count control (G60): results

Array 27595867 (20 seeds + check) and summary 27595869 completed. Check: `measure()` reproduces the published noflag numbers (max difference 0.0). Full tables: `exp2_rollout_gap/results/full_post_countctl_summary.md`; findings under G60 in design.md.

Bias-corrected Δ vs V:

| set | full_post | noflag | control (20 draws, 5,751 docs) mean ± sd [min, max] | count effect | filter effect (control sd) |
|---|---|---|---|---|---|
| stage1 | +0.0291 | +0.0136 | +0.0315 ± 0.0035 [+0.0251, +0.0367] | +0.0024 | −0.0179 (−5.1) |
| main | −0.0160 | −0.0309 | −0.0159 ± 0.0033 [−0.0230, −0.0096] | +0.0001 | −0.0150 (−4.5) |
| sft | −0.0422 | −0.0438 | −0.0403 ± 0.0023 [−0.0446, −0.0362] | +0.0019 | −0.0035 (−1.6) |
| dpo | −0.0382 | −0.0421 | −0.0371 ± 0.0027 [−0.0436, −0.0324] | +0.0011 | −0.0050 (−1.9) |
| instruct | −0.0326 | −0.0412 | −0.0312 ± 0.0034 [−0.0384, −0.0257] | +0.0014 | −0.0100 (−2.9) |

- The count barely moves Δ (≤ +0.002). The filter lowers Δ in every set. For stage1, main and instruct the noflag value lies outside all 20 draws; for sft and dpo it lies inside.
- Excess dispersion sd: filter effects −0.024 to +0.021 against values of 0.51-1.33. Median ln ratio: filter effects within ±0.015.
- The sd units assume noflag's draw spread matches the control's; noflag draws from a smaller pool, so they are approximate.
