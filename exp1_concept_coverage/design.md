# Exp 1: Concept coverage of Olmo 3 pretraining data

Status: draft written 2026-10-17. Every row in the decision tables was reviewed by Angela on 2026-10-17 (tutorial Chunk 4), and the doc was checked against Sheng-Yu's outline. Rows marked **VERIFY** get checked in the pilot. No code runs until this file is committed.

## Question
Using an off-the-shelf SAE on Olmo-3-1025-7B, which concepts are over- or underrepresented in Olmo 3's pretraining data, and does each concept fire on the same content in the documents used to name it and in documents held out from naming?

Maps to Sheng-Yu's RQ1 (are SAE concepts faithful?), RQ2 (SAE for coverage, then an LLM checks each direction on a train/val split) and the item "no training for SAEs for now; find concepts under/overrepresented given the training data". RQ1a (does the SAE miss concepts?) is out of scope; the outline marks it as unsolved.

Train and val are random shard-level splits of one distribution. The faithfulness test therefore asks whether a name holds on unseen docs of the same kind. It does not test a shift to different data.

## What each split is used for
| Split | Used for | Never used for |
|---|---|---|
| Train (80%, by shard) | Coverage (Eq. 1-2), top documents, decile samples. Contains T1 and T2 | Scoring a name on the docs it was written from |
| T1, T2 (two disjoint val-sized shard subsets of train) | One name written from each. T1 vs T2 name agreement = baseline from labeler and sampling noise. T1 name quizzed on T2 for pilot tuning only. Coverage noise floor | Scoring a name on the docs it was written from |
| V (20%, by shard) | One name written from V, shown next to T1's. T1 name quizzed on V (the reported score). Coverage comparison with train | Quizzing the V name; any pilot tuning |
| Pile, SAE training data (`chanind/pile-uncopyrighted-olmo-3-1024-abbrv-2B`, built from `monology/pile-uncopyrighted` files `train/00`-`01`) | Names for concepts missing from our sample | Any score, coverage number or SAE metric |
| Pile, held out from the SAE (`monology/pile-uncopyrighted` file `train/02`) | Baseline for SAE metrics in the pilot (row 22) | Names, coverage, quiz scores |

Rule: a name is never quizzed on the docs it was written from.

All Dolma splits are held out from the SAE (trained on the Pile) and from the names written from other splits. None is held out from the model, which trained on the whole stage 1 mix.

## Decisions
| # | Choice | Reason | Alternatives rejected | Source |
|---|---|---|---|---|
| 1 | Model `allenai/Olmo-3-1025-7B` (Base), revision `a81bae42db3975be1671e27b9c9a56da1a9f980f`; the run logs the revision it loads | The SAE was trained on this model's activations, and this is the model trained on Dolma 3. The SAE config records no model revision, so we pin one | Think/Instruct/RL-Zero: deferred to Exp 2 (the outline's "[ambitious]" todo compares Base with post-trained models on post-training data) | SAE `cfg.json` `model_name: allenai/Olmo-3-1025-7B`, `model_from_pretrained_kwargs: {}`; model card https://huggingface.co/allenai/Olmo-3-1025-7B, section "Model Details" → "Stage 1: Initial Pretraining", "Stage 2: Mid-training", "Stage 3: Long Context"; Olmo 3 report arXiv:2512.13961; HF API sha, 2026-10-17 |
| 2 | SAE `decoderesearch/olmo-3-saes`, `olmo-3-1025-7b/btk-mat-layer-16-k-100` | Hook = output of 0-indexed layer 16 = 17 of Olmo's 32 layers, about 0.53 of the depth. The CG paper attached SAEs at mid-to-deep layers; its footnote 3 says the layer was chosen by the SAE creators and that "deeper layers have a tendency to represent higher-level, sentence- or discourse-level abstractions". All three layer SAEs come from one training run with the same data, k and widths, so the layer choice changes depth only | Layer 4: closer to token identity. Layer 28: 4 layers from the output; not tested here | Model `config.json` `num_hidden_layers: 32`; CG paper Sec. 4.1 and footnote 3; SAE `runner_cfg.json` run_name `btk-mat-olmo-3-1025-7b-multi-layer-k100` |
| 3 | Data `allenai/dolma3_mix-6T-1025-7B` (stage 1 mix) | The card calls it "the collection of data used during the pretraining stage to train the Olmo-3-1025-7B model": 5.93T tokens, 3.87B docs, about 97.5% of training tokens | `dolma3_mix-6T`: Olmo-3-1125-32B's mix. `dolma3_pool`: pre-mix pool. Dolmino and Longmino mixes: excluded by scope; the model sees them last, so their effect may exceed their 2.5% token share (untested) | Dataset card; model card "Stage 1: Initial Pretraining": "5.93T tokens", "Coverage: 97.53%+ of total pretraining budget" (consistent with 5.93T / (5.93T + 100B + 50B), the stage 2/3 sizes on the same card). The model card links `allenai/dolma3_mix-6T-1025`, which redirects (HTTP 307) to `dolma3_mix-6T-1025-7B`; arXiv:2512.13961 |
| 4 | Allocate sampled docs across sources by token share (common_crawl 76.07%, olmocr 13.57%, stack_edu 6.89%, finemath 2.56%, arxiv 0.86%, wiki 0.04%) | The model learns per token, so sources are weighted by tokens. Sources differ in doc length (table below), so token share and doc share give different samples. Picking shards uniformly would skew the mix: olmocr holds 40.5% of the 65,718 shards and 13.57% of the tokens | Doc share (equal to uniform random docs): olmocr falls to 2.2% of the sample, about 6× below its training weight. Uniform over shards. First N docs of the stream (ordered by folder) | Dataset card table; HfApi `list_repo_tree`, 2026-10-17 |
| 5 | Within a source: pick shards with probability proportional to compressed file size, then uniform docs within each shard; log each shard's doc count. Docs per shard is a parameter set in the pilot | Shard sizes within a source vary widely (table below), so uniform shard picking would oversample small shards. Example: olmocr `art_and_design` (3,187 shards, 1.4 GB) and `adult_content` (2,090 shards, 0.1 GB) would supply about 20% of olmocr docs while holding 0.25% of its bytes. Fewer docs per shard spreads the sample across topic folders but downloads more | Uniform over shards (the earlier plan; its VERIFY item "shard sizes within a source are similar" failed, see the shard size table). Sequential reading | HfApi `list_repo_tree`, 2026-10-17 (the recursive listing returned all 65,718 files). **VERIFY** (pilot): `[REMOVED]` counts per olmocr folder |
| 6 | Random 80/20 split **by shard**, stratified by source, seed 0. T1 and T2 are carved out of train by shard the same way | Docs in one shard share a topic folder, so a doc-level split would put near-neighbors on both sides and inflate train/val agreement. Building T1, T2 and V the same way keeps the baseline and the test comparable. Train holds four val-sized subsets, which leaves room for T1 and T2 | Doc-level split. 50/50: no room for T1 and T2 inside train. A released Olmo validation set: the outline mentions one, but searches of allenai datasets on HF ("valid", "heldout", "eval-data", "dolma3", "paloma") found no Olmo 3 validation set | Kimia (to confirm); HF API search, 2026-10-17 |
| 7 | Duplicate check: exact hash of whitespace-normalized text plus MinHash near-duplicate detection; drop V docs that match a train doc and T2 docs that match T1; report counts per source | A doc copied into two splits would make a name look consistent when it is not. T2 gets the same treatment as V so the baseline matches the test | Hash of the first 200 normalized characters: flags docs that only share a header (license blocks, site menus) and misses near-duplicates that differ at the start | MinHash threshold to be cited from a dedup paper before use |
| 8 | Olmocr only: drop docs redacted as `[REMOVED]`, refill olmocr's quota with new draws, report counts per olmocr folder | Redacted text is not what the model trained on. Refilling keeps olmocr at its token share. Web text can contain the literal string, so other sources are not filtered | Drop from all sources; no refill | Dataset card note. **VERIFY** (pilot): whole-text vs partial redaction |
| 9 | Truncate to 1,024 text tokens, no BOS; report the truncation rate per source | SAE training context was 1,024 tokens; later positions are outside its training distribution. Long sources lose the most (olmocr averages 9,606 tokens per doc), so per-source rates make that visible | 2,048 or full length | `cfg.json` `context_size: 1024`; card tokens ÷ docs |
| 10 | Prepend nothing; feed doc tokens as they are | The Olmo 3 tokenizer has no BOS token. `prepend_bos: true` in the SAE config therefore had no effect: the SAE's training rows contain no special tokens, and SAELens passes `prepend_bos=False` when fetching activations | Prepend `<|endoftext|>` or another token: the SAE never saw one at position 0 | `tokenizer_config.json` `bos_token: None`, `add_bos_token: None`; no `bos_token_id` in `config.json`; training data `sae_lens.json` `begin_batch_token: "bos"`, 100 rows scanned with no special tokens; SAELens `activations_store.py` `run_with_cache(..., prepend_bos=False)` (installed 6.54.5). **VERIFY** (pilot): activation norms and reconstruction at position 0, then decide whether to exclude position 0 and record the evidence here |
| 11 | Keep all non-empty docs. Report the length distribution per source, and recompute the classes without docs under 30 tokens to count how many concepts change class | Follows the paper's convention, where Eq. 1 weights every doc equally. The check shows whether short, noisy docs drive the classes | Drop docs under 30 tokens: changes the mix, and the cutoff has no source | CG paper Eq. 1 |
| 12 | Precision set in the pilot: compare SAE reconstruction on 20 docs for (1) fp32 weights + bf16 autocast, (2) bf16 weights, (3) full fp32. Use bf16 weights only if they match (1); otherwise use (1). SAE in float32 | (1) matches SAE training: SAELens runs the LM under `torch.autocast(dtype=torch.bfloat16)` when `autocast_lm` is true. bf16 weights round every operation, including the residual sum the hook reads | Full fp32 as default: slower (memory fits: 7B × 4 B ≈ 28 GB) | `runner_cfg.json` `autocast_lm: true`, `dtype: float32`; SAELens `activations_store.py:667` (installed 6.54.5; SAE trained with 6.42.0). LM weight dtype during SAE training is not recorded |
| 13 | Hook = output of decoder layer 16 = `hidden_states[17]` | SAE hook name `model.layers.16` is that module's output; `hidden_states[0]` is the embeddings | `hidden_states[16]` (off by one) | `cfg.json` `hook_name`. **VERIFY** (pilot): `torch.equal(hook output, hidden_states[17])` |
| 14 | Coverage: Eq. 1 (per-doc mean over tokens) and Eq. 2 (normalize by the mean over concepts), per subset (train, T1, T2, V). Report three missing counts: never fires (χ = 0), χ < 1e-5, χ < e^{-5}. Main classes: missing < e^{-5}; under ≤ 10th pct and over ≥ 90th pct of the rest | Comparable with the paper. The paper prints the threshold as e^{-5} (≈ 0.0067); it may be a typo for 1e-5, and no code link was found, so all three counts are reported. The paper states the percentile cutoffs on Eq. 3 and says per-dataset classes are defined "similarly" with Eq. 2 | New thresholds | CG paper Sec. 3.1. The missing rate depends on sample size, so report it against N |
| 15 | Top documents ranked by max token activation; coverage uses the per-doc mean | Max shows where the concept fires most strongly. Ranking by the mean would favor short docs; ranking by the max favors long docs (more tokens, more chances of a high value), so the pilot compares top-doc lengths with the sample's | Rank by mean | Feature-dashboard convention; citable source to be verified before it is added. **VERIFY** (pilot): top-doc length distribution |
| 16 | Name the first 2,048 concepts plus every concept flagged over/under/missing, capped by the budget from the 20-concept cost pilot (3 names and a quiz per concept); if the cap binds, take a seeded random sample of the flagged ones. Missing concepts are named from their top Pile docs | The 2,048 prefix must reconstruct alone, so it holds the most general concepts. Missing concepts have no firing docs in our sample, so the SAE's own training data is the only place to find examples; these names get no train/val check and are marked "named from the Pile" | All concepts; a random sample; leaving missing concepts unnamed | Bussmann et al. 2025 (arXiv:2503.17547) abstract: "the smaller dictionaries learn general concepts, while the larger dictionaries learn more specific concepts"; `runner_cfg.json` `matryoshka_widths: [2048, 16384, 65536]` |
| 17 | Names written separately from T1, T2 and V, each from top examples plus examples sampled across activation deciles (deciles computed within each subset). Settings (text window per example, number of top examples, examples per decile, token marking, prompt) start from the Paulo et al. released code, cited by file. The pilot tests 1-2 alternatives (e.g. window length) by quizzing T1 names on T2 | The outline asks for top train docs with their names next to top val docs with their names. Starting from the cited method keeps names and quiz scores comparable with it; tuning on T1→T2 keeps V untouched | Train-only names (no val-side name to show). Our own settings without a pilot test | Sheng-Yu's outline; Paulo et al. 2024 (arXiv:2410.13928), abstract: explanations that "remain valid for a broader set of activating contexts". The "top-only explanations scored lower" claim gets checked in the paper body before it is cited |
| 18 | Quiz: the T1 name quizzed on V is the reported score (T1 on T2 is pilot tuning only). Detection (the quiz-taker sees the name and a shuffled 50/50 mix of firing and non-firing docs and picks the firing ones) and fuzzing (picks which highlighted tokens are correct). Firing docs sampled across activation deciles; non-firing docs from the Paulo et al. default, with "similar" non-firing docs tested on T1→T2 in the pilot. Metric: balanced accuracy | Tests a name on data it was not written from. Decile sampling covers weak activations. The choice of non-firing docs sets the quiz's difficulty, so it is fixed and cited. Balanced accuracy weights firing and non-firing docs equally | Visual check only; top-only firing docs; plain accuracy | Paulo et al. 2024 |
| 19 | Names, quiz and name-match judge via the Anthropic API (Message Batches). A stronger model writes the names and a different model takes the quiz. Model ids fixed after the 20-concept cost pilot and kept for the whole run; prompts, raw outputs, temperature and run date saved | One model in both roles could score its own phrasing higher, and the design could not separate that out. The quiz-taker's ability affects T1→T2 and T1→V equally, so their comparison holds | One model for both. Claude Code agents (not reproducible). Open model on GPU (weaker names, more setup) | Cost pilot |
| 20 | N set in the pilot so that most named concepts have at least k firing docs in each of T1, T2 and V (k = examples needed by row 17); report how many fall short. Cap: one job within the `mit_normal_gpu` time limit. Shard downloads run in a separate CPU job on `mit_normal` | T1, T2 and V are each 20% of N, so N must leave enough firing docs per subset to write names from | Largest N in a fixed 2 GPU-hours (no reason for 2 hours). Guessing N | Pilot; `sinfo -p mit_normal_gpu` for the time limit |
| 21 | Name match: Angela judges a seeded random sample of 50 concepts by eye ("same concept?" for T1 vs T2 and T1 vs V). A third model, different from the labeler and the quiz-taker, judges all named concepts; its numbers are reported only if it agrees with Angela's 50 calls, at an agreement threshold written here before the judge runs | Judging by eye does not scale to thousands of concepts. Checking the judge against hand calls tells us whether its numbers can be used | By eye only, with the quiz as the only number at scale | Sheng-Yu's outline (visual check of train vs val names) |
| 22 | Pilot baseline: run the same SAE metrics (fraction of variance explained, active concepts per token) on 50 seeded random docs from `monology/pile-uncopyrighted` file `train/02`, truncated to 1,024 tokens with no BOS, as for Dolma (rows 9, 10) | The SAE was trained on the Pile, so its numbers there show how well it works in its own domain. A drop on Dolma relative to this baseline is SAE error from the domain change, which is one of the gaps RQ3 asks us to separate from the concept gap. File `train/02` is held out because the SAE's training data was built only from files `train/00` and `train/01` | Rows of the SAE's own training data: the SAE was fit on them, so they would overstate its quality (CLAUDE.md: never evaluate on data used to fit). No baseline: Dolma numbers would have no reference | Angela, tutorial commit `5421f4a`; training data `sae_lens.json` `original_data_files: ["train/00.jsonl.zst", "train/01.jsonl.zst"]`; `monology/pile-uncopyrighted` revision `3be90335b66f24456a5d6659d9c8d208c0357119` |

### Doc length by source (row 4)
| Source | Avg tokens/doc | Token share | Doc share |
|---|---|---|---|
| common_crawl | 1,432 | 76.07% | 81.4% |
| olmocr_science_pdfs | 9,606 | 13.57% | 2.2% |
| stack_edu | 778 | 6.89% | 13.6% |
| finemath-3plus | 1,581 | 2.56% | 2.5% |
| rpj-proofpile-arxiv | 5,593 | 0.86% | 0.2% |
| dolma1_7-wiki-en | 592 | 0.04% | 0.1% |

Tokens ÷ docs from the dataset card.

### Shard sizes by source (row 5)
| Source | Shards | Share of shards | Compressed GB | Min MB | Median MB | Max MB |
|---|---|---|---|---|---|---|
| common_crawl | 36,936 | 56.2% | 3,057 | 6.3 | 82.6 | 102.9 |
| olmocr_science_pdfs | 26,615 | 40.5% | 599 | 0.002 | 26.8 | 71.4 |
| stack_edu | 1,977 | 3.0% | 171 | 0.12 | 85.3 | 208.6 |
| finemath-3plus | 128 | 0.2% | 48 | 364.7 | 371.0 | 378.3 |
| rpj-proofpile-arxiv | 20 | 0.0% | 22 | 40.2 | 1,327.1 | 1,452.8 |
| dolma1_7-wiki-en | 42 | 0.1% | 3 | 78.2 | 80.3 | 85.3 |

HfApi `list_repo_tree` on `allenai/dolma3_mix-6T-1025-7B`, revision `2ca900fbe14e86c5c83d064d9f0882f1c0b8c05b`, 2026-10-17.

## Technical decisions
| # | Choice | Reason | Alternatives rejected | Source |
|---|---|---|---|---|
| T1 | Doc text, activations and names in `/orcd/pool/005/angela_h/exp1`; shard downloads in `/orcd/scratch/orcd/006/angela_h/exp1`, deleted after sampling | Pool has 1 TB free for persistent outputs; scratch suits transient downloads | Home (repo folder is public, shared quota). Scratch for outputs | `df -h`, 2026-10-17 |
| T2 | Sparse activations: latent id uint16, value fp16, position uint16 | d_sae 65,536 fits uint16 (0-65,535); positions ≤ 1,024. About 100 active latents × 4 B per token ≈ 6 GB for 16M tokens | Dense: 65,536 × 2 B = 131 KB per token ≈ 2.1 TB for 16M tokens, more than the 1 TB pool | `cfg.json` `d_sae`, `runner_cfg.json` `k: 100` |
| T3 | Parquet for doc and stat tables | Columnar and compressed; loads in pandas and filters by column | JSONL: larger and slower to filter | – |
| T4 | Numbered scripts, each saving its outputs to disk | Any step reruns alone, and outputs can be inspected between steps | One end-to-end script | – |
| T5 | `config.py` holds every constant, each tagged with its row in this file | One place to read and change a setting | Constants spread across scripts | – |
| T6 | s02 as a CPU sbatch job, s04 as a GPU sbatch job, s03 interactive in the tunnel | Heavy work goes through sbatch | Running on the login node | CLAUDE.md |
| T7 | `space/data/` is gitignored and uploaded only to the Space | It holds Dolma text excerpts, and the repo is public | Committing site data | CLAUDE.md repo rules |
| T8 | Static JSON site with one file per concept and per doc | The page loads one concept at a time; static hosting needs no server | One large JSON file | HF Space Static SDK (tutorial Chunk 9) |
| T9 | Pin revisions: model `a81bae42db3975be1671e27b9c9a56da1a9f980f`, SAE repo `ad1f790dd36d44b5b77b1d08ace6a6f48d121649`, dataset `2ca900fbe14e86c5c83d064d9f0882f1c0b8c05b` | A later push to any of these repos would otherwise change results silently | Loading `main` | HF API, 2026-10-17 |

New technical choices made while writing code get a row here before the code runs.

## Code structure
| File | Runs on | Reads | Saves |
|---|---|---|---|
| `config.py` | – | – | Constants with their row: model, SAE and dataset ids + revisions, seeds, split fractions, N, docs per shard, k, paths |
| `s01_list_shards.py` | CPU sbatch | HF API | `DATA/shards.parquet` (path, source, folder, bytes); `results/shards_summary.json` |
| `s02_sample_docs.py` | CPU sbatch | shards | Size-weighted shard draw, `[REMOVED]` filter + refill, shard → split (train/V; T1, T2 inside train), exact + MinHash dedup → `DATA/docs.parquet` (doc_id, source, folder, shard, split, subset, text); `results/sample_summary.json` (counts per source and split, removed, duplicates, lengths) |
| `s03_pilot.py` | GPU, interactive | 200 + 200 Dolma docs, 50 held-out Pile docs | `results/pilot_checks.json` (Dolma and Pile metrics side by side) |
| `s04_activations.py` | GPU sbatch | docs, plus a Pile sample for missing concepts | `DATA/acts/part_*.npz` (sparse token activations); `DATA/doc_stats.parquet` (per-doc mean, max and argmax position per latent); `results/activation_summary.json` |
| `s05_coverage.py` | CPU | doc_stats | `DATA/coverage.parquet` (χ per concept for train, T1, T2, V; classes; noise floor; <30-token check); `results/coverage_summary.json` |
| `s06_examples.py` | CPU | acts, docs | `DATA/examples/` (per named concept and subset: top-k windows and decile samples with tokens and activations) |
| `s07_label.py` | CPU, API | examples | `DATA/labels/raw/` (prompts, batch ids, raw outputs); `DATA/labels/names.json`; `results/label_run.json` (model ids, temperature, date) |
| `s08_score.py` | CPU, API | examples, names | `DATA/labels/scores.json` (quiz T1→T2 and T1→V, name-match judge, Angela's 50 calls); `results/score_summary.json` |
| `s09_site_data.py` | CPU | all above | `space/data/` |
| `sbatch/sample.sbatch`, `sbatch/acts.sbatch` | – | – | Job wrappers in the style of `tools/tunnel.sbatch`; logs in `logs/` |

`DATA` = `/orcd/pool/005/angela_h/exp1` (T1).

### Website data format (`space/data/`)
- `index.json`: one row per named concept: `{id, name_T1, name_V, match, quiz_bacc, chi_train, chi_V, class, named_from}`.
- `concepts/<id>.json`: `{id, names: {T1, T2, V | pile}, scores: {detection, fuzzing, match}, coverage: {chi: {train, T1, T2, V}, class, by_source}, hist: {bins, T1, V}, examples: {T1: [{doc_id, tokens, acts, max}], V: [...], deciles: {T1, V}}, correlated: [{id, cooccur, decoder_cos}]}`.
- `docs/<doc_id>.json`: `{doc_id, source, subset, tokens (≤ 1,024), top_concepts: [{id, name, mean, max}]}`.
- `distribution.json`: per concept log χ for train and V plus the noise band.

## Website (HF Space), mapped from the example visual
| Panel in example | Keep? | Our version | Serves |
|---|---|---|---|
| Label + autointerp score | Keep | T1 name and V name; detection and fuzzing balanced accuracy of the T1 name on V; name-match result | RQ1 faithfulness |
| Activation density histogram | Keep | T1 and V overlaid | Train/val distribution check |
| Top activations with token highlighting | Keep | T1 column next to V column, each with its name above it | Outline: top train docs + names next to top val docs + names |
| Subsample intervals | Keep | Examples from activation deciles, T1 and V | Whether weak activations mean the same thing as strong ones |
| Correlated features | Keep | Concepts that co-activate across docs, plus decoder cosine similarity | Outline: several directions firing on one concept |
| Positive/negative logits | Drop for now | Projecting a layer-16 direction through the unembedding skips 16 layers, so the logits say little | – |
| Neuron alignment, correlated neurons | Drop | About MLP neurons, which we do not study | – |
| (new) Coverage card | Add | χ train, χ V, class (missing/under/over), share of activation by Dolma source; flag for concepts named from the Pile | Outline: under/overrepresented concepts |
| (new) Doc view | Add | Click a doc: its top concepts with names | Outline: doc → concept view |
| (new) Distribution tab | Add | Layout to be proposed to Sheng-Yu for review; candidate: log χ train vs log χ V scatter with the noise-floor band | Outline: compare train/val concept distributions |

Rejected: generating pages with SAEDashboard. It produces this layout but has no train/val side-by-side view, and its Olmo 3 support is unverified.

## Pilot checks (before the full run)
1. `torch.equal(hook output, hidden_states[17])` (row 13).
2. SAE reconstruction: fraction of variance explained, and active concepts per token, on pilot tokens.
3. Reconstruction under three precision setups (row 12).
4. Position 0: activation norms and reconstruction; decide whether to exclude it (row 10).
5. Seconds per doc, and docs per shard (rows 5, 20).
6. `[REMOVED]` per olmocr folder; whole-text vs partial redaction (rows 5, 8).
7. Top-doc lengths vs the sample's length distribution (row 15).
8. Naming settings and non-firing doc choice, tested as T1 names quizzed on T2 (rows 17, 18).
9. Firing docs per concept in each subset, to set N (row 20).
10. 20-concept cost pilot for model choice and scope (rows 16, 19).
11. Pile baseline: checks 2 and 4 on 50 held-out Pile docs, reported next to the Dolma numbers (row 22).
