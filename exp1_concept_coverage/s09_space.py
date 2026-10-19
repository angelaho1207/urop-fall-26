"""Data files for the Hugging Face Space (rows W1-W7). CPU only, no API.

Usage: python s09_space.py
Writes ../space/data/ (gitignored, T7): overview.json (W2), noise.json (W3), sample.json (W6) and
concepts/<id>.json (W4) for the 240 F-sample concepts. Names and quiz scores are added when the F run's files exist.
"""
import json
import shutil

import config
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from s07_names import pieces_of

SPACE = config.RESULTS.parent.parent / "space"
DATA_OUT = SPACE / "data"
FAITH = config.DATA / "full" / "labels" / "faith"
N_DOLMA_WEB, N_PILE_WEB = 30_418, 11_761  # R8: Dolma train common_crawl docs, Pile-CC docs


def r4(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 4)


def windows(run, c, subset):
    """W4, W5: the 40 naming windows, highest activation first, as decoded pieces and activations."""
    ex = json.loads((config.DATA / run / "examples_F" / f"{c}.json").read_text())
    out = [{"pieces": pieces_of(w), "acts": [round(a, 3) for a in w["acts"]], "max": round(w["max"], 3),
            "group": w["group"], "doc": w["doc_id"]} for w in ex["naming"][subset]]
    return sorted(out, key=lambda w: -w["max"])


def main():
    web = pd.read_parquet(config.DATA / "full" / "coverage_vs_pile_web.parquet")
    both = web["log_ratio_web"].notna()
    low, high = np.quantile(web.loc[both, "log_ratio_web"], [0.1, 0.9])
    share = (web["n_fire_train_web"] / N_DOLMA_WEB + web["n_fire_pile_web"] / N_PILE_WEB) / 2
    sample = pd.read_parquet(config.DATA / "full" / "faith_sample.parquet")
    in_sample = set(sample["concept"])

    names = json.loads((FAITH / "names.json").read_text()) if (FAITH / "names.json").exists() else {}
    analysis_path = config.RESULTS / "faith_analysis_summary.json"
    scores = ({int(r["concept"]): r for r in json.loads(analysis_path.read_text())["scores"]}
              if analysis_path.exists() else {})

    if DATA_OUT.exists():
        shutil.rmtree(DATA_OUT)
    (DATA_OUT / "concepts").mkdir(parents=True)

    b = web[both]
    overview = {"id": b["concept"].tolist(), "x": [round(v, 6) for v in share[both]],
                "y": [round(v, 4) for v in b["log_ratio_web"]], "cls": b["class_web"].tolist(),
                "sampled": [int(c in in_sample) for c in b["concept"]],
                "names": {str(c): {"pile": names.get(str(c), {}).get("pile"), "dolma": names.get(str(c), {}).get("dolma")}
                          for c in in_sample if str(c) in names},  # W8
                "low": round(float(low), 4), "high": round(float(high), 4),
                "class_counts": web["class_web"].value_counts().to_dict(),
                "n_docs": {"dolma_web": N_DOLMA_WEB, "pile_cc": N_PILE_WEB}}
    (DATA_OUT / "overview.json").write_text(json.dumps(overview))

    h = web[web["log_ratio_web_half1"].notna() & web["log_ratio_web_half2"].notna()]
    r8 = json.loads((config.RESULTS / "full_vs_pile_web_only.json").read_text())["noise_floor_web_half1_vs_half2"]
    same = r8["same_class_share_eligible"]  # R8's definition: concepts eligible for comparison in both halves
    noise = {"id": h["concept"].tolist(), "h1": [round(v, 4) for v in h["log_ratio_web_half1"]],
             "h2": [round(v, 4) for v in h["log_ratio_web_half2"]], "cls": h["class_web"].tolist(),
             "spearman": round(float(spearmanr(h["log_ratio_web_half1"], h["log_ratio_web_half2"])[0]), 4),
             "same_class_share": round(float(same), 4)}
    (DATA_OUT / "noise.json").write_text(json.dumps(noise))

    rows = []
    for c, cls in zip(sample["concept"], sample["class_web"]):
        c = int(c)
        w = web.loc[c]
        nm, sc = names.get(str(c), {}), scores.get(c, {})
        row = {"id": c, "cls": cls, "log_ratio": r4(w["log_ratio_web"]),
               "share_dolma": round(w["n_fire_train_web"] / N_DOLMA_WEB, 5),
               "share_pile": round(w["n_fire_pile_web"] / N_PILE_WEB, 5),
               "name_pile": nm.get("pile"), "name_dolma": nm.get("dolma"),
               "quiz_pile": r4(sc.get("pile")), "quiz_dolma": r4(sc.get("dolma"))}
        rows.append(row)
        page = {**row, "dolma": windows("full", c, "T1"), "pile": windows("pile", c, "PileCC")}
        (DATA_OUT / "concepts" / f"{c}.json").write_text(json.dumps(page, ensure_ascii=False))
    (DATA_OUT / "sample.json").write_text(json.dumps(rows, ensure_ascii=False))

    # P4: token-type patterns, with up to 3 named F-sample examples per type that is more common in over or under
    pat_path = config.RESULTS / "patterns_token_types.json"
    if pat_path.exists():
        pat = json.loads(pat_path.read_text())
        tt = pd.read_parquet(config.DATA / "full" / "token_types.parquet").set_index("concept")
        examples = []
        for cls in ("over", "under"):
            for ty, (d, lo, hi) in pat["dominant_diff_vs_middle"][cls].items():
                if lo > 0 and d >= 0.01:
                    ids = [int(c) for c in tt.index[(tt["dominant"] == ty) & (tt["class_web"] == cls)] if str(c) in names][:3]
                    examples.append({"cls": cls, "type": ty, "diff": d,
                                     "concepts": [{"id": c, "name": names[str(c)]["dolma"]} for c in ids]})
        (DATA_OUT / "patterns.json").write_text(json.dumps(
            {"share": pat["dominant_share"], "diff": pat["dominant_diff_vs_middle"], "examples": examples}, ensure_ascii=False))

    # Q6: topic categories of the 240 named concepts (plan B)
    top_path = config.RESULTS / "patterns_topics.json"
    if top_path.exists():
        top = json.loads(top_path.read_text())
        asg = pd.read_parquet(config.DATA / "full" / "labels" / "topics" / "assignments.parquet").set_index("concept")["opus"]
        (DATA_OUT / "topics.json").write_text(json.dumps(
            {"share": top["share"], "kappa": top["kappa_opus_vs_sonnet"], "agreement": top["agreement"],
             "categories": top["categories"],
             "concepts": {str(c): (asg.get(c) if isinstance(asg.get(c), str) else None) for c in sample["concept"]}},
            ensure_ascii=False))
    size = sum(p.stat().st_size for p in DATA_OUT.rglob("*.json")) / 1e6
    print(f"overview {len(overview['id'])} concepts (cut lines {low:.3f}, {high:.3f}); noise {len(noise['id'])} "
          f"(Spearman {noise['spearman']}, same class {noise['same_class_share']}); pages {len(rows)}; "
          f"names {sum(r['name_dolma'] is not None for r in rows)}; {size:.1f} MB")


if __name__ == "__main__":
    main()
