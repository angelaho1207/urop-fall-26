"""Noise rerun of the classes and extreme lists, CG App. B.3 (design.md G72). CPU only, no API.

Usage: python s21_named_noise.py
100 reruns, each dropping a random 20% of docs per set (all train docs; each model's G16 matched docs). Each recomputes chi, r,
the e^-5 cut, classes and extreme lists. Reads the acts, DATA/full_post/distribution.parquet and named/concepts.json.
Writes results/full_post_named_noise_summary.json (ids and numbers only).
"""
import json
import time

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import numpy as np
import pandas as pd

import diag_common as dc
from s03_distribution import choose
from s05_coverage import chi  # Exp 1 Eq. 2
from s12_moved_windows import D_SAE, SETS, firing_counts
from s19_named_select import CLASSES, classify, extremes

N_RERUNS, DROP = 100, 0.2  # G72
RUN = "full_post"


def dropped(means, totals, nnz, seed):
    """chi and firing docs lost for one rerun: subtract the dropped docs. A concept with no doc left gets a sum of exactly 0."""
    n = means.shape[0]
    drop = np.random.default_rng(seed).choice(n, size=int(round(DROP * n)), replace=False)
    sub = means[drop]
    lost = np.bincount(sub.indices, minlength=D_SAE)
    sums = totals - np.asarray(sub.sum(0)).ravel()
    sums[nnz - lost == 0] = 0.0
    return chi(sums), lost


def main():
    t0 = time.time()
    table = pd.read_parquet(settings.DATA / RUN / "distribution.parquet")
    pub = json.loads((settings.RESULTS / f"{RUN}_distribution_summary.json").read_text())
    paths, all_lengths = dc.set_lengths()
    chosen, counts = choose(all_lengths)
    if counts != pub["docs_per_scope"]:
        raise SystemExit(f"G39: doc counts {counts} differ from published {pub['docs_per_scope']}")

    # The no-drop chi must equal the published table (G39)
    docs = pd.read_parquet(settings.EXP1_RUN / "docs.parquet", columns=["doc_id", "subset"])
    train_paths = sorted((settings.EXP1_RUN / "acts").glob("part_?????.npz"))
    train, _, _ = dc.read_means(train_paths, docs.loc[docs["subset"] != "V", "doc_id"].to_numpy())
    chi_train, fire_train = table["chi_train"].to_numpy(), table["n_fire_train"].to_numpy()
    means = {"train": train}
    report = {"train_docs": int(train.shape[0]), "train_nnz_equals_n_fire_train": bool((train.getnnz(0) == fire_train).all())}
    rel = np.abs(dc.set_chi(train) - chi_train)[chi_train > 0] / chi_train[chi_train > 0]
    report["check_max_rel_chi_diff"] = {"train": float(rel.max())}
    if rel.max() >= 1e-6:
        raise SystemExit(f"G72: train chi differs from the published table by {rel.max()}")
    for g in SETS:
        means[g], _, _ = dc.read_means(paths[g], chosen[g]["doc"])
        report["check_max_rel_chi_diff"][g] = dc.check_chi(g, means[g], table)
    report["matched_docs"] = {g: int(means[g].shape[0]) for g in SETS}
    totals = {k: np.asarray(m.sum(0)).ravel() for k, m in means.items()}
    nnz = {k: m.getnnz(0) for k, m in means.items()}
    fire = {g: firing_counts(g) for g in SETS}
    print("read", json.dumps(report), round(time.time() - t0), flush=True)

    base = {}
    for g in SETS:
        r, cls, order = classify(chi_train, table[f"chi_{g}"].to_numpy())
        lists = extremes(order, fire_train, fire[g])
        base[g] = {"r": r, "cls": cls, "lists": lists, "stay_class": np.zeros(D_SAE, dtype=np.int32), "ranked": np.zeros(D_SAE, dtype=np.int32),
                   "in_list": {k: np.zeros(D_SAE, dtype=np.int32) for k in lists}, "overlap": {k: [] for k in lists}, "rs": np.full((N_RERUNS, D_SAE), np.nan, dtype=np.float32)}

    for b in range(N_RERUNS):
        chi_t, lost_t = dropped(means["train"], totals["train"], nnz["train"], [0, 72, b, 0])
        for j, g in enumerate(SETS):
            chi_g, lost_g = dropped(means[g], totals[g], nnz[g], [0, 72, b, j + 1])
            r, cls, order = classify(chi_t, chi_g)
            lists = extremes(order, fire_train - lost_t, fire[g] - lost_g)
            s = base[g]
            s["rs"][b] = np.where(np.isfinite(r), r, np.nan)
            s["ranked"] += cls != ""
            s["stay_class"] += (cls == s["cls"]) & (s["cls"] != "")
            for k, cs in lists.items():
                s["in_list"][k][cs] += 1
                s["overlap"][k].append(len(np.intersect1d(cs, s["lists"][k])) / len(s["lists"][k]))
        if (b + 1) % 10 == 0:
            print("rerun", b + 1, round(time.time() - t0), flush=True)

    rows = json.loads((settings.DATA / RUN / "named" / "concepts.json").read_text())["rows"]
    out = {"reruns": N_RERUNS, "drop": DROP, **report, "models": {}}
    for g in SETS:
        s = base[g]
        with np.errstate(invalid="ignore"):
            n_finite = np.isfinite(s["rs"]).sum(0)
            with_two = n_finite >= 2
            spread = np.full(D_SAE, np.nan)
            spread[with_two] = np.nanstd(s["rs"][:, with_two], axis=0)
        per_class = {}
        for c_name in CLASSES:
            mine = s["cls"] == c_name
            per_class[c_name] = {"concepts": int(mine.sum()), "mean_share_stays": round(float(s["stay_class"][mine].mean() / N_RERUNS), 4),
                                 "share_of_concepts_always_stays": round(float((s["stay_class"][mine] == N_RERUNS).mean()), 4),
                                 "median_r_sd": round(float(np.nanmedian(spread[mine])), 4), "p90_r_sd": round(float(np.nanpercentile(spread[mine], 90)), 4)}
        per_list = {}
        for k, cs in s["lists"].items():
            per_list[f"{k[0]}_{k[1]}"] = {"mean_overlap_with_baseline": round(float(np.mean(s["overlap"][k])), 4), "median_share_stays": round(float(np.median(s["in_list"][k][cs]) / N_RERUNS), 4),
                                          "lowest_share_stays": round(float(s["in_list"][k][cs].min() / N_RERUNS), 4), "median_r_sd": round(float(np.nanmedian(spread[cs])), 4)}
        concepts = []
        for x in [x for x in rows if x["model"] == g]:
            c = x["concept"]
            values = s["rs"][:, c][np.isfinite(s["rs"][:, c])]
            key = None if x["list"] == "random" else (x["list"], x["class"])
            concepts.append({"concept": c, "list": x["list"], "class": x["class"], "r": x["r"], "r_sd": None if not with_two[c] else round(float(spread[c]), 4),
                             "r_p2_5": round(float(np.percentile(values, 2.5)), 4) if len(values) else None, "r_p97_5": round(float(np.percentile(values, 97.5)), 4) if len(values) else None,
                             "reruns_r_finite": int(n_finite[c]), "share_stays_in_class": round(float(s["stay_class"][c] / N_RERUNS), 3),
                             "share_stays_in_list": None if key is None else round(float(s["in_list"][key][c] / N_RERUNS), 3)})
        out["models"][g] = {"classes": per_class, "extreme_lists": per_list, "selected_concepts": concepts}
    out["seconds"] = round(time.time() - t0)
    (settings.RESULTS / f"{RUN}_named_noise_summary.json").write_text(json.dumps(out))
    print(json.dumps({k: v for k, v in out.items() if k != "models"}, indent=1), flush=True)
    print(json.dumps({g: {k: v for k, v in m.items() if k != "selected_concepts"} for g, m in out["models"].items()}, indent=1))


if __name__ == "__main__":
    main()
