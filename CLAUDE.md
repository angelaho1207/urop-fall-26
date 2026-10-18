# UROP: Competency Gaps in Training Data (Fall 2026)

Angela Ho, Torralba lab (MIT CSAIL). Supervisors: Kimia Hamidieh, Sheng-Yu (PhD students).

## Project goal
Can SAEs measure gaps between training data and model output with respect to detailed concepts?
Builds on Bohacek et al. 2026, "Uncovering Competency Gaps in LLMs and Their Benchmarks" (arXiv:2512.20638), Eq. 1-3.

Research questions (Sheng-Yu's plan):
1. Can SAEs discover concepts reliably from training data? Do they miss concepts? Are they faithful (does a direction fire on the same concept in train and held-out data)?
2. Why SAEs instead of an LLM tagging concepts? Hypothesis: SAE gives coverage, LLM verifies per-direction accuracy on a train/val split.
3. How to measure the data-vs-output gap while separating SAE train/test error from the concept gap we care about?

## Hard rules
- OLMo only. No Pythia, Gemma or other models.
- Work from Sheng-Yu's plan. Earlier experiments (Pythia, 9/19, 9/23, cg_coverage/) are not templates.
- Every design choice goes in the experiment's `design.md` decision table BEFORE code runs: choice, reason, alternatives rejected, source (config file, card, paper). These feed the slides and write-up, so never skip one.
- Never evaluate on data used to fit the thing being evaluated. State in design.md what each split was used for.
- Show qualitative results first (top documents per concept), metrics second.
- Angela must be able to explain every line of code and every number. Explain any command or code she pastes, line by line.
- Never invent facts about models, datasets or SAEs. Check the config file or model card and cite it.
- Do not touch the Google Slides deck until every experiment and task for the day is done.

## Verified facts (checked 2026-10-17)
- Model: `allenai/Olmo-3-1025-7B` (Base). Needs transformers >= 4.57.0.
- SAE: `decoderesearch/olmo-3-saes`, ids `olmo-3-1025-7b/btk-mat-layer-{4,16,28}-k-100`. Exp 1 uses layer 16.
  Matryoshka BatchTopK, k=100, d_in 4096, d_sae 65,536, nested prefixes 2,048 / 16,384 / 65,536.
  Saved as JumpReLU for inference (cfg.json "architecture": "jumprelu").
  Hook `model.layers.N` = output of decoder layer N = HF `hidden_states[N+1]`.
  Trained on 1B tokens of `chanind/pile-uncopyrighted-olmo-3-1024-abbrv-2B` (the Pile, not Dolma), context 1024, BOS prepended, special tokens excluded from training.
  Load: `SAE.from_pretrained("decoderesearch/olmo-3-saes", "<sae_id>")`.
- Training data of Olmo-3-1025-7B: stage 1 `allenai/dolma3_mix-6T-1025-7B` (5.93T tokens, 97.5% of all tokens), stage 2 `allenai/dolma3_dolmino_mix-100B-1025`, stage 3 `allenai/dolma3_longmino_mix-50B-1025`.
  Stage 1 token shares: common_crawl 76.07%, olmocr_science_pdfs 13.57%, stack_edu 6.89%, finemath-3plus 2.56%, rpj-proofpile-arxiv 0.86%, dolma1_7-wiki-en 0.04%.
  Some olmOCR docs are redacted as `[REMOVED]`; filter and count them.
  `allenai/dolma3_pool` is the pre-mix pool, not what the model trained on.
  Every doc in the stage 1 mix was seen by the model, so a split of it is held out from the SAE and from concept labels, not from the model.
- Post-trained 7B lines: `allenai/Olmo-3-7B-Think-SFT/-DPO/Think`, `allenai/Olmo-3-7B-Instruct-SFT/-DPO/Instruct`.

## Tools per task
- SAE activations: sbatch GPU jobs on ORCD (`mit_normal_gpu`).
- Concept labels: Anthropic API script (Message Batches), fixed model id, prompts and outputs saved. API key lives in `~/.anthropic_key` (chmod 600), never in the repo.
- Code, job submission, analysis: Claude Code in the VS Code tunnel job.
- Website: Hugging Face Space.

## Compute (MIT ORCD Engaging)
- `ssh angela_h@orcd-login.mit.edu`. Python env: `module load miniforge/25.11.0-0 && source ~/venvs/cg/bin/activate`.
- GPU partition `mit_normal_gpu` (L40S, H100, H200), CPU partition `mit_normal`. Check limits with `sinfo -p <partition>`.
- Heavy work goes through sbatch, never the login node. Logs in `logs/`.

## Repo rules
- Repo is temporarily public. Never commit tensors, model weights, dataset text dumps, tokens or keys.
- Each experiment gets a folder `expN_<name>/` with `design.md`, code, and `results/` (small JSON/TXT only).

## Writing style
Concise, no filler. Banned words: genuinely, real, exactly, precisely, worth. No negative parallelisms or three-beat rhythms.
