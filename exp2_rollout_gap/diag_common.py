"""Shared setup for the full_post diagnostics (design.md G39). CPU only.

Rebuilds full_post's sets and G16's doc choice with s03's own functions and set order, and reads only the per-doc
means (Eq. 1) of the chosen docs. check_chi() proves the docs are the ones behind the published full_post numbers.
"""
import numpy as np
import pandas as pd
from scipy import sparse

import settings  # first: puts Exp 1 on the path
from s03_distribution import D_SAE, degeneration, lengths
from s05_coverage import MISSING, chi  # Exp 1: e^-5 and Eq. 2

RUN = "full_post"
SHOWN = ["stage1", "main", "sft", "dpo", "instruct"]  # rollout sets reported in tables (no-loop versions in the JSON)


def concepts():
    """x axis of G11/G13: ln chi_train over the slope concepts, the G11 bins, and the firing-share x (G9)."""
    cov = pd.read_parquet(settings.EXP1_RUN / "coverage.parquet")
    web = pd.read_parquet(settings.EXP1_RUN / "coverage_vs_pile_web.parquet", columns=["n_fire_train"])
    docs = pd.read_parquet(settings.EXP1_RUN / "docs.parquet", columns=["doc_id", "subset"])
    n_train = int((docs["subset"] != "V").sum())
    chi_train = cov["chi_train"].to_numpy()
    n_fire_train = web["n_fire_train"].to_numpy()
    sel = (n_fire_train >= settings.MIN_TRAIN_FIRING_DOCS) & (chi_train >= MISSING)  # G13
    x = np.log(chi_train[sel])
    edges = np.quantile(x, np.linspace(0, 1, settings.N_BINS + 1))
    return {"chi_train": chi_train, "sel": sel, "x": x, "edges": edges, "bin": np.clip(np.digitize(x, edges[1:-1]), 0, len(edges) - 2),
            "x_fire": np.log((n_fire_train / n_train)[sel]), "n_fire_train": n_fire_train}


def set_lengths():
    """s03's set list, in s03's order (V, then each generator and its no-loop version, G14), with doc lengths."""
    run_dir = settings.DATA / RUN
    docs = pd.read_parquet(settings.EXP1_RUN / "docs.parquet", columns=["doc_id", "subset"])
    v_ids = set(docs.loc[docs["subset"] == "V", "doc_id"])
    paths = {"V": sorted((settings.EXP1_RUN / "acts").glob("part_?????.npz"))}
    all_lengths = {"V": lengths(paths["V"], lambda ids: np.array([d in v_ids for d in ids]))}
    for g in settings.GENERATORS:
        g_paths = sorted((run_dir / g / "acts").glob("part_?????.npz"))
        if not g_paths:
            continue
        rolls = pd.concat([pd.read_parquet(p) for p in sorted((run_dir / g / "rollouts").glob("part_?????.parquet"))])
        degen = rolls.set_index("rollout_id")["ids"].map(lambda ids: degeneration(settings.encoder_ids(RUN, ids))).astype(float)
        flagged = set(degen.index[degen >= settings.DEGEN_THRESHOLD])
        paths[g] = g_paths
        all_lengths[g] = lengths(g_paths, lambda ids: np.ones(len(ids), dtype=bool))
        paths[f"{g}_no_loops"] = g_paths
        all_lengths[f"{g}_no_loops"] = lengths(g_paths, lambda ids: np.array([d not in flagged for d in ids]))
    return paths, all_lengths


def read_means(paths, keep_ids):
    """Per-doc Eq. 1 means of the docs in keep_ids, as a sparse (docs x concepts) matrix, with doc ids and lengths.
    Only the doc-level arrays are read (npz loads arrays on access)."""
    keep_ids = np.asarray(keep_ids)
    mats, ids, lens = [], [], []
    for path in paths:
        with np.load(path, allow_pickle=True) as z:
            doc_id = z["doc_id"]
            keep = np.isin(doc_id, keep_ids)
            if not keep.any():
                continue
            rows = np.repeat(np.arange(len(doc_id)), z["doc_active"])
            m = sparse.csr_matrix((z["doc_mean"].astype(np.float64), (rows, z["doc_latent_ids"].astype(np.int64))),
                                  shape=(len(doc_id), D_SAE))[keep]
            mats.append(m)
            ids.append(doc_id[keep])
            lens.append(z["doc_tokens"][keep])
    return sparse.vstack(mats).tocsr(), np.concatenate(ids), np.concatenate(lens).astype(np.int64)


def set_chi(means):
    return chi(np.asarray(means.sum(0)).ravel())


def check_chi(name, means, table):
    """G39: chi from the re-chosen docs must equal the published full_post chi."""
    c, ref = set_chi(means), table[f"chi_{name}"].to_numpy()
    pos = ref > 0
    rel = float((np.abs(c[pos] - ref[pos]) / ref[pos]).max())
    if rel >= 1e-9 or (c[~pos] != 0).any():
        raise SystemExit(f"G39 check failed for {name}: max relative chi difference {rel}")
    return rel


def token_positions(paths, keep_ids, concepts_of_interest):
    """G41: per concept, summed activation, activation x token position, and activation at positions 0-3, over the
    token-level entries of the chosen docs."""
    keep_ids = np.asarray(keep_ids)
    want = np.zeros(D_SAE, dtype=bool)
    want[list(concepts_of_interest)] = True
    total, pos_sum, early = np.zeros(D_SAE), np.zeros(D_SAE), np.zeros(D_SAE)
    for path in paths:
        with np.load(path, allow_pickle=True) as z:
            doc_id = z["doc_id"]
            keep = np.isin(doc_id, keep_ids)
            if not keep.any():
                continue
            doc_tokens = z["doc_tokens"].astype(np.int64)
            tok_doc = np.repeat(np.arange(len(doc_id)), doc_tokens)
            tok_pos = np.arange(len(tok_doc)) - np.repeat(np.cumsum(doc_tokens) - doc_tokens, doc_tokens)
            ent_tok = np.repeat(np.arange(len(tok_doc)), z["tok_counts"].astype(np.int64))
            lat = z["latent_ids"].astype(np.int64)
            m = want[lat] & keep[tok_doc[ent_tok]]
            lat, val, pos = lat[m], z["values"][m].astype(np.float64), tok_pos[ent_tok[m]]
        total += np.bincount(lat, weights=val, minlength=D_SAE)
        pos_sum += np.bincount(lat, weights=val * pos, minlength=D_SAE)
        early += np.bincount(lat[pos < 4], weights=val[pos < 4], minlength=D_SAE)
    return total, pos_sum, early
