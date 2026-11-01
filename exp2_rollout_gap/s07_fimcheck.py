"""Robustness check on the published main result (design.md G35). CPU only.

Usage: python s07_fimcheck.py   (after s03 --run full_fimcheck --degen 0.6)
Compares results/full_distribution_summary.json (published, 108 FIM ids kept) with
results/full_fimcheck_distribution_summary.json (same V, stage1, seeds; main with ids >= 100256 dropped, G34).
Also compares main's re-encoded acts (full_post/main/acts) with the published ones (full/main/acts): which rollouts
changed length, whether any crossed a scope boundary (which would change the G16 draws), and whether the rollouts
without special ids got identical activations (GPU nondeterminism would make them differ).
Writes results/full_fimcheck_summary.json.
"""
import json

import settings
import numpy as np
import pandas as pd

from s03_distribution import degeneration

ARRAYS = ["doc_latent_ids", "doc_mean", "doc_max"]  # per doc, sliced by doc_active
TOKEN_ARRAYS = ["latent_ids", "values"]  # per token entry, sliced by the doc's tok_counts


def per_doc(path):
    """{doc_id: (doc_tokens, tuple of that doc's arrays)} for one acts part."""
    with np.load(path, allow_pickle=True) as z:
        z = {k: z[k] for k in z.files}
    d_end = np.cumsum(z["doc_active"])
    t_end = np.cumsum(z["doc_tokens"])
    e_end = np.cumsum(z["tok_counts"])
    out = {}
    for i, doc in enumerate(z["doc_id"]):
        d0 = d_end[i] - z["doc_active"][i]
        t0, t1 = t_end[i] - z["doc_tokens"][i], t_end[i]
        e0, e1 = (e_end[t0 - 1] if t0 else 0), e_end[t1 - 1]
        out[doc] = (int(z["doc_tokens"][i]), [z[k][d0:d_end[i]] for k in ARRAYS] + [z["tok_counts"][t0:t1]]
                    + [z[k][e0:e1] for k in TOKEN_ARRAYS])
    return out


def main():
    pub = json.loads((settings.RESULTS / "full_distribution_summary.json").read_text())
    new = json.loads((settings.RESULTS / "full_fimcheck_distribution_summary.json").read_text())
    rolls = pd.concat([pd.read_parquet(p) for p in sorted((settings.DATA / "full" / "main" / "rollouts").glob("part_?????.parquet"))])
    has_special = set(rolls.loc[rolls["ids"].map(lambda x: (np.asarray(x) >= settings.SPECIAL_MIN).any()), "rollout_id"])

    old_dir, new_dir = settings.DATA / "full" / "main" / "acts", settings.DATA / "full_post" / "main" / "acts"
    starts = [0] + [a for a, _ in settings.WINDOWS]
    changed_len, crossed, missing, same, differ, max_diff = [], [], [], 0, 0, 0.0
    for path in sorted(old_dir.glob("part_?????.npz")):
        old, re = per_doc(path), per_doc(new_dir / path.name)
        missing += [d for d in old if d not in re]
        for doc, (n_old, arr_old) in old.items():
            if doc not in re:
                continue
            n_new, arr_new = re[doc]
            if n_new != n_old:
                changed_len.append(doc)
                if any((n_old > s) != (n_new > s) for s in starts):
                    crossed.append(doc)
            if doc in has_special:
                continue
            if all(a.shape == b.shape and np.array_equal(a, b) for a, b in zip(arr_old, arr_new)):
                same += 1
            else:
                differ += 1
                if arr_old[1].shape == arr_new[1].shape and np.array_equal(arr_old[0], arr_new[0]):
                    max_diff = max(max_diff, float(np.abs(arr_old[1].astype(float) - arr_new[1].astype(float)).max(initial=0)))

    # G14 loop flags before (published: ids as generated) and after the drop (G34)
    flag_old = set(rolls.loc[rolls["ids"].map(degeneration) >= settings.DEGEN_THRESHOLD, "rollout_id"])
    flag_new = set(rolls.loc[rolls["ids"].map(lambda x: degeneration(settings.encoder_ids("full_fimcheck", x)))
                             >= settings.DEGEN_THRESHOLD, "rollout_id"])

    def pick(s):
        return {k: s[k] for k in ("docs", "slope_chi", "slope_chi_ci95_basic", "bootstrap_bias", "slope_fire_share")}

    summary = {
        "note": "Published Exp 2 main results include 108 FIM ids in 70 of 10,000 rollouts (design.md G34, G35)",
        "docs_per_scope": {"published": pub["docs_per_scope"], "after_drop": new["docs_per_scope"],
                           "equal": pub["docs_per_scope"] == new["docs_per_scope"]},
        "delta_vs_V": {name: {"published": pub["delta_vs_V"][name], "after_drop": new["delta_vs_V"][name]}
                       for name in pub["delta_vs_V"]},
        "slopes": {name: {"published": pick(pub["sets"][name]), "after_drop": pick(new["sets"][name])} for name in pub["sets"]},
        "V_and_stage1_reproduce": all(pub["sets"][n] == new["sets"][n] for n in ("V", "stage1", "stage1_no_loops")),
        "main_rollouts_with_special_ids": len(has_special),
        "main_rollouts_missing_after_drop": len(missing),
        "main_rollouts_length_changed": len(changed_len),
        "main_rollouts_crossing_a_scope_start": sorted(crossed),
        "loop_flags": {"published": len(flag_old), "after_drop": len(flag_new),
                       "changed": sorted(flag_old ^ flag_new)},
        "unchanged_rollouts_identical_acts": same, "unchanged_rollouts_different_acts": differ,
        "max_abs_doc_mean_diff_where_different": max_diff,
    }
    (settings.RESULTS / "full_fimcheck_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
