"""List every shard of the stage 1 mix with its source, folder and compressed size (rows 4, 5).

Saves DATA/shards.parquet (one row per shard) and results/shards_summary.json (per source).
"""
import json

import config  # first: sets HF_HOME
import pandas as pd
from huggingface_hub import HfApi

rows = []
tree = HfApi().list_repo_tree(
    config.DATASET_ID, repo_type="dataset", revision=config.DATASET_REVISION, path_in_repo="data", recursive=True
)
for entry in tree:
    # The recursive listing returns folders too; shards are the files ending in .jsonl.zst
    if not entry.path.endswith(".jsonl.zst"):
        continue
    folder = entry.path.split("/")[1]  # data/<folder>/<file>
    rows.append({"path": entry.path, "folder": folder, "source": config.source_of(folder), "bytes": entry.size})

shards = pd.DataFrame(rows)
config.DATA.mkdir(parents=True, exist_ok=True)
shards.to_parquet(config.DATA / "shards.parquet", index=False)

summary = {
    "dataset": config.DATASET_ID,
    "revision": config.DATASET_REVISION,
    "n_shards": len(shards),
    "by_source": {
        source: {
            "shards": int(len(group)),
            "share_of_shards": round(len(group) / len(shards), 4),
            "gb": round(group["bytes"].sum() / 1e9, 1),
            "min_mb": round(group["bytes"].min() / 1e6, 3),
            "median_mb": round(group["bytes"].median() / 1e6, 2),
            "max_mb": round(group["bytes"].max() / 1e6, 1),
            "folders": int(group["folder"].nunique()),
        }
        for source, group in shards.groupby("source")
    },
}
config.RESULTS.mkdir(exist_ok=True)
(config.RESULTS / "shards_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
