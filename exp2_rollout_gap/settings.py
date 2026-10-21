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

# G4: generators. The branch is resolved to a commit hash at run time and logged
GENERATORS = {"stage1": "stage1-step1413814", "main": config.MODEL_REVISION}

# G1-G3
EOS_ID = 100257  # <|endoftext|>, tokenizer_config.json
MAX_NEW = config.CONTEXT  # 1,024 new tokens at most

# G5, G6
N_ROLLOUTS = 10_000
SEED_ROOT = {"pilot": 1, "full": 0}

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
