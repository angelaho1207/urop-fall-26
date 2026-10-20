# Exp 1 limitations (list only, not yet acted on)

Collected 2026-10-19 from design.md and the review of experiments 1-15. Each item says where it comes from.

## Input to the SAE
1. **Only the first 1,024 tokens of each doc are measured.** Later text of long docs is never seen: truncated share in the pilot was olmOCR 74%, common_crawl 35%, finemath 30%, stack_edu 18%. Concepts that occur late in long docs (e.g. results or reference sections) are undercounted. Row 9 rejected "2,048 or full length" but never listed a random 1,024-token chunk; the reason to reject it (the SAE was trained only on first-1,024-token rows, below) is not recorded.
2. **The SAE never trained on docs shorter than 1,024 tokens.** Its training data was built with `disable_concat_sequences: true`, and SAELens 6.37.6 (`tokenization_and_batching.py`, lines 82-101) keeps one row per Pile doc (its first 1,024 tokens) and drops shorter docs. About half of our docs are shorter (pilot median 724 tokens). Short docs are fed at their own length (no padding), and the model cannot see that a doc is about to end (each activation depends only on earlier tokens), so the gap is in content, not position: the SAE never trained on text typical of short docs or of the last part of any doc (sign-offs, footers, copyright lines), because every training row stopped at token 1,024 of a longer doc. The held-out Pile check (FVE 0.748, docs of all lengths) suggests it copes; FVE by doc length was not measured.
3. **The SAE fits Dolma worse than the Pile:** FVE 0.713 vs 0.748 (pilot; 400 Dolma vs 50 Pile docs; no interval). Every Dolma number carries this SAE error.

## Data scope
4. **Stage 2 and 3 data excluded** (Dolmino, Longmino; 2.5% of tokens). The model sees them last, so their effect may exceed their token share (row 3).
5. **The model saw every doc we sample.** Splits are held out from the SAE and from names, not from Olmo.
6. **Wiki has no V docs** (20 docs, one shard, all in train).
7. **Pile and Dolma overlap was not checked.** Both draw on web, arXiv, Wikipedia and code, so some docs may appear in both.

## Coverage classes
8. **"Missing" depends on the threshold:** 9,967 concepts at e^-5, 1 at 1e-5. The paper's text is ambiguous (row 14). Missing counts also depend on sample size.
9. **The paper's Eq. 2 classes mostly sort concepts by Matryoshka tier** (98.4% of "over" in the first 16,384 ids), which is why the Pile reference replaced them.
10. **Over/under are relative to the Pile.** The reference shapes the answer; the whole-dataset classes mostly reflect which collections each corpus includes (R6).
11. **The main (web-only) classes are noisy near the cut lines:** in the noise floor 87.7% of comparable concepts keep their class, so about 12% of labels flip from resampling alone.
12. **Why web text differs is untested.** Part of the Dolma web vs Pile-CC difference may come from how each pipeline extracted text from HTML, not from what the pages say.
13. **Rare-concept firing rates in the pilot came from 400 docs,** so rates below 1/400 could not be measured when N was chosen.

## Examples, names and quiz
14. **Ranking by max activation favors long docs** (top-doc median 1,024 tokens vs 724 for the sample; row 15).
15. **The weakest activations sit just above the SAE's single firing cutoff (0.442) and often look unrelated** to the concept; decile sampling includes them in names and quizzes.
16. **Names and quiz answers come from LLMs with default sampling** (temperature cannot be set on these models); results are reproducible only through the saved prompts and outputs, not by rerunning.
17. **Quiz scores depend on the non-firing windows chosen:** with neighbour windows instead of random ones, detection fell by 0.12 in the pilot. Reported scores use random windows.
18. **The faithfulness test covers 240 concepts (80 per class), web text only, and the detection quiz only** (no fuzzing). With 80 per class, class differences in the gap cannot be separated (intervals overlap).
19. **The name-match judge is unvalidated** (hand labels skipped), so its numbers are not used.

## Patterns
20. **Topic categories cover only the 240 named concepts;** with 80 per class, only differences of about 10 points or more can be read. Categories were proposed by an LLM.

## Scope
21. **One SAE, one layer (16).** Results may differ at layers 4 and 28 or with other SAEs.
22. **Not addressed:** RQ1a (does the SAE miss concepts?) and the model-output side of the project question (Exp 1 measures training data only).
