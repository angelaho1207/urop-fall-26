"""Build the Space data for the concept tree section (design.md G113). CPU, seconds, no pool data.

Usage: python s36_space_tree.py
Reads only committed results files; recomputes nothing. Writes space/data/exp2_tree.json. Names, ids and numbers only.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = HERE / "results"
SPACE = HERE.parent / "space" / "data"
# | group | depth | path | size | ranked | count | share | null 97.5% | named members |
ROW = re.compile(r"^\| (\d+) \| (\d+) \| ([0-9 →]+) \| (\d+) \| (\d+) \| (\d+) \| ([0-9.]+) \| ([0-9.]+) \| (.*) \|$")


def top_groups(path):
    """{model: {side: [group rows]}} from the '10 enriched groups with the largest excess' tables."""
    out, key = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if m := re.match(r"^### (\w+): 10 enriched groups with the largest excess of (under|over) concepts", line):
            key = (m[1], m[2])
            out.setdefault(m[1], {})[m[2]] = []
        elif key and (m := ROW.match(line)):
            out[key[0]][key[1]].append({"group": int(m[1]), "depth": int(m[2]), "path": m[3], "size": int(m[4]), "ranked": int(m[5]), "count": int(m[6]),
                                        "share": float(m[7]), "null_p975": float(m[8]), "named": [x.split(": ", 1) for x in m[9].split("<br>") if ": " in x]})
    return out


def tree_data(prefix):
    """The tree section's data from results/{prefix}_tree_summary.{json,md} (prefix full_post or full_post_embed, G118)."""
    s = json.loads((R / f"{prefix}_tree_summary.json").read_text(encoding="utf-8"))
    exceeding = lambda st, side, d: {g for g, v in s["sets"][st]["groups"].items() if v["depth"] == d and v[side]["exceeds"]}  # noqa: E731
    overlap = {st: [{"depth": d, **{f"{side}_{k}": n for side in ("under", "over") for k, n in
                                    (("model", len(exceeding(st, side, d))), ("also_V", len(exceeding(st, side, d) & exceeding("V", side, d))))}}
                    for d in range(1, s["depth"] + 1)] for st in s["sets"] if st != "V"}
    return {"sources": [f"results/{prefix}_tree_summary.json", f"results/{prefix}_tree_summary.md"], "depth": s["depth"], "min_split": s["min_split"],
           "groups_per_depth": s["groups_per_depth"], "leaf_sizes_10_50_90_max": s["leaf_sizes_10_50_90_max"],
           "splits": {k: sum(v["split"] == k for v in s["groups"].values()) for k in ("spectral", "pieces")}, "groups_total": len(s["groups"]),
           "per_depth": {st: v["per_depth"] for st, v in s["sets"].items()}, "overlap_with_V": overlap, "top_groups": top_groups(R / f"{prefix}_tree_summary.md")}


def main():
    out = tree_data("full_post")
    SPACE.mkdir(parents=True, exist_ok=True)
    (SPACE / "exp2_tree.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("top groups", {m: {k: len(v) for k, v in x.items()} for m, x in out["top_groups"].items()}, "splits", out["splits"], "bytes", (SPACE / "exp2_tree.json").stat().st_size)


if __name__ == "__main__":
    main()
