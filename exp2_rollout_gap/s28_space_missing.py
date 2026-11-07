"""Build the Space data for the missing-concepts section (design.md G94). CPU, seconds, no pool data.

Usage: python s28_space_missing.py
Reads only committed results files; recomputes nothing. Writes space/data/exp2_missing.json (tables and counts) and
space/data/exp2_missing_lists.json (all list entries with names). Names, ids and numbers only, and no cost fields (G83).
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = HERE / "results"
SPACE = HERE.parent / "space" / "data"
COST_KEY = re.compile(r"usd|spent|price|limit_|usage", re.I)
KEEP_SUMMARY = ["names_returned", "names_planned", "name_statuses", "entries_without_name", "categories", "concepts_themed", "kappa_opus_vs_sonnet", "agreement", "themes", "by_model", "garbled"]
KEEP_SELECTION = ["entries", "distinct_concepts", "distinct_in_list_a", "distinct_in_list_b", "new_dolma_names", "new_rollout_names", "reused_names", "reused_by_source", "new_names_from_under_40_docs", "distinct_random_concepts"]
KEEP_ROW = ["concept", "model", "direction", "list", "r", "chi_train", "chi_rollout", "chi_V", "n_fire_train", "n_fire_rollout", "v_agrees", "name", "name_source"]


def read(name):
    return json.loads((R / f"full_post_missing_{name}.json").read_text(encoding="utf-8"))


def cost_keys(value, path=""):
    if isinstance(value, dict):
        return [f"{path}/{k}" for k in value if COST_KEY.search(k)] + [hit for k, v in value.items() for hit in cost_keys(v, f"{path}/{k}")]
    if isinstance(value, list):
        return [hit for v in value for hit in cost_keys(v, path)]
    return []


def main():
    summary, selection, names = read("summary"), read("selection_summary"), read("names")
    if summary["stopped"] is not None or len(names) != 1800:
        raise SystemExit("G94: expected a finished run with 1,800 list entries")
    out = {"run": "full_post", "sources": [f"results/full_post_missing_{k}.json" for k in ("summary", "selection_summary", "names")],
           **{k: summary[k] for k in KEEP_SUMMARY}, "selection": {k: selection[k] for k in KEEP_SELECTION}}
    rows = [{k: x[k] for k in KEEP_ROW} for x in names]
    dollars = cost_keys(out) + cost_keys(rows[:1])
    if dollars:
        raise SystemExit(f"G83: cost fields in the page data: {dollars}")
    SPACE.mkdir(parents=True, exist_ok=True)
    (SPACE / "exp2_missing.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    (SPACE / "exp2_missing_lists.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print("rows", len(rows), "bytes", (SPACE / "exp2_missing.json").stat().st_size, (SPACE / "exp2_missing_lists.json").stat().st_size)


if __name__ == "__main__":
    main()
