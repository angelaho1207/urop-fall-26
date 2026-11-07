"""Build the Space data for the coverage-list section (design.md G100). CPU, seconds, no pool data.

Usage: python s31_space_coverage.py
Reads only committed results files; recomputes nothing. Writes space/data/exp2_coverage.json. Names, ids and numbers only,
and no cost fields (G83).
"""
import json
from pathlib import Path

from s28_space_missing import cost_keys

HERE = Path(__file__).resolve().parent
R = HERE / "results"
SPACE = HERE.parent / "space" / "data"
KEEP_SELECTION = ["docs", "zero_counts", "zero_fire_outside_matched", "mean_share_staying", "jaccard_with_dolma_train", "reruns", "drop", "list_size",
                  "new_dolma_names", "new_rollout_names", "reused_names", "new_names_from_under_40_docs"]
KEEP_ROW = ["set", "list", "rank", "concept", "chi", "chi_train", "n_fire_train", "n_fire_rollout_all", "stays", "fires_outside_matched", "name", "name_source"]


def main():
    summary = json.loads((R / "full_post_coverage_summary.json").read_text(encoding="utf-8"))
    selection = json.loads((R / "full_post_coverage_selection_summary.json").read_text(encoding="utf-8"))
    names = json.loads((R / "full_post_coverage_names.json").read_text(encoding="utf-8"))
    if summary["stopped"] is not None or summary["entries_without_name"]:
        raise SystemExit("G100: expected a finished run with every entry named")
    out = {"run": "full_post", "sources": [f"results/full_post_coverage_{k}.json" for k in ("summary", "selection_summary", "names")],
           **{k: selection[k] for k in KEEP_SELECTION}, "name_statuses": summary["name_statuses"],
           "rows": [{k: x[k] for k in KEEP_ROW if k in x} for x in names]}
    dollars = cost_keys({k: v for k, v in out.items() if k != "rows"}) + cost_keys(out["rows"][:1])
    if dollars:
        raise SystemExit(f"G83: cost fields in the page data: {dollars}")
    SPACE.mkdir(parents=True, exist_ok=True)
    (SPACE / "exp2_coverage.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("rows", len(out["rows"]), "bytes", (SPACE / "exp2_coverage.json").stat().st_size)


if __name__ == "__main__":
    main()
