"""Build the Space data for the similarity and grouping tab (design.md G109). CPU, seconds, no pool data.

Usage: python s34_space_similarity.py
Reads only committed results files; recomputes nothing. Writes space/data/exp2_similarity.json. Names, ids and numbers only.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = HERE / "results"
SPACE = HERE.parent / "space" / "data"
ROW = re.compile(r"^\| (\d+) \| (\d+) \| ([0-9.]+) \| (.*) \| (.*) \|$")


def md_sections(path):
    """{section heading: [table rows as (a, b, cosine, name a, name b)]} from a results markdown file."""
    out, head = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            head = line[3:]
            out[head] = []
        elif head and (m := ROW.match(line)):
            out[head].append([int(m[1]), int(m[2]), float(m[3]), m[4], m[5]])
    return out


def cluster_members(path):
    """The two clusters' named members, from the first model's 'largest excess' tables (both clusters appear there)."""
    members = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (-?[0-9.]+) \| (.*) \|$", line)
        if m and m[1] not in members:
            members[m[1]] = {"size": int(m[2]), "named": [x.split(": ", 1) for x in m[6].split("<br>") if ": " in x]}
    return members


def main():
    sim = json.loads((R / "full_post_similarity_summary.json").read_text(encoding="utf-8"))
    clusters = json.loads((R / "full_post_clusters_summary.json").read_text(encoding="utf-8"))
    check = json.loads((R / "full_post_similarity_name_check.json").read_text(encoding="utf-8"))
    sections = md_sections(R / "full_post_similarity_summary.md")
    out = {"sources": ["results/full_post_similarity_summary.json", "results/full_post_similarity_summary.md", "results/full_post_clusters_summary.json",
                       "results/full_post_clusters_summary.md", "results/full_post_similarity_name_check.json"],
           "k": sim["k"], "window": sim["window"], "cosine_quantiles": sim["cosine_quantiles_10_50_90"], "sets": sim["sets"],
           "named_pairs": next(v for k, v in sections.items() if k.startswith("Nearest-neighbour pairs")),
           "under_over_pairs": {k.split(":")[0]: v for k, v in sections.items() if "under concepts whose nearest" in k},
           "name_check": {"method": check["method"], "counts": check["counts"]},
           "clusters": {k: clusters[k] for k in ("k_spectral", "components", "ari_seeds_vs_seed0", "eigenvalues_first_101", "no_mutual_neighbour", "no_mutual_neighbour_ids", "sets")},
           "cluster_members": cluster_members(R / "full_post_clusters_summary.md")}
    SPACE.mkdir(parents=True, exist_ok=True)
    (SPACE / "exp2_similarity.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("named pairs", len(out["named_pairs"]), "under-over", {k: len(v) for k, v in out["under_over_pairs"].items()}, "clusters", list(out["cluster_members"]),
          "bytes", (SPACE / "exp2_similarity.json").stat().st_size)


if __name__ == "__main__":
    main()
