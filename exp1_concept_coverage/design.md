# Exp 1: Concept coverage of Olmo 3 pretraining data (DRAFT for review)

Status: draft written 2026-10-18 from the local session. Review every row in Chunk 4 before any code runs. Rows marked **OPEN** need a decision from Angela; rows marked **VERIFY** get checked in the pilot.

## Question
Using an off-the-shelf SAE on Olmo-3-1025-7B, which concepts are over- or underrepresented in Olmo 3's pretraining data, and does each concept fire on the same content in documents used to label it (train split) and documents held out from labeling (val split)?

Maps to Sheng-Yu's RQ1 (are SAE concepts faithful?) and the Oct 13 item 1 (under/overrepresented concepts, no SAE training).

## What each split is used for
| Split | Used for | Never used for |
|---|---|---|
| Train (80%) | Coverage (Eq. 1-2), top documents, interval samples, writing concept labels | Scoring labels |
| Val (20%) | Coverage comparison with train, top documents shown next to train's, scoring labels written from train | Writing labels |
| Noise floor (two disjoint 20%-sized subsets of train) | How much coverage and top documents change from sampling alone | Anything else |

Both splits are held out from the SAE (trained on the Pile) and from the labels. Neither is held out from the model, which trained on the whole stage 1 mix.

## Decisions
| # | Choice | Reason | Alternatives rejected | Source |
|---|---|---|---|---|
| 1 | Model `allenai/Olmo-3-1025-7B` (Base) | The SAE was trained on this model's activations, and this is the model trained on Dolma 3 | Think/Instruct: SAE not trained on them; their extra data is post-training | SAE `cfg.json` `model_name`; model card |
| 2 | SAE `decoderesearch/olmo-3-saes`, `olmo-3-1025-7b/btk-mat-layer-16-k-100` | Layer 16 of 32 is mid-depth. The CG paper attached SAEs at mid-to-deep layers (Llama 19/32, Gemma 20/26) and notes deeper layers carry higher-level, sentence- or discourse-level abstractions | Layer 4: closer to token identity. Layer 28: four layers from the output, where directions tend to track next-token prediction | CG paper Sec. 4.1 and footnote 3; SAE `runner_cfg.json` |
| 3 | Data `allenai/dolma3_mix-6T-1025-7B` (stage 1 mix) | 5.93T of 6.08T training tokens (97.5%) | `dolma3_pool`: pre-mix pool, not what the model saw. Dolmino and Longmino mixes: 2.5% of tokens; separate experiment if needed | Model card; dataset card |
| 4 | Sample docs stratified by source token share (common_crawl 76.07%, olmocr 13.57%, stack_edu 6.89%, finemath 2.56%, arxiv 0.86%, wiki 0.04%) | Keeps the source mix the model saw. Shard counts per source do not match token shares, so picking shards uniformly would skew the mix | Uniform over shards; first N docs of the stream (order is by folder, so it would be one source) | Dataset card table; HF file listing |
| 5 | Within a source: seeded random shards, then seeded random docs per shard | Approximates uniform doc sampling within a source | Sequential reading | **VERIFY**: shard sizes within a source are similar (HF API file sizes); get the full file list with `HfApi.list_repo_files` (the plain listing stops at 100,000 files) |
| 6 | Random 80/20 doc-level split, stratified by source, seed 0 | Kimia's suggestion (to confirm). Train must hold at least two val-sized subsets for the noise floor | 50/50: no room for the noise floor inside train | Kimia (to confirm) |
| 7 | Cross-split duplicate check: hash of whitespace-normalized text, plus hash of the first 200 normalized characters; report counts | A doc copied into both splits would make a label look consistent when it is not | None | – |
| 8 | Drop docs containing `[REMOVED]`; report the count | Redacted text is not what the model trained on | Keep them | Dataset card note |
| 9 | Truncate to 1,024 tokens; report the fraction of docs truncated | SAE training context was 1,024 tokens; later positions are out of its training distribution | 2,048 or full length | `cfg.json` `context_size` |
| 10 | Prepend BOS; exclude BOS from all averages and top examples | SAE trained with `prepend_bos: true` and `exclude_special_tokens: true`, so it never learned BOS activations | Include BOS | `cfg.json` metadata. **VERIFY** whether the Olmo 3 tokenizer adds BOS on its own |
| 11 | **OPEN**: minimum doc length | Eq. 1 gives every doc equal weight, so a 5-token doc counts as much as a 1,024-token doc. Options: (a) keep all non-empty docs (paper's convention), (b) drop docs under 30 tokens (less noise, changes the mix). Report the length distribution either way | – | CG paper Eq. 1 |
| 12 | Model in bfloat16, SAE in float32 | SAE weights are float32; the LM ran under autocast during SAE training | Full float32 LM: twice the memory | `runner_cfg.json` (`autocast_lm: true`, `dtype: float32`). **VERIFY**: reconstruction error, bf16 vs fp32 LM, on 20 docs |
| 13 | Hook = output of decoder layer 16 = `hidden_states[17]` | SAE hook name `model.layers.16` is that module's output; `hidden_states[0]` is the embeddings | `hidden_states[16]` (off by one) | `cfg.json` `hook_name`. **VERIFY** with a forward hook in the pilot |
| 14 | Coverage: paper's Eq. 1 (per-doc mean over tokens) and Eq. 2 (normalize by mean over concepts); missing < 1e-5, under ≤ 10th pct, over ≥ 90th pct of non-missing | Comparable with the paper | New thresholds | CG paper Sec. 3.1. The missing rate depends on sample size, so report it against N |
| 15 | Top documents ranked by max token activation; coverage uses the per-doc mean | Max shows where the concept fires most strongly. Ranking by the mean would favor short docs | Rank by mean | Standard in SAE feature dashboards (example visual) |
| 16 | Label the first 2,048 concepts plus every concept flagged over/under/missing | The 2,048 prefix must reconstruct alone, so it holds the most general concepts. Labeling all 65,536 twice is too much for one night | All concepts; a random sample | Bussmann et al. 2025 (arXiv:2503.17547): "smaller dictionaries learn general concepts" |
| 17 | Labels written from train only, from top examples plus examples sampled across activation deciles | Top-only explanations miss the rest of the activation distribution and scored lower | Top-only | Paulo et al. 2024 (arXiv:2410.13928) |
| 18 | Label scoring on val: detection (scorer sees the label and a shuffled mix of val activating and non-activating docs, predicts which activate) and fuzzing (predicts which highlighted tokens are correct); metric is accuracy | Tests the label on data it was not written from, which is the train/val faithfulness test | Visual check only | Paulo et al. 2024 |
| 19 | Labeler and scorer: Anthropic API, Message Batches, fixed model id, prompts and raw outputs saved | Reproducible and citable | Claude Code agents (not reproducible); open model on GPU (weaker labels, more setup) | Model chosen after a 20-concept cost pilot |
| 20 | Sample size N set after the pilot: largest N that fits a ~2 GPU-hour job | Throughput is unknown until measured | Guessing N | Pilot |

## Website (HF Space), mapped from the example visual
| Panel in example | Keep? | Our version | Serves |
|---|---|---|---|
| Label + autointerp score | Keep | Label written from train; detection and fuzzing accuracy on val | RQ1 faithfulness |
| Activation density histogram | Keep | Train and val overlaid | Train/val distribution check |
| Top activations with token highlighting | Keep | Train column next to val column | Sheng-Yu item 3 |
| Subsample intervals | Keep | Examples from activation deciles, train and val | Whether weak activations mean the same thing as strong ones |
| Correlated features | Keep | Concepts that co-activate across docs, plus decoder cosine similarity | Sheng-Yu item 4.2 (several directions on one concept) |
| Positive/negative logits | Drop for now | Projecting a layer-16 direction through the unembedding skips 16 layers, so the logits say little | – |
| Neuron alignment, correlated neurons | Drop | About MLP neurons, which we do not study | – |
| (new) Coverage card | Add | χ train, χ val, class (missing/under/over), share of activation by Dolma source | Oct 13 item 1 |
| (new) Doc view | Add | Click a doc: its top concepts with labels | Sheng-Yu item 4 |
| (new) Distribution tab | Add | log χ train vs log χ val scatter with the noise-floor band | Sheng-Yu item 5 |

Rejected: generating pages with SAEDashboard. It produces this layout but has no train/val side-by-side view, and its Olmo 3 support is unverified.

## Pilot checks (before the full run)
1. Hook output equals `hidden_states[17]`.
2. SAE reconstruction: fraction of variance explained, and active concepts per token, on pilot tokens.
3. bf16 vs fp32 LM reconstruction error (decision 12).
4. Tokenizer BOS behavior (decision 10).
5. Seconds per doc, to set N (decision 20).
