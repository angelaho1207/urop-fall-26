"""Constants for Exp 1. Each one names the design.md row it comes from (T = technical, P = pilot)."""
import os
from pathlib import Path

# P8: Hugging Face downloads go to pool, not home. Must be set before transformers or
# huggingface_hub is imported, so every script imports config first.
HF_CACHE = Path("/orcd/pool/005/angela_h/hf_cache")
os.environ.setdefault("HF_HOME", str(HF_CACHE))

# Row 1, T9
MODEL_ID = "allenai/Olmo-3-1025-7B"
MODEL_REVISION = "a81bae42db3975be1671e27b9c9a56da1a9f980f"

# Row 2, T9
SAE_REPO = "decoderesearch/olmo-3-saes"
SAE_ID = "olmo-3-1025-7b/btk-mat-layer-16-k-100"
SAE_REVISION = "ad1f790dd36d44b5b77b1d08ace6a6f48d121649"

# Row 13: the SAE reads the output of decoder layer 16, which is hidden_states[17]
LAYER = 16
HIDDEN_STATES_INDEX = LAYER + 1

# Row 3, T9
DATASET_ID = "allenai/dolma3_mix-6T-1025-7B"
DATASET_REVISION = "2ca900fbe14e86c5c83d064d9f0882f1c0b8c05b"

# Row 4: token share per source, from the dataset card's "Mix Compositions" table
TOKEN_SHARE = {
    "common_crawl": 0.7607,
    "olmocr_science_pdfs": 0.1357,
    "stack_edu": 0.0689,
    "finemath-3plus": 0.0256,
    "rpj-proofpile-arxiv": 0.0086,
    "dolma1_7-wiki-en": 0.0004,
}
REDACTED_SOURCE = "olmocr_science_pdfs"  # row 8: the [REMOVED] filter applies to this source only
REDACTION_MARK = "[REMOVED]"

# Rows 5, 6
SEED = 0
VAL_FRACTION = 0.2  # row 6: 20% of shards go to V
SUBSET_FRACTION_OF_TRAIN = 0.25  # T1 and T2 are each 25% of train = 20% of all, the size of V

# Row 9
CONTEXT = 1024

# Row 22, P7
PILE_ID = "monology/pile-uncopyrighted"
PILE_REVISION = "3be90335b66f24456a5d6659d9c8d208c0357119"
PILE_FILE = "train/02.jsonl.zst"
PILE_HEAD_DOCS = 10_000
PILE_N_DOCS = 50

# P2, P3, P13
PILOT_N_DOCS = 400
PILOT_DOCS_PER_SHARD = 10
PILOT_PRECISION_DOCS = 20
PILOT_HOOK_CHECK_DOCS = 5

# Full run, decided from the pilot on 2026-10-18
FULL_N_DOCS = 50_000  # row 20
FULL_DOCS_PER_SHARD = 50  # row 5
MODEL_DTYPE = "bfloat16"  # row 12: bf16 weights, no autocast
EXCLUDE_POSITION_0 = False  # row 10: position 0 stays in averages and top examples

# P15: candidate k (firing docs needed per subset) until row 17 fixes it
CANDIDATE_K = (20, 40)
CANDIDATE_N = (10_000, 20_000, 50_000, 100_000)
PREFIX_WIDTH = 2048  # row 16: first Matryoshka prefix

# T1, P16
DATA = Path("/orcd/pool/005/angela_h/exp1")
SCRATCH = Path("/orcd/scratch/orcd/006/angela_h/exp1")
RESULTS = Path(__file__).resolve().parent / "results"


def source_of(folder: str) -> str:
    """Map a shard folder name such as 'common_crawl-health-0018' to its source."""
    for source in TOKEN_SHARE:
        if folder.startswith(source):
            return source
    raise ValueError(f"unknown source for folder {folder}")
