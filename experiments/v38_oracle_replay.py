"""v3.8 Phase 0 Part A: exact replay of the three reference arms.

Pre-registered in ``docs/v3_8_fact_preregistration.md`` §1 (the v3.7
correction obligation) and §3. Read-only: this script imports the frozen
experiment modules and calls their functions; nothing in ``src/`` or in the
frozen scripts is modified. CPU-only, API 0. Every float must match the frozen
record within 1e-9, every int/bool/selection exactly.

Three replays, aligned per sample_uid:

  R1  v3.3 unrestricted candidate oracle
      (``v33_compare_arms._decisions(real, "oracle")`` + ``_episode_metrics``)
      against ``results/v33_clean_rerun.json`` arms.oracle_relabel.
      Candidate set = the whole per-window pool with RESEGMENT closed (no
      score ordering, no structural veto); held-out labels choose THE
      CANDIDATE directly (max true_repair_gain among beneficial_and_safe);
      no CHR/pme/damage constraint.

  R2  v3.7 frozen-score constrained oracles
      (``v37_shift_headroom.oracle_global`` / ``oracle_expert_mixture``)
      against ``results/v37_shift_headroom.json``. Same underlying pool, but
      the per-candidate score/order is frozen: PAIR_absolute/logreg tournament
      score (global) or a convex mixture of training-source experts
      (mixture), with the frozen v2 structural veto applied. Held-out labels
      only choose the per-family threshold (and, for the mixture, the
      simplex weight) inside fixed grids, subject to CHR <= 0.10,
      pme <= 0.0055, damage <= 0.0402 per held-out fold.

  R3  PICS_joint_relabel incumbent
      (``v33_compare_arms._PICSArmX`` with ``PICS_JOINT_FEATURES``, LODO
      first-commit replay) against ``results/v33_clean_rerun.json``
      arms.PICS_joint_relabel and the per-window commit records in
      ``results/v33_clean_rerun_harmful.json``.

Per-uid commits for R2 are captured by re-driving the frozen v3.7 primitives
(``sweep_margins``/``_pick_best``/``_scored_arrays``/``_exact_metrics``) in
this script; the resulting metrics must equal both the frozen v3.7 record and
the values returned by ``v37.oracle_global``/``oracle_expert_mixture``
themselves (two code paths, one answer).

Any replay breach >= 1e-9 writes the diff report and exits 1: per the
pre-registration, Phase-0 conclusions are void until integrity is repaired.

Usage:
    python experiments/v38_oracle_replay.py
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

import v33_compare_arms as v33  # noqa: E402
import v36_pair_ranker_probe as v36  # noqa: E402
import v37_shift_headroom as v37  # noqa: E402
from introact_ts.contextual_shield import EPISODE_FAMILY_ORDER  # noqa: E402
from introact_ts.pics import PICS_JOINT_FEATURES  # noqa: E402

ROWS_PATH = ROOT / "results" / "v33_training_data.jsonl"
FROZEN_V33 = ROOT / "results" / "v33_clean_rerun.json"
FROZEN_V33_COMMITS = ROOT / "results" / "v33_clean_rerun_harmful.json"
FROZEN_V37 = ROOT / "results" / "v37_shift_headroom.json"
OUT = ROOT / "results" / "v38_oracle_replay.json"

TOL = 1e-9

#: Float fields of the v3.3 arm metric dict that must replay within TOL.
ARM_FLOAT_FIELDS = (
    "commit_rate", "damage", "conditional_harm_rate", "cond_damage",
    "conditional_mean_loss", "conditional_loss_p90", "conditional_loss_p95",
    "protected_mis_edit_rate", "coverage", "beneficial_coverage",
    "mean_repair_gain_contaminated", "max_dataset_bs_share",
)
#: Int fields that must replay exactly.
ARM_INT_FIELDS = ("n_windows", "committed", "beneficial_commits")

#: Float fields of the v3.7 public metric dict (``v37._public_metrics``).
V37_FLOAT_FIELDS = ("commit_rate", "bcov", "gain", "chr", "pme", "damage")
V37_INT_FIELDS = ("n_windows", "committed", "harmful_commits",
                  "beneficial_commits")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pkey(params):
    return json.dumps(params, sort_keys=True)


def _ckey(uid, fam, rung, params):
    return (uid, fam, rung, _pkey(params))


# -- generic comparison helpers (unit-tested locally) --------------------------


def compare_floats(got, ref, names, tol=TOL):
    """Per-field {got, ref, abs_diff, ok} for the named float fields."""
    out = {}
    for n in names:
        g, r = float(got[n]), float(ref[n])
        d = abs(g - r)
        out[n] = {"got": g, "ref": r, "abs_diff": d, "ok": bool(d < tol)}
    return out


def compare_ints(got, ref, names):
    out = {}
    for n in names:
        g, r = int(got[n]), int(ref[n])
        out[n] = {"got": g, "ref": r, "ok": bool(g == r)}
    return out


def compare_float_dict(got, ref, tol=TOL):
    """Compare {key: float} dicts: keys exact, values within tol."""
    keys_ok = set(got) == set(ref)
    per_key = {}
    worst = 0.0
    for k in sorted(set(got) | set(ref)):
        if k in got and k in ref:
            d = abs(float(got[k]) - float(ref[k]))
            worst = max(worst, d)
            per_key[k] = {"got": float(got[k]), "ref": float(ref[k]),
                          "abs_diff": d, "ok": bool(d < tol)}
        else:
            per_key[k] = {"got": got.get(k), "ref": ref.get(k), "ok": False}
    return {"keys_match": bool(keys_ok), "max_abs_diff": worst,
            "per_key": per_key,
            "ok": bool(keys_ok and worst < tol)}


def compare_arm_metrics(got, ref, tol=TOL):
    """One v3.3-style arm metric dict against its frozen counterpart."""
    floats = compare_floats(got, ref, ARM_FLOAT_FIELDS, tol)
    ints = compare_ints(got, ref, ARM_INT_FIELDS)
    strata = compare_float_dict(got["protected_stratum_edit"],
                                ref["protected_stratum_edit"], tol)
    ok = (all(v["ok"] for v in floats.values())
          and all(v["ok"] for v in ints.values()) and strata["ok"])
    return {"floats": floats, "ints": ints,
            "protected_stratum_edit": strata,
            "max_abs_diff": max([v["abs_diff"] for v in floats.values()]
                                + [strata["max_abs_diff"]]),
            "pass": bool(ok)}


def compare_v37_metrics(got, ref, tol=TOL):
    """One v3.7 public metric dict (``_public_metrics``) against frozen."""
    floats = compare_floats(got, ref, V37_FLOAT_FIELDS, tol)
    ints = compare_ints(got, ref, V37_INT_FIELDS)
    fam = compare_float_dict(got["commit_by_family"], ref["commit_by_family"],
                             tol)
    src = compare_float_dict(got["commit_by_source"], ref["commit_by_source"],
                             tol)
    ok = (all(v["ok"] for v in floats.values())
          and all(v["ok"] for v in ints.values()) and fam["ok"] and src["ok"])
    return {"floats": floats, "ints": ints, "commit_by_family": fam,
            "commit_by_source": src,
            "max_abs_diff": max([v["abs_diff"] for v in floats.values()]
                                + [fam["max_abs_diff"], src["max_abs_diff"]]),
            "pass": bool(ok)}


# -- pick serialisation ---------------------------------------------------------


def _pick_key(pick_row):
    if pick_row is None:
        return None
    return {"family": pick_row["family"], "rung": pick_row["rung"],
            "params_key": _pkey(pick_row["params"]),
            "true_repair_gain": float(pick_row["true_repair_gain"]),
            "true_loss": float(pick_row["true_loss"])}


# -- R1: v3.3 unrestricted candidate oracle --------------------------------------


def replay_v33_oracle(real, frozen_arm):
    committed = v33._decisions(real, "oracle")
    met = v33._episode_metrics(real, committed)
    cmp_ = compare_arm_metrics(met, frozen_arm)
    picks = {}
    for uid, got in committed.items():
        picks[uid] = _pick_key(got[0] if got else None)
    n_bns = {}
    by_window = {}
    for r in real:
        by_window.setdefault(r["sample_uid"], []).append(r)
    for uid, rs in by_window.items():
        n_bns[uid] = sum(
            1 for r in rs
            if r["beneficial_and_safe"] and r["family"] in EPISODE_FAMILY_ORDER)
    print(f"[R1 oracle] bcov={met['beneficial_coverage']:.6f} "
          f"gain={met['mean_repair_gain_contaminated']:.6f} "
          f"committed={met['committed']} pass={cmp_['pass']}", flush=True)
    return {"comparison": cmp_, "picks": picks, "n_bns_eligible": n_bns,
            "pass": bool(cmp_["pass"])}


# -- R3: PICS_joint_relabel incumbent ---------------------------------------------

PICS_RECORD_FLOATS = ("true_loss", "true_repair_gain", "before_nmse",
                      "after_nmse", "delta_utility", "struct_distortion",
                      "risk")
PICS_RECORD_EXACT = ("family", "rung", "verdict_reason", "corrupted_hash",
                     "clean_hash", "output_hash", "dataset", "stratum",
                     "true_kind")
PICS_EXPLAIN_FLOATS = ("benefit_score", "harm_score", "harm_spread",
                       "spread_cap")


def replay_pics(real, frozen_arm, frozen_folds, frozen_commits):
    datasets = sorted({r["dataset"] for r in real})
    all_committed = {}
    per_fold = {}
    for test_ds in datasets:
        train, cal, test = v33._split(real, test_ds)
        model = v33._PICSArmX(PICS_JOINT_FEATURES)
        model.fit(train, cal)
        committed = v33._decisions(test, model)
        all_committed.update(committed)
        m = v33._episode_metrics(test, committed)
        cmp_ = compare_arm_metrics(m, frozen_folds[test_ds])
        per_fold[test_ds] = cmp_
        print(f"[R3 pics {test_ds}] bcov={m['beneficial_coverage']:.4f} "
              f"CHR={m['conditional_harm_rate']:.3f} pass={cmp_['pass']}",
              flush=True)
    pooled = v33._episode_metrics(real, all_committed, keep_records=True)
    cmp_pooled = compare_arm_metrics(pooled, frozen_arm)

    # per-window commit records against the frozen ledger
    frozen_by_uid = {c["sample_uid"]: c
                     for c in frozen_commits["all_commits"]}
    got_by_uid = {c["sample_uid"]: c for c in pooled["records"]}
    uids_match = set(frozen_by_uid) == set(got_by_uid)
    rec_mismatch = []
    worst = 0.0
    for uid in sorted(set(frozen_by_uid) & set(got_by_uid)):
        a, b = got_by_uid[uid], frozen_by_uid[uid]
        for f in PICS_RECORD_EXACT:
            fa, fb = a.get(f), b.get(f)
            if f == "output_hash" and (fa is None or fb is None):
                if fa != fb:
                    rec_mismatch.append((uid, f, fa, fb))
            elif fa != fb:
                rec_mismatch.append((uid, f, fa, fb))
        if _pkey(a["params"]) != _pkey(b["params"]):
            rec_mismatch.append((uid, "params", a["params"], b["params"]))
        if int(a["episode_position"]) != int(b["episode_position"]):
            rec_mismatch.append((uid, "episode_position",
                                 a["episode_position"], b["episode_position"]))
        if bool(a["harmful"]) != bool(b["harmful"]):
            rec_mismatch.append((uid, "harmful", a["harmful"], b["harmful"]))
        for f in PICS_RECORD_FLOATS:
            if a.get(f) is None or b.get(f) is None:
                if a.get(f) != b.get(f):
                    rec_mismatch.append((uid, f, a.get(f), b.get(f)))
                continue
            d = abs(float(a[f]) - float(b[f]))
            worst = max(worst, d)
            if d >= TOL:
                rec_mismatch.append((uid, f, a[f], b[f]))
        ea, eb = a.get("decision_detail"), b.get("decision_detail")
        if (ea is None) != (eb is None):
            rec_mismatch.append((uid, "decision_detail presence",
                                 ea is not None, eb is not None))
        elif ea is not None:
            for f in PICS_EXPLAIN_FLOATS:
                d = abs(float(ea[f]) - float(eb[f]))
                worst = max(worst, d)
                if d >= TOL:
                    rec_mismatch.append((uid, "decision_detail." + f,
                                         ea[f], eb[f]))
            ta, tb = ea.get("selected_threshold"), eb.get("selected_threshold")
            if (ta is None) != (tb is None):
                rec_mismatch.append((uid, "selected_threshold presence",
                                     ta, tb))
            elif ta is not None:
                for i, (x, y) in enumerate(zip(ta, tb)):
                    d = abs(float(x) - float(y))
                    worst = max(worst, d)
                    if d >= TOL:
                        rec_mismatch.append(
                            (uid, f"selected_threshold[{i}]", x, y))
    rec_ok = uids_match and not rec_mismatch
    print(f"[R3 pics pooled] bcov={pooled['beneficial_coverage']:.4f} "
          f"CHR={pooled['conditional_harm_rate']:.4f} "
          f"records_match={rec_ok} (worst float diff {worst:.3e})",
          flush=True)
    ok = (cmp_pooled["pass"] and rec_ok
          and all(c["pass"] for c in per_fold.values()))
    return {"pooled": cmp_pooled, "per_fold": per_fold,
            "records": {"uids_match": bool(uids_match),
                        "n_frozen": len(frozen_by_uid),
                        "n_replay": len(got_by_uid),
                        "worst_float_abs_diff": worst,
                        "mismatches": [list(m) for m in rec_mismatch[:50]],
                        "n_mismatches": len(rec_mismatch),
                        "pass": bool(rec_ok)},
            "picks": {uid: _pick_key(got[0] if got else None)
                      for uid, got in all_committed.items()},
            "pass": bool(ok)}


# -- R2: v3.7 constrained oracles --------------------------------------------------


def _compare_v37_oracle(got, ref, tol=TOL):
    """got/ref: {"per_fold": {ds: {...}}, "pooled": {...}}."""
    per_fold = {}
    ok = True
    for ds in ref["per_fold"]:
        g, r = got["per_fold"][ds], ref["per_fold"][ds]
        entry = {"metrics": compare_v37_metrics(g["metrics"], r["metrics"],
                                                tol),
                 "margins": compare_float_dict(g["margins"], r["margins"],
                                               tol),
                 "feasible_match": bool(g["feasible"] == r["feasible"]),
                 "n_configs_match": bool(g["n_configs"] == r["n_configs"])}
        if "weights" in r:
            entry["weights"] = compare_float_dict(g["weights"], r["weights"],
                                                  tol)
            entry["weights_ok"] = entry["weights"]["ok"]
        if "n_feasible" in r:
            entry["n_feasible_match"] = bool(g["n_feasible"]
                                             == r["n_feasible"])
        fold_ok = (entry["metrics"]["pass"] and entry["margins"]["ok"]
                   and entry["feasible_match"] and entry["n_configs_match"]
                   and entry.get("weights_ok", True)
                   and entry.get("n_feasible_match", True))
        entry["pass"] = bool(fold_ok)
        per_fold[ds] = entry
        ok = ok and fold_ok
    pooled = compare_v37_metrics(got["pooled"], ref["pooled"], tol)
    ok = ok and pooled["pass"]
    return {"per_fold": per_fold, "pooled": pooled, "pass": bool(ok)}


def _oracle_global_with_commits(fold_models, eps):
    """Re-drive v37.oracle_global keeping the per-uid commits.

    Uses only frozen v3.7 primitives; metrics must equal
    ``v37.oracle_global``'s own output (asserted by the caller)."""
    pooled_committed = {}
    for test_ds in v37.REAL_SOURCES:
        fm = fold_models[test_ds]
        test_eps = [ep for uid, ep in eps.items()
                    if ep["dataset"] == test_ds]
        blocks = [v37._scored_arrays(sc, "p_vs_keep", "tournament_score")
                  for _, sc in fm["scored_test"]]
        meta = [{"prot": ep["stratum"] in v36.PROTECTED_STRATA,
                 "cont": ep["stratum"] == "contaminated"}
                for ep in test_eps]
        combos, metrics, sel_rows = v37.sweep_margins(blocks, meta)
        best, feasible = v37._pick_best(combos, metrics)
        sel = np.array([r[best] for r in sel_rows])
        _, committed = v37._exact_metrics(sel, blocks, test_eps)
        pooled_committed.update(committed)
    return pooled_committed


def _oracle_mix_with_commits(fold_models, eps):
    """Re-drive v37.oracle_expert_mixture keeping the per-uid commits."""
    pooled_committed = {}
    weights_grid = v37.simplex_grid(5)
    for test_ds in v37.REAL_SOURCES:
        train_sources = [s for s in v37.REAL_SOURCES if s != test_ds]
        experts = v37.fit_source_experts(eps, train_sources)
        test_eps = [ep for uid, ep in eps.items()
                    if ep["dataset"] == test_ds]
        pmat = [v37.expert_scores(experts, train_sources, ep)
                for ep in test_eps]
        meta = [{"prot": ep["stratum"] in v36.PROTECTED_STRATA,
                 "cont": ep["stratum"] == "contaminated"}
                for ep in test_eps]
        best_rec = None
        for wi, w in enumerate(weights_grid):
            wv = np.array(w)
            blocks = []
            for ep, P in zip(test_eps, pmat):
                sc = [{"row": r, "mix": float(P[i] @ wv)}
                      for i, r in enumerate(ep["cands"])]
                blocks.append(v37._scored_arrays(sc, "mix", "mix"))
            combos, metrics, sel_rows = v37.sweep_margins(blocks, meta)
            best, feasible = v37._pick_best(combos, metrics)
            rec_key = (feasible, metrics["bcov"][best],
                       metrics["gain"][best], -metrics["chr"][best], -wi)
            if best_rec is None or rec_key > best_rec[0]:
                best_rec = (rec_key, blocks, combos, best, sel_rows)
        _, blocks, combos, best, sel_rows = best_rec
        sel = np.array([r[best] for r in sel_rows])
        _, committed = v37._exact_metrics(sel, blocks, test_eps)
        pooled_committed.update(committed)
    return pooled_committed


def replay_v37(frozen_v37):
    pairs, rows = v36._load()
    eps = v36._build_episodes(rows)
    v36._EPS = eps
    _, integrity = v36._integrity(pairs, eps)
    for m in integrity:
        print("[integrity]", m, flush=True)

    repro, fold_models = v37.reproduce(pairs, eps)
    out = {"v36_reproduction_pass": bool(repro["pass"]),
           "v36_reproduction_max_abs_diff":
               repro["max_abs_diff_overall"]}
    if not repro["pass"]:
        print("[FATAL] v3.6 reproduction breach; v3.7 oracles void",
              flush=True)
        out["pass"] = False
        out["fatal"] = ("v36 reproduction breach "
                        f"{repro['max_abs_diff_overall']:.3e} >= 1e-9")
        return out, None, None, eps

    og = v37.oracle_global(fold_models, eps)
    om = v37.oracle_expert_mixture(fold_models, eps)
    ref_og = frozen_v37["oracle"]["oracle_target_threshold_global"]
    ref_om = frozen_v37["oracle"]["oracle_target_expert_mixture"]
    cmp_og = _compare_v37_oracle(og, ref_og)
    cmp_om = _compare_v37_oracle(om, ref_om)
    print(f"[R2 oracle-global] bcov={og['pooled']['bcov']:.6f} "
          f"pass={cmp_og['pass']}", flush=True)
    print(f"[R2 oracle-mixture] bcov={om['pooled']['bcov']:.6f} "
          f"pass={cmp_om['pass']}", flush=True)

    # Second code path with per-uid commits; must agree with the first.
    comm_g = _oracle_global_with_commits(fold_models, eps)
    met_g = v36._episode_metrics(comm_g)
    comm_m = _oracle_mix_with_commits(fold_models, eps)
    met_m = v36._episode_metrics(comm_m)
    xcheck_g = compare_v37_metrics(v37._public_metrics(met_g), og["pooled"])
    xcheck_m = compare_v37_metrics(v37._public_metrics(met_m), om["pooled"])
    print(f"[R2 xcheck] global_path2_pass={xcheck_g['pass']} "
          f"mixture_path2_pass={xcheck_m['pass']}", flush=True)

    out.update({
        "oracle_target_threshold_global": cmp_og,
        "oracle_target_expert_mixture": cmp_om,
        "second_path_xcheck": {"global": xcheck_g,
                               "mixture": xcheck_m},
        "pass": bool(cmp_og["pass"] and cmp_om["pass"]
                     and xcheck_g["pass"] and xcheck_m["pass"]),
    })
    return out, comm_g, comm_m, eps


# -- alignment ---------------------------------------------------------------------


def build_alignment(real, picks_oracle, comm_g, comm_m, picks_pics, n_bns):
    """Per-sample_uid alignment of the four decision rules."""
    by_window = {}
    for r in real:
        by_window.setdefault(r["sample_uid"], []).append(r)
    rows = []
    for uid in sorted(by_window):
        rs = by_window[uid]
        w = rs[0]
        g = comm_g.get(uid)
        m = comm_m.get(uid)
        rows.append({
            "sample_uid": uid,
            "dataset": w["dataset"],
            "stratum": w["stratum"],
            "true_kind": w["true_kind"],
            "n_candidates": len(rs),
            "n_beneficial_and_safe_eligible": n_bns.get(uid, 0),
            "oracle_unrestricted": picks_oracle.get(uid),
            "v37_global": _pick_key(g[0] if g else None),
            "v37_expert_mixture": _pick_key(m[0] if m else None),
            "pics_incumbent": picks_pics.get(uid),
        })
    return rows


def alignment_summary(align):
    def _key(e):
        return None if e is None else (
            e["family"], e["rung"], e["params_key"])

    n = len(align)
    su = {}
    for arm in ("oracle_unrestricted", "v37_global", "v37_expert_mixture",
                "pics_incumbent"):
        su[arm] = sum(1 for r in align if r[arm] is not None)
    same_go = sum(1 for r in align
                  if _key(r["oracle_unrestricted"]) == _key(r["v37_global"]))
    same_mo = sum(1 for r in align
                  if _key(r["oracle_unrestricted"])
                  == _key(r["v37_expert_mixture"]))
    same_po = sum(1 for r in align
                  if _key(r["oracle_unrestricted"])
                  == _key(r["pics_incumbent"]))
    # oracle gain mass the constrained oracles leave on the table
    missed_g = sum(r["oracle_unrestricted"]["true_repair_gain"]
                   for r in align
                   if r["oracle_unrestricted"] and r["v37_global"] is None)
    missed_m = sum(r["oracle_unrestricted"]["true_repair_gain"]
                   for r in align
                   if r["oracle_unrestricted"]
                   and r["v37_expert_mixture"] is None)
    total = sum(r["oracle_unrestricted"]["true_repair_gain"]
                for r in align if r["oracle_unrestricted"])
    return {
        "n_windows": n,
        "commits_by_arm": su,
        "identical_pick_windows": {
            "oracle_vs_v37_global": same_go,
            "oracle_vs_v37_mixture": same_mo,
            "oracle_vs_pics": same_po,
        },
        "oracle_gain_mass": {
            "total": total,
            "uncaptured_by_v37_global": missed_g,
            "uncaptured_by_v37_mixture": missed_m,
            "frac_uncaptured_global": missed_g / total if total else None,
            "frac_uncaptured_mixture": missed_m / total if total else None,
        },
    }


EXPLANATION = {
    "candidate_set": (
        "R1 (v3.3 unrestricted oracle): the whole per-window candidate pool "
        "with RESEGMENT closed (family in EPISODE_FAMILY_ORDER = DENOISE / "
        "DESPIKE / IMPUTE); no score ordering and no structural veto -- any "
        "beneficial_and_safe candidate is reachable. "
        "R2 (v3.7 constrained oracles): the same underlying pool, but every "
        "candidate is first filtered by the frozen v2 structural veto and "
        "then forced into a frozen ordering -- the v3.6 PAIR_absolute/logreg "
        "tournament score (threshold_global) or a convex mixture of five "
        "training-source experts (expert_mixture). Only the top-ranked "
        "candidate that clears its family threshold can ever commit "
        "(first-commit replay)."),
    "available_labels": (
        "Both use held-out ground truth, at different action points: R1 uses "
        "the labels to CHOOSE THE CANDIDATE (max true_repair_gain among "
        "beneficial_and_safe, per window). R2 uses the labels only to CHOOSE "
        "THE CALIBRATION -- the per-family threshold on the fixed margin "
        "grid {0.00..0.40} and, for the mixture, the simplex weight vector "
        "(70 weight vectors, step 0.25). The candidate ranking itself never "
        "sees held-out labels."),
    "constraints": (
        "R1: none -- by construction CHR=0, damage=0, pme=0. "
        "R2: per held-out fold the chosen configuration must satisfy "
        "CHR <= 0.10, pme <= 0.0055, damage <= 0.0402 (the frozen incumbent "
        "damage); feasible-first selection, then max bcov, max gain, min "
        "CHR, lowest grid index."),
    "reading": (
        "The gap between bcov 0.6591 (R1) and 0.0409/0.1795 (R2) is "
        "therefore not a candidate-pool ceiling: it is the cost of freezing "
        "the PAIR score ordering and only letting labels move thresholds / "
        "expert weights on a fixed grid. v3.7's conclusion is corrected "
        "accordingly: the frozen-PAIR-ranking route is excluded; redefining "
        "candidate semantics and constructing identifiable high-precision "
        "candidates is not."),
}


# -- main -------------------------------------------------------------------------


def main():
    t0 = time.time()
    frozen_v33 = json.load(FROZEN_V33.open(encoding="utf-8"))
    frozen_v33_commits = json.load(FROZEN_V33_COMMITS.open(encoding="utf-8"))
    frozen_v37 = json.load(FROZEN_V37.open(encoding="utf-8"))
    rows = v33._load_rows(str(ROWS_PATH))
    real = [r for r in rows if not r["dataset"].startswith("ood:")]
    print(f"{len(rows)} candidates, {len(real)} real "
          f"({len({r['sample_uid'] for r in real})} windows)", flush=True)

    r1 = replay_v33_oracle(real, frozen_v33["arms"]["oracle_relabel"])
    r3 = replay_pics(real, frozen_v33["arms"]["PICS_joint_relabel"],
                     frozen_v33["folds"]["PICS_joint_relabel"],
                     frozen_v33_commits["PICS_joint_relabel"])
    r2, comm_g, comm_m, eps = replay_v37(frozen_v37)

    align = []
    if r2.get("pass") and comm_g is not None:
        align = build_alignment(real, r1["picks"], comm_g, comm_m,
                                r3["picks"], r1["n_bns_eligible"])
    summary = alignment_summary(align) if align else None

    out = {
        "phase": "v3.8 Phase 0 Part A: exact replay of the three reference "
                 "arms (docs/v3_8_fact_preregistration.md §1, §3)",
        "tolerance": TOL,
        "input_hashes": {
            "v33_training_data": _sha256(ROWS_PATH),
            "v33_clean_rerun": _sha256(FROZEN_V33),
            "v33_clean_rerun_harmful": _sha256(FROZEN_V33_COMMITS),
            "v37_shift_headroom": _sha256(FROZEN_V37),
            "v36_pair_probe": _sha256(v36.OUT_JSON),
            "v36_pair_predictions": _sha256(v36.OUT_PRED),
            "v36_pair_dataset": _sha256(v36.PAIR_PATH),
        },
        "code_hashes": {
            "experiments/v33_compare_arms.py": _sha256(
                ROOT / "experiments" / "v33_compare_arms.py"),
            "experiments/v36_pair_ranker_probe.py": _sha256(
                ROOT / "experiments" / "v36_pair_ranker_probe.py"),
            "experiments/v37_shift_headroom.py": _sha256(
                ROOT / "experiments" / "v37_shift_headroom.py"),
            "experiments/v38_oracle_replay.py": _sha256(
                Path(__file__).resolve()),
        },
        "r1_v33_unrestricted_oracle": {
            "pass": r1["pass"],
            "headline": {
                "bcov": frozen_v33["arms"]["oracle_relabel"]
                ["beneficial_coverage"],
                "gain": frozen_v33["arms"]["oracle_relabel"]
                ["mean_repair_gain_contaminated"],
                "chr": frozen_v33["arms"]["oracle_relabel"]
                ["conditional_harm_rate"],
                "damage": frozen_v33["arms"]["oracle_relabel"]["damage"],
                "pme": frozen_v33["arms"]["oracle_relabel"]
                ["protected_mis_edit_rate"],
            },
            "comparison": r1["comparison"],
        },
        "r2_v37_constrained_oracles": r2,
        "r3_pics_incumbent": {
            "pass": r3["pass"],
            "headline": {
                "bcov": frozen_v33["arms"]["PICS_joint_relabel"]
                ["beneficial_coverage"],
                "gain": frozen_v33["arms"]["PICS_joint_relabel"]
                ["mean_repair_gain_contaminated"],
                "chr": frozen_v33["arms"]["PICS_joint_relabel"]
                ["conditional_harm_rate"],
                "damage": frozen_v33["arms"]["PICS_joint_relabel"]["damage"],
                "pme": frozen_v33["arms"]["PICS_joint_relabel"]
                ["protected_mis_edit_rate"],
            },
            "pooled": r3["pooled"],
            "per_fold": r3["per_fold"],
            "records": r3["records"],
        },
        "oracle_difference_explanation": EXPLANATION,
        "alignment_summary": summary,
        "alignment": align,
        "runtime_sec": time.time() - t0,
    }
    all_pass = bool(r1["pass"] and r2.get("pass") and r3["pass"])
    out["all_replays_pass"] = all_pass
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)
    print(f"[done] all_replays_pass={all_pass} "
          f"runtime={time.time() - t0:.1f}s -> {OUT.name}", flush=True)
    print("___V38_ORACLE_REPLAY_DONE___", flush=True)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
