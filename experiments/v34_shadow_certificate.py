"""v3.4 Phase 2: Shadow Intervention Certificate signal probe.

Pre-registered in ``docs/v3_4_scrc_pics_preregistration.md`` §2.1 and §6.
IMPUTE's real missing targets are unobservable at deployment, so reliability
of a candidate imputation operator on the *current* window is measured on
pseudo-gaps instead: hide observed values whose geometry matches the window's
real missing evidence, let the candidate method fill them, and score the fill
against the values that were hidden -- those are known.

Ground-truth discipline: the certificate path (everything from
``evidence_mask`` down to ``certify_candidate``) receives only the corrupted
series, the sample_uid, and the operator params. Labels from the candidate
table are attached afterwards, under ``eval_labels``, and read only by
``evaluate`` (the offline scoring namespace).

Error definition (frozen here, per pre-registration "canonical NMSE or
per-point absolute error, pick one"): a trial's error is the **canonical
uncentered finite-mask NMSE restricted to the pseudo-gap points**,

    err = mean((pred - true) ** 2) / ref_var_observed

where ``ref_var_observed`` is ``metrics_common.ref_var`` of the window's
observed evidence values (median-centred variance of the finite, non-missing
points), computed once per window. If ``ref_var_observed < 1e-12`` the raw
mean squared error is used, mirroring ``metrics_common.canonical_nmse``.
The KEEP baseline for the same pseudo-gap is ``materialize_for_probe`` of the
shadowed series -- exactly what the frozen TSFM would see unedited -- scored
with the same formula.

Primary pre-registered ranking feature: ``shadow_gain_mean`` (KEEP error minus
candidate error, averaged over valid trials). For ranking, the harm-suspicion
score is ``-shadow_gain_mean``; candidates with ``shadow_support == 0``
(insufficient observation to run >= 2 valid trials, abstained by the
certificate) are ranked as most suspicious via a sentinel above every finite
score. All other shadow features are report-only.

Usage:
    python experiments/v34_shadow_certificate.py --n-jobs 32
"""

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from metrics_common import ref_var  # noqa: E402
from v33_labels import hash_array  # noqa: E402
from introact_ts.actions import (  # noqa: E402
    Action, apply_action, missing_mask, _mask_runs,
)
from introact_ts.probe import materialize_for_probe  # noqa: E402

# -- frozen certificate constants (pre-registered, do not tune) ---------------

#: Shadow masks per sample_uid.
N_REPLICAS = 3
#: Smallest min_run any IMPUTE candidate uses; the evidence mask is computed
#: at this sensitivity so it covers every candidate's fill target.
EVIDENCE_MIN_RUN = 8
#: An evidence run of at least this length counts towards block geometry.
BLOCK_MIN_RUN = 4
#: Observed points kept between a pseudo-gap and the nearest evidence/run edge.
CLEARANCE = 8
#: Pseudo-gap block length clip, and scattered-point count clip.
BLOCK_LEN_CLIP = (4, 32)
SCATTER_K_CLIP = (4, 32)
#: Block length when the window shows no missing evidence at all.
DEFAULT_BLOCK_LEN = 8
#: shadow_support = 1 requires at least this many valid trials.
MIN_VALID_TRIALS = 2
#: A per-source recall gate applies only to sources with at least this many
#: harmful accepted IMPUTE commits (pre-registered minimum sample standard).
MIN_HARMFUL_FOR_SOURCE_GATE = 5
#: Gate 2 margin and gate 3 working-point constraint.
AUPRC_MIN_IMPROVEMENT = 0.05
BS_FALSE_REJECT_MAX = 0.20
GATE1_AUROC_MIN = 0.75
GATE3_RECALL_MIN = 0.70
GATE3_SOURCE_RECALL_MIN = 0.50
GATE4_COVERAGE_MIN = 0.90

SOURCE_GROUPS = ("US Term Structure", "ETTm1", "ETTh2")


def source_group(dataset: str) -> str:
    return dataset if dataset in SOURCE_GROUPS else "other"


# -- certificate path (corrupted series + uid + params only) -------------------


def shadow_seed(sample_uid: str, replica: int) -> np.random.Generator:
    """Deterministic per-(uid, replica) generator from a fixed hash seed."""
    digest = hashlib.sha256(
        f"{sample_uid}|shadow|{replica}".encode("utf-8")).digest()
    ss = np.random.SeedSequence(int.from_bytes(digest[:8], "little"))
    return np.random.default_rng(ss)


def evidence_mask(series: np.ndarray) -> np.ndarray:
    """Real missing evidence: NaN plus stuck-sensor runs, NaN-layout only."""
    x = np.asarray(series, dtype=np.float64)
    return missing_mask(x, min_run=EVIDENCE_MIN_RUN)


def geometry_of(series: np.ndarray) -> str:
    """'block' when the missing evidence is dominated by contiguous runs of
    >= BLOCK_MIN_RUN points, else 'scattered'. Inferred purely from where the
    evidence sits; an evidence-free window defaults to 'block'."""
    ev = evidence_mask(series)
    if not ev.any():
        return "block"
    block_pts = sum(hi - lo for lo, hi in _mask_runs(ev)
                    if hi - lo >= BLOCK_MIN_RUN)
    return "block" if 2 * block_pts >= int(ev.sum()) else "scattered"


def make_shadow_mask(sample_uid: str, series: np.ndarray,
                     replica: int) -> np.ndarray:
    """One deterministic pseudo-gap mask, or None when it cannot be placed.

    The mask only ever marks observed (finite, non-evidence) positions, keeps
    CLEARANCE observed points between itself and any evidence or run edge, and
    is a contiguous block or a scattered point set depending on the window's
    evidence geometry.
    """
    x = np.asarray(series, dtype=np.float64)
    T = len(x)
    ev = evidence_mask(x)
    observed = np.isfinite(x) & ~ev
    rng = shadow_seed(sample_uid, replica)
    mask = np.zeros(T, dtype=bool)

    if geometry_of(x) == "block":
        runs = [(lo, hi) for lo, hi in _mask_runs(ev)
                if hi - lo >= BLOCK_MIN_RUN]
        if runs:
            L = int(np.median([hi - lo for lo, hi in runs]))
            L = int(min(max(L, BLOCK_LEN_CLIP[0]), BLOCK_LEN_CLIP[1]))
        else:
            L = DEFAULT_BLOCK_LEN
        eligible = [(lo, hi) for lo, hi in _mask_runs(observed)
                    if hi - lo >= L + 2 * CLEARANCE]
        if not eligible:
            return None
        lo, hi = eligible[int(rng.integers(len(eligible)))]
        span = hi - lo - 2 * CLEARANCE - L + 1
        start = lo + CLEARANCE + int(rng.integers(span))
        mask[start:start + L] = True
    else:
        k = int(min(max(int(ev.sum()), SCATTER_K_CLIP[0]), SCATTER_K_CLIP[1]))
        eligible = np.flatnonzero(observed)
        if len(eligible) < k:
            return None
        mask[rng.choice(eligible, size=k, replace=False)] = True
    return mask


def shadow_masks(sample_uid: str, series: np.ndarray) -> list:
    """The N_REPLICAS deterministic masks for one window (None if unplaceable)."""
    return [make_shadow_mask(sample_uid, series, r) for r in range(N_REPLICAS)]


def certificate_operator(series: np.ndarray, params: dict):
    """The candidate IMPUTE operator, called through the production dispatch.

    This is by construction the same code path as the formal IMPUTE action;
    ``tests/test_shadow_certificate.py`` proves the outputs agree value by
    value, and the main run re-checks the output hash of every candidate
    against the frozen candidate table.
    """
    return apply_action(np.asarray(series, dtype=np.float64),
                        Action.IMPUTE, **params)


def observed_ref_var(series: np.ndarray) -> float:
    """Median-centred variance of the window's observed evidence values."""
    x = np.asarray(series, dtype=np.float64)
    obs = x[np.isfinite(x) & ~evidence_mask(x)]
    if len(obs) < 2:
        return float("nan")
    return ref_var(obs)


def _trial_error(pred: np.ndarray, true: np.ndarray, rv: float) -> float:
    """Canonical uncentered finite-mask NMSE on the pseudo-gap points."""
    d = pred - true
    finite = np.isfinite(d)
    if not finite.any():
        return float("nan")
    v = float(np.mean(d[finite] ** 2))
    return v / rv if np.isfinite(rv) and rv >= 1e-12 else v


def run_trial(series: np.ndarray, mask: np.ndarray, params: dict,
              rv: float) -> dict:
    """One shadow trial: hide, impute with the candidate method, score.

    A trial is valid only when the mask exists, the operator stays applicable
    on the shadowed series, and every hidden point comes back finite.
    """
    if mask is None or not mask.any():
        return {"valid": False, "reason": "no_mask"}
    x = np.asarray(series, dtype=np.float64)
    xs = x.copy()
    xs[mask] = np.nan
    true = x[mask]

    out = certificate_operator(xs, params)
    if not out.applicable:
        return {"valid": False, "reason": "operator_not_applicable"}
    pred = np.asarray(out.series, dtype=np.float64)[mask]
    if not np.isfinite(pred).all():
        return {"valid": False, "reason": "nonfinite_fill"}

    keep = materialize_for_probe(xs)[mask]
    cand_err = _trial_error(pred, true, rv)
    keep_err = _trial_error(keep, true, rv)
    return {
        "valid": True,
        "candidate_error": cand_err,
        "keep_error": keep_err,
        "gain": keep_err - cand_err,
        "operator_output_hash": hash_array(out.series),
    }


def certify_candidate(sample_uid: str, series: np.ndarray, params: dict,
                      masks: list = None, rv: float = None) -> dict:
    """All shadow features for one IMPUTE candidate on one window."""
    x = np.asarray(series, dtype=np.float64)
    masks = shadow_masks(sample_uid, x) if masks is None else masks
    rv = observed_ref_var(x) if rv is None else rv

    trials = []
    for r, mask in enumerate(masks):
        t = run_trial(x, mask, params, rv)
        t["replica"] = r
        t["mask_hash"] = (hashlib.sha256(mask.tobytes()).hexdigest()
                          if mask is not None else None)
        trials.append(t)

    valid = [t for t in trials if t["valid"]]
    ce = np.asarray([t["candidate_error"] for t in valid], dtype=np.float64)
    ke = np.asarray([t["keep_error"] for t in valid], dtype=np.float64)
    gains = np.asarray([t["gain"] for t in valid], dtype=np.float64)
    n = len(valid)

    features = {
        "shadow_valid_trials": n,
        "shadow_candidate_error_mean": float(ce.mean()) if n else None,
        "shadow_candidate_error_q90":
            float(np.percentile(ce, 90)) if n else None,
        "shadow_candidate_error_std": float(ce.std()) if n else None,
        "shadow_keep_error_mean": float(ke.mean()) if n else None,
        "shadow_gain_mean": float(gains.mean()) if n else None,
        "shadow_gain_worst": float(gains.min()) if n else None,
        # Dispersion of the per-trial gain: coefficient of variation,
        # std / (|mean| + eps). Lower = the operator helps (or hurts)
        # consistently across pseudo-gap placements. None below 2 trials.
        "shadow_stability": (float(gains.std()
                                   / (abs(gains.mean()) + 1e-8))
                             if n >= 2 else None),
        "shadow_support": 1 if n >= MIN_VALID_TRIALS else 0,
    }
    return {"features": features, "trials": trials,
            "geometry": geometry_of(x),
            "evidence_n": int(evidence_mask(x).sum()),
            "ref_var_observed": float(rv) if np.isfinite(rv) else None}


def _certify_uid(task) -> list:
    """Certify every candidate of one window. Top-level for pickling."""
    sample_uid, series, params_list = task
    x = np.asarray(series, dtype=np.float64)
    masks = shadow_masks(sample_uid, x)
    rv = observed_ref_var(x)
    out = []
    for params in params_list:
        rec = certify_candidate(sample_uid, x, params, masks=masks, rv=rv)
        formal = certificate_operator(x, params)
        rec["formal_output_hash"] = (
            hash_array(formal.series) if formal.applicable else None)
        out.append(rec)
    return out


# -- evaluation namespace (labels allowed here) ---------------------------------


def _params_key(params: dict) -> str:
    return json.dumps(params, sort_keys=True)


def harm_suspicion_scores(recs: list) -> np.ndarray:
    """Primary pre-registered ranking score: -shadow_gain_mean, with
    abstained (shadow_support == 0) candidates sent above every finite score.
    """
    finite = [-r["features"]["shadow_gain_mean"]
              for r in recs if r["features"]["shadow_support"] == 1]
    sentinel = (max(finite) + 1.0) if finite else 1.0
    return np.asarray([
        -r["features"]["shadow_gain_mean"]
        if r["features"]["shadow_support"] == 1 else sentinel
        for r in recs], dtype=np.float64)


def _working_point(scores: np.ndarray, harmful: np.ndarray,
                   bs: np.ndarray) -> dict:
    """Loosest rejection threshold with beneficial_and_safe false-reject <= 20%.

    Reject = certificate fails = score >= t (the abstain sentinel included).
    Among feasible thresholds pick the one maximising harmful recall; ties
    break towards fewer rejections (larger t). t = inf rejects nobody.
    """
    cand = sorted(set(float(s) for s in scores)) + [float("inf")]
    best = None
    for t in cand:
        rej = scores >= t
        frr = float(np.mean(rej[bs])) if bs.any() else 0.0
        if frr > BS_FALSE_REJECT_MAX + 1e-12:
            continue
        rec = float(np.mean(rej[harmful])) if harmful.any() else 0.0
        key = (rec, t)
        if best is None or key > best[0]:
            best = (key, t, rej, frr, rec)
    _, t, rej, frr, rec = best
    return {"threshold": t, "reject": rej, "bs_false_reject_rate": frr,
            "harmful_recall": rec}


def evaluate(records: list, commits: list) -> dict:
    """Pre-registered signal gates on the PICS-accepted IMPUTE population.

    ``commits`` are the PICS_joint_relabel first-commit IMPUTE records from
    ``results/v33_harmful_commits.json`` (they carry the deployed harm score).
    Joined to shadow records by (sample_uid, params).
    """
    from sklearn.metrics import average_precision_score, roc_auc_score

    by_key = {(r["sample_uid"], _params_key(r["params"])): r for r in records}
    joined, unmatched = [], []
    for c in commits:
        k = (c["sample_uid"], _params_key(c["params"]))
        rec = by_key.get(k)
        if rec is None:
            unmatched.append(c["sample_uid"])
            continue
        joined.append({
            "sample_uid": c["sample_uid"],
            "dataset": c["dataset"],
            "params": c["params"],
            "harmful": bool(c["harmful"]),
            "beneficial_and_safe": bool(rec["eval_labels"]["beneficial_and_safe"]),
            "pics_harm_score": float(c["decision_detail"]["harm_score"]),
            "features": rec["features"],
        })
    if not joined:
        return {"error": "no accepted IMPUTE commits joined",
                "n_unmatched": len(unmatched)}

    harmful = np.asarray([j["harmful"] for j in joined], dtype=bool)
    bs = np.asarray([j["beneficial_and_safe"] for j in joined], dtype=bool)
    harm_score = np.asarray([j["pics_harm_score"] for j in joined])
    scores = harm_suspicion_scores(joined)

    auroc = float(roc_auc_score(harmful, scores))
    auprc_shadow = float(average_precision_score(harmful, scores))
    auprc_pics = float(average_precision_score(harmful, harm_score))
    wp = _working_point(scores, harmful, bs)
    rej = wp["reject"]

    # Per-source decomposition at the chosen working point.
    per_source = {}
    for j in joined:
        per_source.setdefault(source_group(j["dataset"]), []).append(j)
    source_report = {}
    for g in sorted(per_source):
        idx = [i for i, j in enumerate(joined)
               if source_group(j["dataset"]) == g]
        h = harmful[idx]
        r = rej[idx]
        s = scores[idx]
        entry = {
            "n_accepted_impute": len(idx),
            "n_harmful": int(h.sum()),
            "n_beneficial_and_safe": int(bs[idx].sum()),
            "harmful_recall_at_working_point":
                float(np.mean(r[h])) if h.any() else None,
            "auroc": float(roc_auc_score(h, s))
            if 0 < h.sum() < len(h) else None,
            "support1_share": float(np.mean(
                [j["features"]["shadow_support"] == 1
                 for j in per_source[g]])),
        }
        source_report[g] = entry
    gated_sources = {g: r for g, r in source_report.items()
                     if g in SOURCE_GROUPS
                     and r["n_harmful"] >= MIN_HARMFUL_FOR_SOURCE_GATE}

    gate1 = auroc >= GATE1_AUROC_MIN
    gate2 = (auprc_shadow - auprc_pics) >= AUPRC_MIN_IMPROVEMENT
    gate3_overall = wp["harmful_recall"] >= GATE3_RECALL_MIN
    gate3_sources = all(
        r["harmful_recall_at_working_point"] >= GATE3_SOURCE_RECALL_MIN
        for r in gated_sources.values())
    gate3 = gate3_overall and gate3_sources
    n_support = sum(r["features"]["shadow_valid_trials"] >= MIN_VALID_TRIALS
                    for r in records)
    coverage = n_support / max(len(records), 1)
    gate4 = coverage >= GATE4_COVERAGE_MIN

    gates = {
        "gate1_auroc": {
            "pass": bool(gate1), "auroc": auroc,
            "threshold": GATE1_AUROC_MIN,
            "primary_feature": "shadow_gain_mean (score = -gain_mean, "
                               "shadow_support==0 ranked most suspicious)"},
        "gate2_auprc_improvement": {
            "pass": bool(gate2),
            "auprc_shadow": auprc_shadow,
            "auprc_pics_harm_score": auprc_pics,
            "improvement": auprc_shadow - auprc_pics,
            "min_improvement": AUPRC_MIN_IMPROVEMENT},
        "gate3_recall_at_frr20": {
            "pass": bool(gate3),
            "harmful_recall": wp["harmful_recall"],
            "min_recall": GATE3_RECALL_MIN,
            "bs_false_reject_rate": wp["bs_false_reject_rate"],
            "bs_false_reject_max": BS_FALSE_REJECT_MAX,
            "threshold": wp["threshold"],
            "n_rejected": int(rej.sum()),
            "per_source": {g: r["harmful_recall_at_working_point"]
                           for g, r in source_report.items()},
            "gated_sources": sorted(gated_sources),
            "min_harmful_for_source_gate": MIN_HARMFUL_FOR_SOURCE_GATE,
            "source_gate_min_recall": GATE3_SOURCE_RECALL_MIN,
            "gate3_overall_pass": bool(gate3_overall),
            "gate3_sources_pass": bool(gate3_sources)},
        "gate4_trial_coverage": {
            "pass": bool(gate4),
            "share_valid_trials_ge2": coverage,
            "n_records": len(records),
            "n_with_valid_trials_ge2": int(n_support),
            "min_coverage": GATE4_COVERAGE_MIN},
    }
    n_fail = sum(1 for g in gates.values() if not g["pass"])
    verdict = "PASS" if n_fail == 0 else (
        "PARTIAL" if n_fail == 1 else "DIAGNOSTIC_FAILURE")

    out = {
        "population": {
            "n_pics_accepted_impute": len(commits),
            "n_joined": len(joined),
            "n_unmatched": len(unmatched),
            "unmatched_uids": unmatched,
            "n_harmful": int(harmful.sum()),
            "n_beneficial_and_safe": int(bs.sum()),
        },
        "gates": gates,
        "n_gates_failed": n_fail,
        "verdict": verdict,
        "per_source": source_report,
        "report_only_feature_aurocs": _feature_aurocs(joined, harmful),
        "joined": [
            {"sample_uid": j["sample_uid"], "dataset": j["dataset"],
             "harmful": j["harmful"],
             "beneficial_and_safe": j["beneficial_and_safe"],
             "pics_harm_score": j["pics_harm_score"],
             "shadow_score": float(scores[i]),
             "rejected_at_working_point": bool(rej[i]),
             "features": j["features"]}
            for i, j in enumerate(joined)],
    }
    if n_fail >= 2:
        # Pre-registered failure report: harmful commits the certificate did
        # not catch at the working point, with their feature values.
        out["failure_samples"] = [
            {"sample_uid": j["sample_uid"], "dataset": j["dataset"],
             "label": "harmful",
             "reason": "not rejected at working point",
             "shadow_score": float(scores[i]),
             "features": j["features"]}
            for i, j in enumerate(joined) if harmful[i] and not rej[i]]
    return out


def _feature_aurocs(joined: list, harmful: np.ndarray) -> dict:
    """Report-only AUROCs for every other shadow feature (not gate inputs)."""
    from sklearn.metrics import roc_auc_score
    names = ["shadow_candidate_error_mean", "shadow_candidate_error_q90",
             "shadow_candidate_error_std", "shadow_keep_error_mean",
             "shadow_gain_mean", "shadow_gain_worst", "shadow_stability"]
    out = {}
    sup = np.asarray([j["features"]["shadow_support"] == 1 for j in joined])
    for name in names:
        vals = np.asarray([j["features"][name] if j["features"][name] is not None
                           else np.nan for j in joined], dtype=np.float64)
        ok = sup & np.isfinite(vals)
        if ok.sum() < 3 or harmful[ok].sum() == 0 or (~harmful[ok]).sum() == 0:
            out[name] = None
            continue
        # harm-suspicion direction: errors and instability rank high, gains low.
        sign = -1.0 if "gain" in name else 1.0
        out[name] = float(roc_auc_score(harmful[ok], sign * vals[ok]))
    return out


# -- self-test driver (used by the multiprocess bit-consistency test) -----------


def _selftest_inputs() -> list:
    """Fixed synthetic windows and candidates; no corpus, no files, no labels."""
    rng = np.random.RandomState(7)
    walk = np.cumsum(rng.randn(256))
    block = walk.copy()
    block[120:140] = np.nan
    rng2 = np.random.RandomState(11)
    t = np.arange(256, dtype=np.float64)
    scat = 3.0 * np.sin(2 * np.pi * t / 24.0) + rng2.randn(256) * 0.3
    scat[np.linspace(20, 230, 10).astype(int)] = np.nan
    rng3 = np.random.RandomState(13)
    flat = np.cumsum(rng3.randn(256))
    flat[160:200] = flat[159]
    params = [{"method": "linear", "min_run": 16},
              {"method": "seasonal", "min_run": 8},
              {"method": "linear", "min_run": 32}]
    return [
        ("SELFTEST:block:0", block, params),
        ("SELFTEST:scattered:0", scat, params),
        ("SELFTEST:flatline:0", flat, params),
    ]


def selftest(out_path: str) -> None:
    """Serialise shadow records for the fixed inputs, byte-stable."""
    records = []
    for uid, series, params_list in _selftest_inputs():
        for params, rec in zip(params_list,
                               _certify_uid((uid, series, params_list))):
            records.append({"sample_uid": uid, "params": params, **rec})
    records.sort(key=lambda r: (r["sample_uid"], _params_key(r["params"])))
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True) + "\n")


# -- main ------------------------------------------------------------------------


def _code_hashes() -> dict:
    out = {}
    for rel in ("experiments/v34_shadow_certificate.py",
                "src/introact_ts/actions.py",
                "src/introact_ts/probe.py",
                "experiments/metrics_common.py",
                "experiments/v33_labels.py"):
        p = ROOT / rel
        if p.exists():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "results" / "v33_training_data.jsonl"))
    ap.add_argument("--harmful", default=str(ROOT / "results" / "v33_harmful_commits.json"))
    ap.add_argument("--manifest", default=str(ROOT / "results" / "p0_corpus_manifest_a.json"))
    ap.add_argument("--out", default=str(ROOT / "results" / "v34_shadow_certificate.json"))
    ap.add_argument("--records-out",
                    default=str(ROOT / "results" / "v34_shadow_records.jsonl"))
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
    ap.add_argument("--n-corpus", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--selftest", default=None,
                    help="write self-test records to this path and exit")
    args = ap.parse_args()

    if args.selftest:
        selftest(args.selftest)
        print(f"___V34_SHADOW_SELFTEST_DONE___ {args.selftest}")
        return

    import time
    t0 = time.time()

    rows = [json.loads(l) for l in open(args.data, encoding="utf-8")]
    impute = [r for r in rows if r["family"] == "IMPUTE"]
    print(f"{len(rows)} candidates, {len(impute)} IMPUTE", flush=True)

    # Rebuild the frozen seed-101 calibration corpus exactly as the candidate
    # table builder did, then match windows by corrupted_hash -- the pristine
    # series is never read anywhere in this script.
    from build_calibration import build as build_calibration
    windows, _ = build_calibration(n=args.n_corpus, seed=args.seed,
                                   source="mixed", verbose=False)
    print(f"rebuilt {len(windows)} windows in {time.time() - t0:.1f}s",
          flush=True)
    by_hash = defaultdict(list)
    for w in windows:
        by_hash[hash_array(np.asarray(w.series, dtype=np.float64))].append(w)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    manifest_hash = hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest()
    manifest_by_uid = {r["sample_uid"]: r for r in manifest["records"]}

    uid_series, n_hash_mismatch, unmatched_uids = {}, 0, []
    for r in impute:
        uid = r["sample_uid"]
        if uid in uid_series:
            continue
        cands = by_hash.get(r["corrupted_hash"], [])
        if len(cands) != 1:
            unmatched_uids.append(uid)
            continue
        series = np.asarray(cands[0].series, dtype=np.float64)
        if hash_array(series) != r["corrupted_hash"]:
            n_hash_mismatch += 1
            continue
        # The candidate table's uid is the manifest's; confirm the pair agrees.
        m = manifest_by_uid.get(uid)
        if m is None or m["corrupted_hash"] != r["corrupted_hash"]:
            n_hash_mismatch += 1
            continue
        uid_series[uid] = series
    print(f"matched {len(uid_series)} windows, unmatched {len(unmatched_uids)}, "
          f"hash mismatches {n_hash_mismatch}", flush=True)
    if unmatched_uids or n_hash_mismatch:
        raise SystemExit("window reconstruction failed verification; refusing "
                         "to certify against unverified series")

    tasks = []
    for r in impute:
        tasks.append((r["sample_uid"], r["params"], r))
    by_uid = defaultdict(list)
    for uid, params, row in tasks:
        by_uid[uid].append((params, row))
    work = [(uid, uid_series[uid],
             [p for p, _ in pairs]) for uid, pairs in sorted(by_uid.items())]

    t1 = time.time()
    records = []
    if args.n_jobs > 1 and len(work) > 1:
        with ProcessPoolExecutor(max_workers=args.n_jobs) as ex:
            per_uid = list(ex.map(_certify_uid, work))
    else:
        per_uid = [_certify_uid(w) for w in work]
    print(f"certified {len(work)} windows in {time.time() - t1:.1f}s "
          f"(n_jobs={args.n_jobs})", flush=True)

    n_formal_mismatch = 0
    for (uid, _, params_list), recs in zip(work, per_uid):
        rows_for_uid = by_uid[uid]
        for (params, row), rec in zip(rows_for_uid, recs):
            if rec["formal_output_hash"] is not None and \
                    rec["formal_output_hash"] != row.get("output_hash"):
                n_formal_mismatch += 1
            records.append({
                "sample_uid": uid,
                "window_id": row["window_id"],
                "dataset": row["dataset"],
                "stratum": row["stratum"],
                "family": row["family"],
                "rung": row["rung"],
                "params": row["params"],
                "corrupted_hash": row["corrupted_hash"],
                "manifest_hash": row["manifest_hash"],
                "geometry": rec["geometry"],
                "evidence_n": rec["evidence_n"],
                "ref_var_observed": rec["ref_var_observed"],
                "mask_hashes": [t["mask_hash"] for t in rec["trials"]],
                "trials": rec["trials"],
                "features": rec["features"],
                "formal_output_hash": rec["formal_output_hash"],
                "formal_output_matches_table":
                    rec["formal_output_hash"] == row.get("output_hash"),
                # evaluation namespace only; never read by the certificate
                "eval_labels": {
                    "harmful": bool(row["harmful"]),
                    "beneficial_and_safe": bool(row["beneficial_and_safe"]),
                    "true_loss": row["true_loss"],
                    "true_repair_gain": row["true_repair_gain"],
                },
            })
    records.sort(key=lambda r: (r["sample_uid"], _params_key(r["params"])))
    print(f"formal output hash mismatches: {n_formal_mismatch}", flush=True)

    with open(args.records_out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True) + "\n")

    harm = json.loads(Path(args.harmful).read_text(encoding="utf-8"))
    commits = [c for c in harm["PICS_joint_relabel"]["all_commits"]
               if c["family"] == "IMPUTE"]
    evaluation = evaluate(records, commits)

    summary = {
        "phase": "v3.4 Phase 2 shadow certificate signal probe",
        "preregistration": "docs/v3_4_scrc_pics_preregistration.md §2.1, §6",
        "error_definition": (
            "per-trial canonical uncentered finite-mask NMSE restricted to the "
            "pseudo-gap points; normaliser = metrics_common.ref_var of the "
            "window's observed (finite, non-evidence) values; raw MSE when "
            "ref_var < 1e-12. KEEP baseline = materialize_for_probe of the "
            "shadowed series, same formula."),
        "primary_feature": "shadow_gain_mean",
        "constants": {
            "n_replicas": N_REPLICAS, "evidence_min_run": EVIDENCE_MIN_RUN,
            "block_min_run": BLOCK_MIN_RUN, "clearance": CLEARANCE,
            "block_len_clip": list(BLOCK_LEN_CLIP),
            "scatter_k_clip": list(SCATTER_K_CLIP),
            "default_block_len": DEFAULT_BLOCK_LEN,
            "min_valid_trials": MIN_VALID_TRIALS,
            "min_harmful_for_source_gate": MIN_HARMFUL_FOR_SOURCE_GATE,
        },
        "reconstruction": {
            "method": "build_calibration.build(n=1600, seed=101, "
                      "source='mixed') rebuilt the frozen corpus; windows "
                      "matched to candidates by corrupted_hash; hash_array of "
                      "the rebuilt series re-verified against the candidate "
                      "table and the p0 manifest",
            "n_windows_rebuilt": len(windows),
            "n_windows_matched": len(uid_series),
            "n_unmatched_uids": len(unmatched_uids),
            "n_hash_mismatches": n_hash_mismatch,
            "manifest_hash": manifest_hash,
            "manifest_sha256_of_file": manifest_hash,
        },
        "operator_consistency": {
            "n_formal_output_hash_mismatches": n_formal_mismatch,
            "note": "certificate_operator dispatches apply_action(., IMPUTE, "
                    "**params); every candidate's output on the corrupted "
                    "series was re-hashed and compared to output_hash in the "
                    "frozen candidate table"},
        "n_impute_candidates": len(impute),
        "n_records": len(records),
        "geometry_counts": dict(Counter(r["geometry"] for r in records)),
        "evaluation": evaluation,
        "code_hashes": _code_hashes(),
        "elapsed_seconds": time.time() - t0,
    }
    Path(args.out).write_text(json.dumps(summary, indent=1, default=float),
                              encoding="utf-8")
    print(json.dumps({k: v["pass"] for k, v in evaluation["gates"].items()},
                     indent=1))
    print("verdict:", evaluation["verdict"])
    print(f"___V34_SHADOW_CERTIFICATE_DONE___ wrote {args.out} and "
          f"{args.records_out}", flush=True)


if __name__ == "__main__":
    main()
