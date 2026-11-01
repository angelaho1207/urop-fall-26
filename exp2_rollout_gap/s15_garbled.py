"""Garbled-rollout check from the per-doc NLL of s14 (design.md G56-G59). CPU only.

Usage: python s15_garbled.py
1. Threshold = 99th percentile of V's mean NLL, written to results/full_post_garbled_threshold.json before any
   rollout NLL is read (G56).
2. Per set: share flagged, token-weighted share, NLL quantiles, short-doc share, overlap with G14 loops.
3. DATA/full_post/garbled_examples.md: 10 random flagged and 10 just-below rollouts per post-trained set (G57, pool).
4. Run full_post_noflag: flagged docs dropped from every set, one G16 count, then Δ vs V (bias-corrected), excess
   dispersion, median ln ratio, and G41's top 10 gainers after the filter (G58).
Writes results/full_post_noflag_distribution_summary.json and results/full_post_garbled_summary.{json,md}.
"""
import json

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np
import pandas as pd
from transformers import AutoTokenizer

import diag_common as dc
from s03_distribution import D_SAE, bootstrap_slopes, degeneration, log_y, slope
from s03_pilot import tokenize  # Exp 1
from s09_diagnostics import split_half_noise, variance_split
from s14_nll import GENERATORS, OUT as NLL, acts_run

RUN = dc.RUN
NOFLAG = f"{RUN}_noflag"
QUANTILES = (0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99)
POST = ["sft", "dpo", "instruct"]
SHORT = 30
N_EXAMPLES = 10
N_GAINERS = 10
R = settings.RESULTS


def r4(v):
    return None if v is None else round(float(v), 4)


def read_nll(s):
    parts = sorted((NLL / s).glob("part_?????.npz"))
    frames = []
    for p in parts:
        with np.load(p, allow_pickle=True) as z:
            frames.append(pd.DataFrame({k: z[k] for k in ("doc_id", "n_tokens", "n_pred", "nll_mean")}))
    return pd.concat(frames).set_index("doc_id")


def loop_flags(g):
    rolls = pd.concat([pd.read_parquet(p) for p in sorted((settings.DATA / RUN / g / "rollouts").glob("part_?????.parquet"))])
    degen = rolls.set_index("rollout_id")["ids"].map(lambda ids: degeneration(settings.encoder_ids(RUN, ids))).astype(float)
    return degen >= settings.DEGEN_THRESHOLD  # G14, as diag_common.set_lengths


def describe(df, thr, loops=None):
    has = df["nll_mean"].notna()
    flag = has & (df["nll_mean"] > thr)
    out = {"docs": len(df), "docs_without_nll": int((~has).sum()), "flagged": int(flag.sum()),
           "share_flagged": r4(flag.mean()), "token_weighted_share": r4(df.loc[flag, "n_tokens"].sum() / df["n_tokens"].sum()),
           "nll_quantiles": {str(q): r4(np.quantile(df.loc[has, "nll_mean"], q)) for q in QUANTILES},
           "share_flagged_docs_under_30_tokens": r4(flag[df["n_tokens"] < SHORT].mean()) if (df["n_tokens"] < SHORT).any() else None,
           "share_flagged_docs_30_plus_tokens": r4(flag[df["n_tokens"] >= SHORT].mean())}
    if loops is not None:
        lp = loops.reindex(df.index).fillna(False).astype(bool)
        out["share_of_flagged_that_are_loops"] = r4(lp[flag].mean()) if flag.any() else None
        out["share_of_loops_flagged"] = r4(flag[lp].mean()) if lp.any() else None
    return out, flag


def examples(nll, flags, thr, loops):
    tok = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    md = [f"# Garbled-rollout examples (design.md G57; threshold {thr:.4f} nats, V's 99th percentile)\n\n"
          "Pool only (G20): rollout text. Text shown is what the encoder scored (decoded, cut to 1,024 tokens).\n"]
    for j, g in enumerate(POST):
        df = nll[g]
        rolls = pd.concat([pd.read_parquet(p) for p in sorted((settings.DATA / RUN / g / "rollouts").glob("part_?????.parquet"))]).set_index("rollout_id")["ids"]
        flagged = np.sort(df.index[flags[g]].to_numpy())
        pick = np.random.default_rng([0, 57, j]).choice(flagged, size=min(N_EXAMPLES, len(flagged)), replace=False)
        below = df[df["nll_mean"].notna() & ~flags[g]].sort_values("nll_mean", ascending=False).index[:N_EXAMPLES]
        for title, ids in ((f"{g}: {len(pick)} random flagged of {len(flagged)}", pick), (f"{g}: {len(below)} highest below the threshold", below)):
            md.append(f"\n## {title}\n")
            for d in ids:
                text = tok.decode(tokenize(tok, tok.decode(settings.encoder_ids(acts_run(g), rolls.at[d])))[0]).replace("~~~~", "~ ~ ~ ~")
                md.append(f"\n### `{d}`: NLL {df.at[d, 'nll_mean']:.3f}, {df.at[d, 'n_tokens']} tokens, loop {bool(loops[g].get(d, False))}\n\n~~~~\n{text}\n~~~~\n")
    (settings.DATA / RUN / "garbled_examples.md").write_text("".join(md))


def recompute(drop):
    """G58: as s10's min30 run, with flagged docs (and docs without an NLL) dropped from every set."""
    c = dc.concepts()
    x, sel, chi_train = c["x"], c["sel"], c["chi_train"]
    paths, all_lengths = dc.set_lengths()
    eligible = {name: np.sort(n.index[~n.index.isin(list(drop[name.replace("_no_loops", "")]))].to_numpy()) for name, n in all_lengths.items()}
    n = min(len(e) for e in eligible.values())
    chosen = {name: np.random.default_rng([0, 58, 9, j]).choice(e, size=n, replace=False) for j, (name, e) in enumerate(eligible.items())}
    rng = np.random.default_rng(0)  # as s03
    summary = {"run": NOFLAG, "docs": n, "available": {k: len(e) for k, e in eligible.items()}, "sets": {}}
    boots, slopes, chis, noise, var_r = {}, {}, {}, {}, {}
    for j, name in enumerate(paths):
        means, _, lens = dc.read_means(paths[name], chosen[name])
        cs = dc.set_chi(means)
        chis[name] = cs
        b = slope(x, cs[sel])
        boots[name], slopes[name] = bootstrap_slopes(means, x, sel, rng, settings.BOOTSTRAP), b
        y, zeros = log_y(cs[sel])
        noise[name], _ = split_half_noise(means, np.random.default_rng([0, 58, j]), sel)
        vs = variance_split(x, y)
        var_r[name] = vs["var_r"]
        summary["sets"][name] = {"docs": int(means.shape[0]), "slope_chi": r4(b), "bootstrap_bias": r4(boots[name].mean() - b),
                                 "median_ln_ratio": r4(np.median(y - x)), "variance_split": vs, "noise_var_split_half": r4(noise[name]),
                                 "selected_concepts_with_chi_0": zeros,
                                 "length_quantiles": {str(q): int(np.quantile(lens, q)) for q in (0.1, 0.5, 0.9)}}
        print(name, means.shape[0], round(b, 4), flush=True)
    noise_train = var_r["V"] - noise["V"]
    summary["noise_train_var"] = r4(noise_train)
    for name, e in summary["sets"].items():  # G42
        ex = e["variance_split"]["var_r"] - noise[name] - noise_train
        e["excess_dispersion_var"], e["excess_dispersion_sd"] = r4(ex), r4(np.sign(ex) * np.sqrt(abs(ex)))
    summary["delta_vs_V"] = {}
    for name in paths:
        if name == "V":
            continue
        d, db = slopes[name] - slopes["V"], boots[name] - boots["V"]
        bias = float(db.mean() - d)
        summary["delta_vs_V"][name] = {"delta": r4(d), "ci95_basic": (2 * d - np.quantile(db, [0.975, 0.025])).round(4).tolist(),
                                       "bootstrap_bias": r4(bias), "delta_bias_corrected": r4(d - bias)}  # G45
    out_dir = settings.DATA / NOFLAG
    out_dir.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame({"concept": np.arange(D_SAE), "chi_train": chi_train, "in_slope": sel, **{f"chi_{k}": v for k, v in chis.items()}})
    table.to_parquet(out_dir / "distribution.parquet")
    (R / f"{NOFLAG}_distribution_summary.json").write_text(json.dumps(summary, indent=1))
    return summary, chis, chi_train


def main():
    # 1. Threshold from V alone, written before any rollout NLL is read (G56)
    if len(list((NLL / "V").glob("part_?????.npz"))) != 20:
        raise SystemExit("V parts missing")
    nll = {"V": read_nll("V")}
    v = nll["V"]["nll_mean"].dropna()
    thr = float(np.quantile(v, 0.99))
    (R / f"{RUN}_garbled_threshold.json").write_text(json.dumps({"threshold_nats": round(thr, 6), "v_docs_with_nll": len(v), "quantile": 0.99}, indent=1))
    print("threshold", thr, flush=True)

    # 2. Per set
    for g in GENERATORS:
        nll[g] = read_nll(g)
    loops = {g: loop_flags(g) for g in GENERATORS}
    report = {"threshold_nats": round(thr, 6), "sets": {}}
    flags, drop = {}, {}
    for s in ["V"] + GENERATORS:
        report["sets"][s], flags[s] = describe(nll[s], thr, loops.get(s))
        drop[s] = set(nll[s].index[flags[s] | nll[s]["nll_mean"].isna()])
    # 3. Examples (pool only)
    examples(nll, flags, thr, loops)
    # 4. Recompute without flagged docs
    noflag, chis, chi_train = recompute(drop)
    pub = json.loads((R / f"{RUN}_distribution_summary.json").read_text())
    diag = json.loads((R / f"{RUN}_diagnostics.json").read_text())
    table = pd.read_parquet(settings.DATA / RUN / "distribution.parquet")
    report["noflag_docs_per_set"] = noflag["docs"]
    report["compare"] = {}
    for g in dc.SHOWN:
        gain_new = chis[g] - chi_train
        rank_new = np.empty(D_SAE, dtype=np.int64)
        rank_new[np.argsort(-gain_new)] = np.arange(1, D_SAE + 1)
        gain_old = table[f"chi_{g}"].to_numpy() - chi_train
        top = [int(r["concept"]) for r in diag["gainers"][g][:N_GAINERS]]
        report["compare"][g] = {
            "delta": {"full_post": pub["delta_vs_V"][g]["delta"], "noflag": noflag["delta_vs_V"][g]["delta"]},
            "delta_bias_corrected": {"full_post": diag["full_post_delta_bias_corrected"][g]["delta_bias_corrected"],
                                     "noflag": noflag["delta_vs_V"][g]["delta_bias_corrected"]},
            "noflag_ci95_basic": noflag["delta_vs_V"][g]["ci95_basic"],
            "excess_dispersion_var": {"full_post": diag["sets"][g]["excess_dispersion_var"], "noflag": noflag["sets"][g]["excess_dispersion_var"]},
            "excess_dispersion_sd": {"full_post": diag["sets"][g]["excess_dispersion_sd"], "noflag": noflag["sets"][g]["excess_dispersion_sd"]},
            "median_ln_ratio": {"full_post": diag["sets"][g]["median_ln_ratio"], "noflag": noflag["sets"][g]["median_ln_ratio"]},
            "top_gainers": [{"concept": k, "rank_full_post": i + 1, "rank_noflag": int(rank_new[k]),
                             "gain_share_full_post": r4(gain_old[k] / D_SAE), "gain_share_noflag": r4(gain_new[k] / D_SAE)} for i, k in enumerate(top)],
        }
        tg = report["compare"][g]["top_gainers"]
        report["compare"][g]["top10_still_top10"] = sum(t["rank_noflag"] <= 10 for t in tg)
        report["compare"][g]["top10_in_top30"] = sum(t["rank_noflag"] <= 30 for t in tg)
    (R / f"{RUN}_garbled_summary.json").write_text(json.dumps(report, indent=1))

    md = [f"# Exp 2 garbled-rollout check (design.md G54-G59)\n\nThreshold: {thr:.4f} nats (99th percentile of V's mean NLL, "
          f"{len(v):,} docs). Encoder: main, bf16. Recomputed run `{NOFLAG}`: {noflag['docs']:,} docs per set after dropping flagged docs (G16).\n",
          "\n| set | docs | flagged | share flagged | token-weighted share | NLL 1 / 10 / 50 / 90 / 99% | flagged share, < 30 tokens / ≥ 30 | flagged that are loops | loops flagged |\n|---|---|---|---|---|---|---|---|---|\n"]
    for s, e in report["sets"].items():
        q = e["nll_quantiles"]
        md.append(f"| {s} | {e['docs']:,} | {e['flagged']:,} | {e['share_flagged']:.1%} | {e['token_weighted_share']:.1%} | "
                  f"{q['0.01']:.2f} / {q['0.1']:.2f} / {q['0.5']:.2f} / {q['0.9']:.2f} / {q['0.99']:.2f} | "
                  f"{e['share_flagged_docs_under_30_tokens']} / {e['share_flagged_docs_30_plus_tokens']} | "
                  f"{e.get('share_of_flagged_that_are_loops', '–')} | {e.get('share_of_loops_flagged', '–')} |\n")
    md.append("\n| set | Δ vs V (full_post → noflag) | bias-corrected Δ | noflag basic 95% | excess dispersion sd | median ln ratio | top 10 gainers still top 10 / in top 30 |\n|---|---|---|---|---|---|---|\n")
    for g, e in report["compare"].items():
        f = lambda k: f"{e[k]['full_post']:+.4f} → {e[k]['noflag']:+.4f}"  # noqa: E731
        md.append(f"| {g} | {f('delta')} | {f('delta_bias_corrected')} | [{e['noflag_ci95_basic'][0]:+.4f}, {e['noflag_ci95_basic'][1]:+.4f}] | "
                  f"{e['excess_dispersion_sd']['full_post']:.2f} → {e['excess_dispersion_sd']['noflag']:.2f} | {f('median_ln_ratio')} | "
                  f"{e['top10_still_top10']} / {e['top10_in_top30']} |\n")
    md.append("\nTop 10 gainers (G41), rank after the filter: " + "; ".join(
        f"{g} " + ", ".join(f"{t['concept']}→{t['rank_noflag']}" for t in e["top_gainers"]) for g, e in report["compare"].items()) + ".\n")
    (R / f"{RUN}_garbled_summary.md").write_text("".join(md))
    print("".join(md))


if __name__ == "__main__":
    main()
