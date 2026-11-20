"""Build the Space data for the embedding similarity section (design.md G121). CPU, seconds, no pool data.

Usage: python s40_space_embed.py
Reads only committed results files; recomputes nothing. Writes space/data/exp2_embed.json. Names, ids and numbers only.
"""
import json

from s34_space_similarity import R, SPACE, cluster_members, md_sections
from s36_space_tree import tree_data

SETS = ["V", "stage1", "main", "sft", "dpo", "instruct"]


def load(name):
    return json.loads((R / name).read_text(encoding="utf-8"))


def group_shares(tree, g):
    """Under and over share of tree group g in every set."""
    return {s: {side: tree["sets"][s]["groups"][str(g)][side]["share"] for side in ("under", "over")} for s in SETS}


def main():
    dec, emb = load("full_post_similarity_summary.json"), load("full_post_embed_similarity_summary.json")
    dec_cl, emb_cl = load("full_post_clusters_summary.json"), load("full_post_embed_clusters_summary.json")
    tree_json = load("full_post_embed_tree_summary.json")
    tree = tree_data("full_post_embed")
    halves = {g: {"size": tree_json["groups"][g]["size"], "shares": group_shares(tree_json, g)} for g in ("1", "2")}  # depth 1 = the K = 2 split
    spotlight = {}
    for side in ("over", "under"):  # G121 rule: highest share among the pretrained model's 10 largest-excess groups
        best = max(tree["top_groups"]["main"][side], key=lambda x: x["share"])
        spotlight[side] = {**best, "shares": group_shares(tree_json, best["group"])}
    check = load("full_post_embed_name_check.json")
    win, vec, overlap = load("full_post_embed_windows_summary.json"), load("full_post_embed_vectors_summary.json"), load("full_post_embed_checks.json")
    sections = md_sections(R / "full_post_embed_similarity_summary.md")
    out = {"sources": ["results/full_post_embed_*", "results/full_post_similarity_summary.json", "results/full_post_clusters_summary.json"],
           "sets": {s: {"decoder": dec["sets"][s], "embedding": emb["sets"][s]} for s in SETS},
           "same_class": {s: {"decoder": dec_cl["sets"][s], "embedding": emb_cl["sets"][s]} for s in SETS},
           "halves": halves, "half_members": cluster_members(R / "full_post_embed_clusters_summary.md"),
           "ari_seeds_vs_seed0": emb_cl["ari_seeds_vs_seed0"], "no_mutual_neighbour": emb_cl["no_mutual_neighbour"],
           "spotlight": spotlight, "tree": tree,
           "name_check": {"method": check["method"], "counts": check["counts"]},
           "shared_docs": {k: overlap[k] for k in ("embedding_neighbours", "decoder_neighbours", "random_frequency_matched", "embedding_neighbours_also_decoder_neighbours")},
           "run": {**{k: win[k] for k in ("docs", "concepts", "pairs", "distinct_windows", "concepts_under_40", "concepts_under_5", "concepts_with_1")},
                   **{k: vec[k] for k in ("model", "revision", "tokens_10_50_90_max", "truncated")}},
           "cosine_quantiles": {"embedding": emb["cosine_quantiles_10_50_90"], "decoder": dec["cosine_quantiles_10_50_90"]},
           "named_pairs": next(v for k, v in sections.items() if k.startswith("Nearest-neighbour pairs"))}
    (SPACE / "exp2_embed.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("spotlight", {k: (v["group"], v["share"]) for k, v in spotlight.items()}, "halves", {g: h["size"] for g, h in halves.items()},
          "named pairs", len(out["named_pairs"]), "bytes", (SPACE / "exp2_embed.json").stat().st_size)


if __name__ == "__main__":
    main()
