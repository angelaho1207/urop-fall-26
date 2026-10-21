"""Qualitative results before metrics (design.md G19, G20). CPU only.

Usage: python s04_examples.py --run full
Reads DATA/<run>/distribution.parquet (from s03), the rollouts and acts of each generator, Exp 1's docs.parquet,
acts/ and concept names. Writes DATA/<run>/examples.md (pool, never git: G20).
"""
import argparse
import json

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config
import numpy as np
import pandas as pd
from transformers import AutoTokenizer

from s03_pilot import tokenize  # Exp 1
from s06_examples import BEFORE, WINDOW  # Exp 1 E1: 32-token windows, 16 tokens before the max

N_ROLLOUTS_SHOWN, N_EXTREMES, N_WINDOWS = 10, 5, 5
NAMES = settings.EXP1_RUN / "labels" / "faith" / "names.json"


def top_windows(paths, concepts, keep_of):
    """G19: for each concept, the N_WINDOWS docs with the highest max activation, with the max's position."""
    rows = []
    for path in paths:
        with np.load(path, allow_pickle=True) as z:
            keep = keep_of(z["doc_id"])
            doc = np.repeat(np.arange(len(z["doc_id"])), z["doc_active"])
            m = np.isin(z["doc_latent_ids"], concepts) & keep[doc]
            rows.append(pd.DataFrame({"concept": z["doc_latent_ids"][m].astype(int), "doc_id": z["doc_id"][doc[m]],
                                      "max": z["doc_max"][m], "argmax": z["doc_argmax"][m].astype(int)}))
    df = pd.concat(rows)
    return df.sort_values("max", ascending=False).groupby("concept").head(N_WINDOWS)


def window_text(tokenizer, ids, center):
    """Exp 1 E1 window, with the max token marked as [[token]]."""
    start = int(min(max(center - BEFORE, 0), max(len(ids) - WINDOW, 0)))
    piece = ids[start:start + WINDOW]
    k = center - start
    text = tokenizer.decode(piece[:k]) + "[[" + tokenizer.decode(piece[k:k + 1]) + "]]" + tokenizer.decode(piece[k + 1:])
    return text.replace("\n", "⏎ ")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, choices=["pilot", "full"])
    args = parser.parse_args()
    run_dir = settings.DATA / args.run
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.MODEL_REVISION)
    table = pd.read_parquet(run_dir / "distribution.parquet").set_index("concept")
    names = {int(c): v["dolma"] for c, v in json.loads(NAMES.read_text()).items()}
    gens = [g for g in settings.GENERATORS if f"chi_{g}" in table]
    out = [f"# Exp 2 examples, run {args.run}\n"]

    # (a) Sample rollouts, as the model wrote them (G19)
    rolls = {}
    for g in gens:
        rolls[g] = pd.concat([pd.read_parquet(p) for p in sorted((run_dir / g / "rollouts").glob("part_?????.parquet"))])
        rolls[g] = rolls[g].set_index("rollout_id")
        out.append(f"\n## (a) {N_ROLLOUTS_SHOWN} rollouts, {g}\n")
        for i in np.random.default_rng([0, 19]).choice(len(rolls[g]), size=N_ROLLOUTS_SHOWN, replace=False):
            ids = list(rolls[g]["ids"].iloc[i])
            text = tokenizer.decode(ids)[:600].replace("\n", "⏎ ")
            out.append(f"- `{rolls[g].index[i]}` ({len(ids)} tokens, ended by EOS: {rolls[g]['ended_by_eos'].iloc[i]}): {text}\n")

    # (b) Named concepts with the largest gaps vs V (G19)
    named = [c for c in names if table.at[c, "in_slope"]]
    picks = {}
    for g in gens:
        sub = table.loc[named]
        tiny = sub.loc[sub[f"chi_{g}"] > 0, f"chi_{g}"].min() / 2  # G13 floor, so chi = 0 ranks as most suppressed
        score = np.log(np.maximum(sub[f"chi_{g}"], tiny) / sub["chi_V"]).sort_values()
        picks[g] = {"rarer in rollouts": score.index[:N_EXTREMES].tolist(),
                    "more common in rollouts": score.index[::-1][:N_EXTREMES].tolist()}
    needed = sorted({c for p in picks.values() for side in p.values() for c in side})

    docs = pd.read_parquet(settings.EXP1_RUN / "docs.parquet", columns=["doc_id", "subset", "text"]).set_index("doc_id")
    v_ids = set(docs.index[docs["subset"] == "V"])
    v_top = top_windows(sorted((settings.EXP1_RUN / "acts").glob("part_?????.npz")), needed,
                        lambda ids: np.array([d in v_ids for d in ids]))
    g_top = {g: top_windows(sorted((run_dir / g / "acts").glob("part_?????.npz")), needed,
                            lambda ids: np.ones(len(ids), dtype=bool)) for g in gens}

    def v_window(r):
        return window_text(tokenizer, tokenize(tokenizer, docs.at[r.doc_id, "text"])[0], r.argmax)

    def g_window(g, r):  # G8: the encoded ids are the re-tokenized text
        return window_text(tokenizer, tokenize(tokenizer, tokenizer.decode(list(rolls[g].at[r.doc_id, "ids"])))[0], r.argmax)

    for g in gens:
        for side, concepts in picks[g].items():
            out.append(f"\n## (b) {g}: named concepts {side} than in Dolma V\n")
            for c in concepts:
                row = table.loc[c]
                out.append(f"\n### Concept {c}: χ_train {row.chi_train:.3g}, χ_V {row.chi_V:.3g}, χ_{g} {row[f'chi_{g}']:.3g}; "
                           f"firing docs V {row.n_fire_V}, {g} {row[f'n_fire_{g}']}\n")
                out.append(f"Exp 1 Dolma name: {names[c]}\n\n")
                out.append("Dolma V, top windows:\n")
                out += [f"- ({r.max:.2f}) {v_window(r)}\n" for r in v_top[v_top.concept == c].itertuples()]
                out.append(f"\nRollouts ({g}), top windows:\n")
                out += [f"- ({r.max:.2f}) {g_window(g, r)}\n" for r in g_top[g][g_top[g].concept == c].itertuples()]

    path = run_dir / "examples.md"
    path.write_text("".join(out))
    print(path)


if __name__ == "__main__":
    main()
