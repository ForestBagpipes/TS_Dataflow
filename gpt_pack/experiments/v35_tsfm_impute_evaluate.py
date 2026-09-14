"""v3.5 Phase 2: TSFM_RECONSTRUCT_IMPUTE gate evaluation (frozen records only).

Pre-registered in ``docs/v3_5_acv_preregistration.md`` §6. Runs only after
``results/v35_tsfm_impute_records.jsonl`` is frozen. Every arm output is
recomputed and must re-verify hash-identical to the frozen record BEFORE any
evaluation field is attached; a single mismatch aborts the evaluation.

Outcome fields follow the v3.3 canonical convention exactly:
``v33_labels.compute_action_labels`` with family IMPUTE -- KEEP
counterfactual = the probe-materialised series, uncentered finite-mask NMSE
against the pristine reference, damage = max(worse_binary, discard_share),
ALPHA = 0.03. Nothing is re-implemented here.

Operator green light (§6, ALL required):
  1. paired harmful rate vs the current IMPUTE candidate: relative
     reduction >= 25%;
  2. beneficial_and_safe rate not below the current candidate's;
  3. median true loss strictly lower;
  4. direction consistent (tsfm harm rate <= candidate harm rate) on at
     least 3 real sources (datasets not prefixed 'ood:');
  5. no observed finite value modified (structural; asserted at build and
     re-asserted here);
  6. oracle window coverage (share of routed-IMPUTE windows with at least
     one beneficial_and_safe arm among the paired actions) increases by
     >= 0.03 when the tsfm arm joins the candidate arms, OR coverage is
     unchanged while the harmful rate clearly drops (relative reduction
     >= 25%, the same bar as gate 1).

Usage:
    python experiments/v35_tsfm_impute_evaluate.py --device cuda
"""

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from v33_labels import compute_action_labels, hash_array  # noqa: E402
import v35_tsfm_impute_probe as probe2  # noqa: E402
from introact_ts.actions import Action, apply_action  # noqa: E402
from introact_ts.backends import make_backend  # noqa: E402

ALPHA = 0.03
GATE1_MIN_REL_REDUCTION = 0.25
GATE4_MIN_SOURCES = 3
GATE6_MIN_COV_GAIN = 0.03

ARMS = ("keep", "default", "candidate", "tsfm")


def _labels_for_arms(x, clean, arms_series, touched):
    """compute_action_labels for every arm of one window (family IMPUTE)."""
    out = {}
    for arm, y in arms_series.items():
        lab = compute_action_labels("IMPUTE", x, y, clean,
                                    touched=touched.get(arm), params={})
        out[arm] = {k: lab[k] for k in
                    ("before_nmse", "after_nmse", "true_loss",
                     "true_repair_gain", "beneficial", "safe", "harmful",
                     "beneficial_and_safe")}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default=str(
        ROOT / "results" / "v35_tsfm_impute_records.jsonl"))
    ap.add_argument("--manifest",
                    default=str(ROOT / "results" / "p0_corpus_manifest_a.json"))
    ap.add_argument("--out", default=str(
        ROOT / "results" / "v35_tsfm_impute_probe.json"))
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n-corpus", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    args = ap.parse_args()

    t0 = time.time()
    recs = [json.loads(l) for l in open(args.records, encoding="utf-8")]
    records_sha = hashlib.sha256(Path(args.records).read_bytes()).hexdigest()
    print(f"{len(recs)} frozen records (sha256 {records_sha[:16]}...)",
          flush=True)

    # Rebuild the corpus; this stage MAY read the pristine reference (it is
    # the evaluation namespace), keyed to the same windows by corrupted hash.
    from build_calibration import build as build_calibration
    windows, _ = build_calibration(n=args.n_corpus, seed=args.seed,
                                   source="mixed", verbose=False)
    by_hash = defaultdict(list)
    for w in windows:
        by_hash[hash_array(np.asarray(w.series, dtype=np.float64))].append(w)
    uid_win = {}
    for r in recs:
        uid = r["sample_uid"]
        if uid in uid_win:
            continue
        cands = by_hash.get(r["corrupted_hash"], [])
        if len(cands) != 1:
            raise SystemExit(f"window matching failed for {uid}")
        uid_win[uid] = cands[0]

    # Recompute every arm and re-verify the frozen hashes BEFORE any outcome
    # field is computed. The tsfm arm is rebuilt with the same proposer.
    proposer = make_backend(probe2.PROPOSER_SPEC, device=args.device)
    by_uid = defaultdict(list)
    for r in recs:
        by_uid[r["sample_uid"]].append(r)
    uids = sorted(by_uid)

    arms_series, labels_by_uid = {}, {}
    n_finite_violations = 0
    for uid in uids:
        w = uid_win[uid]
        x = np.asarray(w.series, dtype=np.float64)
        clean = np.asarray(w.clean_series, dtype=np.float64)
        rec0 = by_uid[uid][0]
        y_keep = probe2.materialize_for_probe(x)
        out_def = apply_action(x, Action.IMPUTE,
                               **probe2.DEFAULT_IMPUTE_PARAMS)
        y_tsfm, spans = probe2.tsfm_reconstruct_impute(proposer, x)
        n_finite_violations += int(
            not np.array_equal(y_tsfm[np.isfinite(x)], x[np.isfinite(x)]))
        if hash_array(y_keep) != rec0["arm_hashes"]["keep"] \
                or hash_array(out_def.series) != rec0["arm_hashes"]["default"] \
                or hash_array(y_tsfm) != rec0["arm_hashes"]["tsfm"]:
            raise SystemExit(f"frozen arm hash mismatch on {uid}; refusing "
                             f"to attach outcome fields")
        arms_series[uid] = {"keep": y_keep, "default": out_def.series,
                            "tsfm": y_tsfm}
        labels_by_uid[uid] = {"keep": None, "default": None, "tsfm": None}
        nan_mask = ~np.isfinite(x)
        partial = _labels_for_arms(
            x, clean,
            {"keep": y_keep, "default": out_def.series, "tsfm": y_tsfm},
            {"keep": None, "default": out_def.touched, "tsfm": nan_mask})
        labels_by_uid[uid].update(partial)
    print(f"re-verified {len(uids)} windows x keep/default/tsfm arms; "
          f"observed-finite violations: {n_finite_violations}", flush=True)

    # Per candidate row: re-run its own operator, verify, label, pair.
    rows = []
    for uid in uids:
        w = uid_win[uid]
        x = np.asarray(w.series, dtype=np.float64)
        clean = np.asarray(w.clean_series, dtype=np.float64)
        for r in sorted(by_uid[uid],
                        key=lambda r: (r["rung"], json.dumps(r["params"],
                                                             sort_keys=True))):
            out = apply_action(x, Action.IMPUTE, **r["params"])
            if hash_array(out.series) != r["arm_hashes"]["candidate"]:
                raise SystemExit(f"candidate arm hash mismatch on {uid}")
            lab = compute_action_labels("IMPUTE", x, out.series, clean,
                                        touched=out.touched, params={})
            rows.append({
                "sample_uid": uid, "dataset": r["dataset"],
                "stratum": r["stratum"], "rung": r["rung"],
                "params": r["params"],
                "candidate": {k: lab[k] for k in
                              ("true_loss", "true_repair_gain", "harmful",
                               "beneficial_and_safe", "before_nmse",
                               "after_nmse")},
                "tsfm": labels_by_uid[uid]["tsfm"],
                "default": labels_by_uid[uid]["default"],
                "keep": labels_by_uid[uid]["keep"],
            })
    print(f"paired {len(rows)} candidate rows", flush=True)

    # -- gates ---------------------------------------------------------------
    cand_harm = np.asarray([r["candidate"]["harmful"] for r in rows])
    tsfm_harm = np.asarray([r["tsfm"]["harmful"] for r in rows])
    cand_bs = np.asarray([r["candidate"]["beneficial_and_safe"] for r in rows])
    tsfm_bs = np.asarray([r["tsfm"]["beneficial_and_safe"] for r in rows])
    cand_loss = np.asarray([r["candidate"]["true_loss"] for r in rows])
    tsfm_loss = np.asarray([r["tsfm"]["true_loss"] for r in rows])

    harm_c = float(cand_harm.mean())
    harm_t = float(tsfm_harm.mean())
    rel_red = (harm_c - harm_t) / harm_c if harm_c > 0 else 0.0
    g1 = rel_red >= GATE1_MIN_REL_REDUCTION
    g2 = float(tsfm_bs.mean()) >= float(cand_bs.mean())
    med_c, med_t = float(np.median(cand_loss)), float(np.median(tsfm_loss))
    g3 = med_t < med_c

    real_sources = sorted({r["dataset"] for r in rows
                           if not r["dataset"].startswith("ood:")})
    per_source = {}
    for s in real_sources:
        idx = [i for i, r in enumerate(rows) if r["dataset"] == s]
        hc = float(cand_harm[idx].mean())
        ht = float(tsfm_harm[idx].mean())
        per_source[s] = {"n_rows": len(idx), "harm_rate_candidate": hc,
                         "harm_rate_tsfm": ht,
                         "direction_ok": bool(ht <= hc + 1e-12)}
    n_dir_ok = sum(v["direction_ok"] for v in per_source.values())
    g4 = n_dir_ok >= GATE4_MIN_SOURCES

    g5 = n_finite_violations == 0

    win_cand_bs = defaultdict(bool)
    win_tsfm_bs = defaultdict(bool)
    win_harm = defaultdict(list)
    for r in rows:
        u = r["sample_uid"]
        win_cand_bs[u] = win_cand_bs[u] or r["candidate"]["beneficial_and_safe"] > 0.5
        win_tsfm_bs[u] = win_tsfm_bs[u] or r["tsfm"]["beneficial_and_safe"] > 0.5
    cov_old = float(np.mean([int(v) for v in win_cand_bs.values()]))
    cov_new = float(np.mean([int(win_cand_bs[u] or win_tsfm_bs[u])
                             for u in win_cand_bs]))
    cov_gain = cov_new - cov_old
    g6 = cov_gain >= GATE6_MIN_COV_GAIN or (
        abs(cov_gain) < 1e-12 and rel_red >= GATE1_MIN_REL_REDUCTION)

    gates = {
        "gate1_harm_rel_reduction": {
            "pass": bool(g1), "harm_rate_candidate": harm_c,
            "harm_rate_tsfm": harm_t, "relative_reduction": rel_red,
            "threshold": GATE1_MIN_REL_REDUCTION},
        "gate2_bs_rate_not_below": {
            "pass": bool(g2), "bs_rate_candidate": float(cand_bs.mean()),
            "bs_rate_tsfm": float(tsfm_bs.mean())},
        "gate3_median_true_loss_down": {
            "pass": bool(g3), "median_candidate": med_c,
            "median_tsfm": med_t},
        "gate4_source_direction": {
            "pass": bool(g4), "n_sources_direction_ok": n_dir_ok,
            "threshold": GATE4_MIN_SOURCES, "per_source": per_source},
        "gate5_observed_finite_untouched": {
            "pass": bool(g5), "violations": n_finite_violations},
        "gate6_oracle_coverage": {
            "pass": bool(g6), "coverage_candidate_only": cov_old,
            "coverage_with_tsfm": cov_new, "coverage_gain": cov_gain,
            "threshold_gain": GATE6_MIN_COV_GAIN,
            "fallback": "equal coverage with harmful-rate relative "
                        "reduction >= 25%"},
    }
    verdict = "green" if all(g["pass"] for g in gates.values()) else "not_green"

    # Descriptive arm statistics (all four arms, pooled over rows/windows).
    arm_stats = {}
    for arm in ARMS:
        if arm == "candidate":
            sub = [r["candidate"] for r in rows]
        else:
            sub = [labels_by_uid[r["sample_uid"]][arm] for r in rows]
        arm_stats[arm] = {
            "harmful_rate": float(np.mean([s["harmful"] for s in sub])),
            "bs_rate": float(np.mean([s["beneficial_and_safe"] for s in sub])),
            "median_true_loss": float(np.median([s["true_loss"]
                                                 for s in sub])),
            "mean_after_nmse": float(np.mean([s["after_nmse"]
                                              for s in sub])),
        }

    # Verifier disagreement summary from the frozen records.
    gaps = defaultdict(list)
    for r in recs:
        for spec, g in r["verifier_disagreement"].items():
            if g["mean_abs_gap"] is not None:
                gaps[spec].append(g["mean_abs_gap"])
    disagreement = {s: {"n_windows": len(v),
                        "mean": float(np.mean(v)),
                        "median": float(np.median(v))}
                    for s, v in gaps.items()}

    summary = {
        "phase": "v3.5 Phase 2 TSFM_RECONSTRUCT_IMPUTE gate evaluation",
        "preregistration": "docs/v3_5_acv_preregistration.md §3, §6",
        "records_file": args.records,
        "records_sha256": records_sha,
        "n_records": len(recs),
        "n_windows": len(uids),
        "model_status": recs[0]["model"] if recs else None,
        "config_hash": recs[0]["config_hash"] if recs else None,
        "arm_stats": arm_stats,
        "verifier_disagreement": disagreement,
        "oracle_window_coverage": {
            "definition": "share of routed-IMPUTE windows with >=1 "
                          "beneficial_and_safe arm",
            "candidate_only": cov_old, "with_tsfm": cov_new},
        "gates": gates,
        "verdict": verdict,
        "elapsed_seconds": time.time() - t0,
    }
    Path(args.out).write_text(json.dumps(summary, indent=1, default=float),
                              encoding="utf-8")
    out_hash = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
    print(json.dumps({"gates": {k: v["pass"] for k, v in gates.items()},
                      "verdict": verdict,
                      "probe_json_sha256": out_hash}, indent=1))
    print(f"___V35_TSFM_IMPUTE_EVALUATE_DONE___ wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
