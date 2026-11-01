"""Constants for Exp 2. Each one names the design.md row it comes from (G = decision, X = technical).

Exp 1's helpers import a module called `config`, so this file is named `settings` and puts Exp 1's folder on
the path: `import config` then finds Exp 1's config (model, SAE, context, data paths), and Exp 1 code runs
unchanged. Every Exp 2 script imports settings first, because Exp 1's config sets HF_HOME.
"""
import sys
from pathlib import Path

EXP1 = Path(__file__).resolve().parent.parent / "exp1_concept_coverage"
sys.path.insert(0, str(EXP1))
import config  # noqa: E402  (Exp 1's config)

# G4, G30: generators as (repo id, revision). A branch is resolved to a commit hash at run time and logged
GENERATORS = {"stage1": (config.MODEL_ID, "stage1-step1413814"), "main": (config.MODEL_ID, config.MODEL_REVISION),
              "sft": ("allenai/Olmo-3-7B-Instruct-SFT", "main"), "dpo": ("allenai/Olmo-3-7B-Instruct-DPO", "main"),
              "instruct": ("allenai/Olmo-3-7B-Instruct", "main")}

# G1-G3
EOS_ID = 100257  # <|endoftext|>, tokenizer_config.json
IM_END_ID = 100265  # <|im_end|>
MAX_NEW = config.CONTEXT  # 1,024 new tokens at most
# G3, G31: ids that end a rollout. The post-trained generation_config.json files list both
STOP_IDS = {"stage1": [EOS_ID], "main": [EOS_ID], "sft": [IM_END_ID, EOS_ID], "dpo": [IM_END_ID, EOS_ID],
            "instruct": [IM_END_ID, EOS_ID]}

# G34: ids >= 100256 are special tokens; in these runs they are removed before decoding
SPECIAL_MIN = 100256
DROP_SPECIAL = {"pilot_post", "full_post", "full_fimcheck"}

# G5, G6, G33: full runs use seed root 0, pilots 1
N_ROLLOUTS = 10_000
SEED_ROOT = {"pilot": 1, "full": 0, "pilot_post": 1, "full_post": 0, "full_fimcheck": 0}

# G12
WINDOWS = [(0, 256), (256, 512), (512, 768), (768, 1024)]

# G13
MIN_FIRING_DOCS = 40  # display: hollow marker below this, per plotted set
MIN_TRAIN_FIRING_DOCS = 160  # concepts in the slope b, chosen on Dolma train only

# G11
BOOTSTRAP = 1000
N_BINS = 20

# G14
DEGEN_NGRAM = 4
DEGEN_MIN_TOKENS = 64
DEGEN_TAIL = 256  # score the last 256 tokens
DEGEN_THRESHOLD = 0.6  # set on the pilot, design.md G14

# X1
PART_SIZE = 500
DATA = Path("/orcd/pool/005/angela_h/exp2")
RESULTS = Path(__file__).resolve().parent / "results"
EXP1_RUN = config.DATA / "full"  # Exp 1 full run: docs.parquet, coverage.parquet, acts/


def encoder_ids(run, ids):
    """G34: the rollout ids that are decoded and encoded. In DROP_SPECIAL runs, ids >= 100256 are removed."""
    ids = list(ids)
    return [i for i in ids if i < SPECIAL_MIN] if run in DROP_SPECIAL else ids
