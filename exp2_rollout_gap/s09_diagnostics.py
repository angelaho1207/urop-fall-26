"""Diagnostics of full_post (design.md G39-G42, G44, G45). CPU only.

Usage: python s09_diagnostics.py
Reads DATA/full_post/distribution.parquet and results/full_post_distribution_summary.json (s03), the full_post acts
and rollouts, and Exp 1's coverage, docs, acts and concept names.
Writes results/full_post_diagnostics.json and DATA/full_post/diagnostics_gainers.md (text, pool only: G20).
"""
import json

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import diag_common as dc
from s03_distribution import D_SAE, choose, log_y, slope
from s04_examples import NAMES, top_windows, window_text
from s03_pilot import tokenize  # Exp 1
from s05_coverage import chi

TOP_K = [10, 100, 1000]
N_GAINERS, N_EXAMPLES = 30, 10
SHORT = 30  # tokens, Exp 1 row 11
SETS_DETAIL = ["V"] + dc.SHOWN
MASKS = {"all": lambda b: b >= 0, "without_rarest_3_bins": lambda b: b >= 3,
         "without_top_bin": lambda b: b <= 18, "middle_16_bins": lambda b: (b >= 3) & (b <= 18)}  # G44


def r4(v):
    return round(float(v), 4)


def shape_vs_shuffle(x, y):
    """G40: paired vs unpaired distance between ln chi_set (y) and ln chi_train (x) over the slope concepts."""
    d_pair = float(np.mean((y - x) ** 2))
    d_marg = float(np.mean((np.sort(y) - np.sort(x)) ** 2))
    loc = float((y.mean() - x.mean()) ** 2)
    scale = float((y.std() - x.std()) ** 2)
    return {"D_pair": r4(d_pair), "D_marg": r4(d_marg), "shape_share": r4(d_marg / d_pair),
            "shuffle_share": r4(1 - d_marg / d_pair), "D_marg_location": r4(loc), "D_marg_scale": r4(scale),
            "D_marg_rest": r4(d_marg - loc - scale), "sd_x": r4(x.std()), "sd_y": r4(y.std()),
            "spearman": r4(spearmanr(x, y).statistic)}


def variance_split(x, y):
    """G42: Var(r) = (b - 1)^2 Var(x) + Var(e) for r = y - x and the OLS fit y = a + b x + e."""
    b = float(np.cov(x, y, bias=True)[0, 1] / x.var())
    e = (y - y.mean()) - b * (x - x.mean())
    r = y - x
    trend = (b - 1) ** 2 * x.var()
    return {"b": r4(b), "var_r": r4(r.var()), "trend": round(float(trend), 6), "trend_share": round(float(trend / r.var()), 6),
            "var_e": r4(e.var()), "identity_gap": float(r.var() - trend - e.var())}


def split_half_noise(means, rng, sel):
    """G40, G42: noise variance of ln chi at n docs from two random halves, assuming it scales as 1/n."""
    n = means.shape[0]
    order = rng.permutation(n)
    c1 = dc.set_chi(means[order[: n // 2]])[sel]
    c2 = dc.set_chi(means[order[n // 2: 2 * (n // 2)]])[sel]
    both = (c1 > 0) & (c2 > 0)
    d = np.log(c1[both]) - np.log(c2[both])
    return float(d.var() / 4), int((~both).sum())


def boot_multi(means, x, sel, masks, rng, n_boot, chunk=50):
    """G44: one set of doc resamples, the slope on each concept range."""
    n = means.shape[0]
    mt = means.T.tocsr()
    out = {k: [] for k in masks}
    for start in range(0, n_boot, chunk):
        size = min(chunk, n_boot - start)
        counts = rng.multinomial(n, np.full(n, 1 / n), size=size).T
        for s in np.asarray(mt @ counts).T:
            c = chi(s)[sel]
            for k, m in masks.items():
                out[k].append(slope(x[m], c[m]))
    return {k: np.array(v) for k, v in out.items()}


def main():
    c = dc.concepts()
    x, sel, chi_train, bins = c["x"], c["sel"], c["chi_train"], c["bin"]
    run_dir = settings.DATA / dc.RUN
    table = pd.read_parquet(run_dir / "distribution.parquet")
    pub = json.loads((settings.RESULTS / f"{dc.RUN}_distribution_summary.json").read_text())

    paths, all_lengths = dc.set_lengths()
    chosen, counts = choose(all_lengths)
    if counts != pub["docs_per_scope"]:
        raise SystemExit(f"G39: doc counts {counts} differ from published {pub['docs_per_scope']}")
    report = {"run": dc.RUN, "docs_per_scope": counts, "sets": {}, "check_max_rel_chi_diff": {}}
    means, lens, ids, chis = {}, {}, {}, {}
    for name in paths:
        means[name], ids[name], lens[name] = dc.read_means(paths[name], chosen[name]["doc"])
        report["check_max_rel_chi_diff"][name] = dc.check_chi(name, means[name], table)
        chis[name] = dc.set_chi(means[name])
        print(name, means[name].shape, means[name].nnz, flush=True)

    # G40, G42: per set
    noise = {}
    for j, name in enumerate(paths):
        y, zeros = log_y(chis[name][sel])
        noise[name], dropped = split_half_noise(means[name], np.random.default_rng([0, 40, j]), sel)
        r = y - x
        cs = chis[name]
        above = cs > chi_train
        vs = variance_split(x, y)
        if abs(vs["b"] - pub["sets"][name]["slope_chi"]) > 1e-4:
            raise SystemExit(f"G39: slope of {name} {vs['b']} differs from published {pub['sets'][name]['slope_chi']}")
        entry = {"shape_vs_shuffle": shape_vs_shuffle(x, y), "variance_split": vs,
                 "median_ln_ratio": r4(np.median(r)), "median_log10_ratio": r4(np.median(r) / np.log(10)),
                 "share_slope_concepts_below_1x": r4((r < 0).mean()), "slope_concepts_with_chi_0": zeros,
                 "noise_var_split_half": r4(noise[name]), "split_half_concepts_dropped": dropped,
                 "all_concepts_above_1x": int(above.sum()),
                 "mass_share_of_concepts_above_1x": r4(cs[above].sum() / D_SAE),
                 "train_mass_share_of_same_concepts": r4(chi_train[above].sum() / D_SAE),
                 "length_quantiles": {str(q): int(np.quantile(lens[name], q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
                 "share_docs_under_30_tokens": r4((lens[name] < SHORT).mean())}
        # G41: concentration and moved mass
        own = np.sort(cs)[::-1]
        entry["top_k_mass_share"] = {str(k): r4(own[:k].sum() / D_SAE) for k in TOP_K}
        gain = cs - chi_train
        tv = gain.clip(0).sum() / D_SAE
        order = np.argsort(-gain)
        entry["tv_distance_to_train"] = r4(tv)
        entry["tv_share_top_30_gainers"] = r4(gain[order[:30]].clip(0).sum() / D_SAE / tv)
        entry["tv_share_top_1000_gainers"] = r4(gain[order[:1000]].clip(0).sum() / D_SAE / tv)
        # G42: window frames from the published table (noise is whole-doc only)
        entry["variance_split_windows"] = []
        for w in range(len(settings.WINDOWS)):
            yw, _ = log_y(table[f"chi_{name}_w{w}"].to_numpy()[sel])
            entry["variance_split_windows"].append(variance_split(x, yw))
        report["sets"][name] = entry
    own_train = np.sort(chi_train)[::-1]
    report["train_top_k_mass_share"] = {str(k): r4(own_train[:k].sum() / D_SAE) for k in TOP_K}
    noise_train = report["sets"]["V"]["variance_split"]["var_r"] - noise["V"]
    report["noise_train_var"] = r4(noise_train)
    for name, entry in report["sets"].items():  # G42: excess dispersion
        ex = entry["variance_split"]["var_r"] - noise[name] - noise_train
        entry["excess_dispersion_var"] = r4(ex)
        entry["excess_dispersion_sd"] = r4(np.sign(ex) * np.sqrt(abs(ex)))
    out_json = settings.RESULTS / f"{dc.RUN}_diagnostics.json"
    out_json.write_text(json.dumps(report, indent=1))  # checkpoint: later stages add to it
    print("G40-G42 done", flush=True)

    # G44, G45: delta by concept range, with basic intervals and bias-corrected point estimates
    masks = {k: f(bins) for k, f in MASKS.items()}
    rng = np.random.default_rng([0, 44])
    point, boots = {}, {}
    for name in paths:
        cs = chis[name][sel]
        point[name] = {k: slope(x[m], cs[m]) for k, m in masks.items()}
        boots[name] = boot_multi(means[name], x, sel, masks, rng, settings.BOOTSTRAP)
        print("boot", name, flush=True)
    report["delta_by_range"] = {}
    for name in paths:
        if name == "V":
            continue
        report["delta_by_range"][name] = {}
        for k in masks:
            d = point[name][k] - point["V"][k]
            db = boots[name][k] - boots["V"][k]
            bias = float(db.mean() - d)
            report["delta_by_range"][name][k] = {"concepts": int(masks[k].sum()), "delta": r4(d),
                                                 "ci95_basic": (2 * d - np.quantile(db, [0.975, 0.025])).round(4).tolist(),
                                                 "bootstrap_bias": r4(bias), "delta_bias_corrected": r4(d - bias)}
    report["binned_minus_V"] = {name: [r4(a - v) for a, v in zip(pub["sets"][name]["binned_median_log_ratio"],
                                                                   pub["sets"]["V"]["binned_median_log_ratio"])]
                                for name in pub["sets"] if name != "V"}
    report["full_post_delta_bias_corrected"] = {name: {"delta": d["delta"], "ci95_basic": d["ci95_basic"],
                                                       "bootstrap_bias": d["bootstrap_bias"],
                                                       "delta_bias_corrected": r4(d["delta"] - d["bootstrap_bias"])}
                                                for name, d in pub["delta_vs_V"].items()}  # G45
    out_json.write_text(json.dumps(report, indent=1))

    # G41: top gainers with names, short-doc share and token positions
    names = {int(k): v["dolma"] for k, v in json.loads(NAMES.read_text()).items()}
    gainers = {name: np.argsort(-(chis[name] - chi_train))[:N_GAINERS] for name in SETS_DETAIL}
    union = sorted({int(k) for v in gainers.values() for k in v})
    report["gainers"] = {}
    for name in SETS_DETAIL:
        total, pos_sum, early = dc.token_positions(paths[name], chosen[name]["doc"], union)
        short_sum = np.asarray(means[name][lens[name] < SHORT].sum(0)).ravel()
        all_sum = np.asarray(means[name].sum(0)).ravel()
        n_fire = np.diff((means[name] > 0).T.tocsr().indptr)
        rows = []
        for k in gainers[name]:
            k = int(k)
            rows.append({"concept": k, "chi_train": float(f"{chi_train[k]:.4g}"), "chi_V": float(f"{chis['V'][k]:.4g}"),
                         "chi_set": float(f"{chis[name][k]:.4g}"), "mass_gain_share": r4((chis[name][k] - chi_train[k]) / D_SAE),
                         "ln_ratio": r4(np.log(chis[name][k] / chi_train[k])) if chis[name][k] > 0 and chi_train[k] > 0 else None,
                         "n_fire_train": int(c["n_fire_train"][k]), "n_fire_set": int(n_fire[k]), "in_slope": bool(sel[k]),
                         "name": names.get(k), "share_chi_from_docs_under_30": r4(short_sum[k] / all_sum[k]) if all_sum[k] else None,
                         "mean_token_position": round(float(pos_sum[k] / total[k]), 1) if total[k] else None,
                         "share_activation_positions_0_3": r4(early[k] / total[k]) if total[k] else None})
        report["gainers"][name] = rows
        print("positions", name, flush=True)
    out_json.write_text(json.dumps(report, indent=1))
    print("wrote", out_json, flush=True)

    # G41: example windows (pool only, G20)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    docs = pd.read_parquet(settings.EXP1_RUN / "docs.parquet", columns=["doc_id", "subset", "text"]).set_index("doc_id")
    needed = sorted({int(k) for g in dc.SHOWN for k in gainers[g][:N_EXAMPLES]})
    v_keep = set(chosen["V"]["doc"])
    v_top = top_windows(paths["V"], needed, lambda d: np.array([i in v_keep for i in d]))
    out = [f"# full_post diagnostics: top {N_EXAMPLES} concepts by χ mass gain per rollout set (design.md G41)\n"]
    for g in dc.SHOWN:
        keep = set(chosen[g]["doc"])
        rolls = pd.concat([pd.read_parquet(p) for p in sorted((run_dir / g / "rollouts").glob("part_?????.parquet"))]).set_index("rollout_id")
        g_top = top_windows(paths[g], needed, lambda d: np.array([i in keep for i in d]))
        out.append(f"\n## {g}\n")
        for row in report["gainers"][g][:N_EXAMPLES]:
            k = row["concept"]
            out.append(f"\n### Concept {k}: χ_train {row['chi_train']}, χ_V {row['chi_V']}, χ_{g} {row['chi_set']} "
                       f"(gain {row['mass_gain_share']:.2%} of all χ mass); firing docs train {row['n_fire_train']}, {g} {row['n_fire_set']}; "
                       f"mean token position {row['mean_token_position']}, activation at positions 0-3 {row['share_activation_positions_0_3']}, "
                       f"χ from docs under 30 tokens {row['share_chi_from_docs_under_30']}\n")
            out.append(f"Exp 1 Dolma name: {row['name'] or '(none; not among the 240 named concepts)'}\n\nRollouts ({g}), top windows:\n")
            for r in g_top[g_top.concept == k].itertuples():
                ids_ = settings.encoder_ids(dc.RUN, rolls.at[r.doc_id, "ids"])  # G34
                out.append(f"- ({r.max:.2f}, `{r.doc_id}`) {window_text(tokenizer, tokenize(tokenizer, tokenizer.decode(ids_))[0], r.argmax)}\n")
            out.append("\nDolma V, top windows:\n")
            for r in v_top[v_top.concept == k].itertuples():
                out.append(f"- ({r.max:.2f}) {window_text(tokenizer, tokenize(tokenizer, docs.at[r.doc_id, 'text'])[0], r.argmax)}\n")
    (run_dir / "diagnostics_gainers.md").write_text("".join(out))
    print("wrote", run_dir / "diagnostics_gainers.md")


if __name__ == "__main__":
    main()
