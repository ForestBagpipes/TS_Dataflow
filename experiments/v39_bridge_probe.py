"""v3.9 Phase 2: MIRAGE-TS BRIDGE long-gap action -- risk-gated eta shrinkage.

Pre-registered in ``docs/v3_9_mirage_preregistration.md`` §4. CPU-only,
API 0. Reads the frozen Phase-1 candidate file (no model inference is ever
re-run); candidate labels are re-derived with the exact Phase-1 label path
(``experiments/v33_labels.py::compute_action_labels``, family "IMPUTE")
ONLY after the Phase-2 candidate/signal freeze.

BRIDGE candidates (§4): for each base proposer m_j in
{tsicl, openfim, fm_mean, moment} and the frozen linear bridge b,

    z(j, eta) = b + eta * (m_j - b),  eta in {0, 0.25, 0.5, 0.75, 1.0}

mixed ONLY on the raw NaN mask; observed support is unchanged per value
(drift == 0 asserted for every candidate). eta=0 reproduces the frozen
linear_bridge output hash and eta=1 the base proposer's output hash
(per-window integrity gate at candidate time; label-set cross-check against
the Phase-1 probe at evaluate time).

Five deployment-available risk signals (§4; never the v3.4 shadow score or
the v3.5 prequential score):

 1. posterior_width          TS-ICL q90-q10 width over the gap, normalised by
                             the observed MAD with a train-source floor
                             (winsorised/robust: the floor is the train q10 of
                             observed MADs, the ECDF winsorises at 1%/99%)
 2. cross_model_disagreement mean |OpenFIM - TS-ICL median| over the gap,
                             same robust MAD normalisation
 3. boundary_seam            max over {left/right} x {value, first-order
                             slope} discontinuity at the gap edges, robust-
                             scale normalised (v3.8 diagnostics convention)
 4. bridge_deviation         mean |z - b| over the gap, robust MAD
                             normalisation (= eta * the base deviation)
 5. unsupported/missing-view flag (missing view => normalised signal 1.0 and
                             the window KEEPs; with no usable foundation
                             imputer the rule never commits)

Primary risk score: each signal is normalised by a robust empirical CDF
fitted on the five TRAIN sources of the LODO fold (winsorised at the train
1%/99% quantiles); R = max(width, disagreement, seam). Primary FM path:
fm_mean (the OpenFIM/TS-ICL central-estimate mean). Operating point grid
(fixed, §4): risk quantile tau in {0.2, 0.4, 0.6, 0.8} x eta in
{0, 0.25, 0.5, 0.75, 1.0}; a window commits z(fm_mean, eta) iff its
train-normalised R <= tau, otherwise it KEEPs (eta=0 IS the linear bridge,
so low-eta grid points are the "high R shrinks to linear" behaviour).

Calibration (§4, strict): six LODO folds; each fold fits the robust CDFs on
the five train sources only and selects the maximum-coverage grid point
whose train CHR Clopper-Pearson 95% upper bound <= 0.15 (tie-break: more
train B&S, then larger eta, then smaller tau). The held-out source never
participates in normalisation, selection or calibration.

Signal gates (§4, reported one by one): harmful AUROC >= 0.70; AUPRC lift
over random prevalence >= 0.10; a trained LODO working point submits >= 15
commits on long blocks (pooled held-out); held-out CHR <= 0.15; >= 4/6
sources non-inferior (per-source B&S count >= tsicl's and harmful count
<= tsicl's on that source's long-gap windows); against the best single
proposer (tsicl), B&S non-decreasing with harmful reduced, or more B&S at
the same harmful. All uncertainty ablations are reported regardless of how
low any model's harmful rate is.

Conditional branch (§4): if the candidate oracle passes but the risk
signals fail, train ONE pre-registered light monotone risk head (isotonic
on each of the five normalised signals and on R, source-group DRO model
choice by worst-source Brier loss; no HGB, no deep nets, no legacy PICS
features), then re-run the same grid once. Still failing => stop.

Stages:
    python experiments/v39_bridge_probe.py candidates
    python experiments/v39_bridge_probe.py freeze
    python experiments/v39_bridge_probe.py evaluate
"""

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats as _scipy_stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

import v39_longgap_probe as p1  # noqa: E402
from v33_labels import compute_action_labels, hash_array  # noqa: E402
from v38_impute_mask_audit import raw_nan_mask  # noqa: E402
from introact_ts.actions import robust_scale  # noqa: E402

P1_CANDIDATES = ROOT / "results" / "v39_longgap_candidates.jsonl"
P1_FREEZE = ROOT / "results" / "v39_longgap_candidates_freeze.json"
P1_PROBE = ROOT / "results" / "v39_longgap_probe.json"

OUT_CANDIDATES = ROOT / "results" / "v39_bridge_candidates.jsonl"
OUT_SIGNALS = ROOT / "results" / "v39_bridge_signals.jsonl"
OUT_FREEZE = ROOT / "results" / "v39_bridge_freeze.json"
OUT_PROBE = ROOT / "results" / "v39_bridge_probe.json"
OUT_MANIFEST = ROOT / "results" / "v39_bridge_manifest.json"

#: Base proposers whose fills mix with the linear bridge (§4).
BASE_PROPOSERS = ("tsicl", "openfim", "fm_mean", "moment")
#: Primary FM path (§4: the OpenFIM/TS-ICL central-estimate mean).
PRIMARY_BASE = "fm_mean"
BRIDGE_REF = "linear_bridge"
ETAS = (0.0, 0.25, 0.5, 0.75, 1.0)
RISK_QUANTILES = (0.2, 0.4, 0.6, 0.8)

HARM_LOSS = 0.03
CHR_CALIB_UPPER = 0.15
CP_ALPHA = 0.05
#: Robust-width truncation: the observed-MAD denominator is floored at this
#: quantile of the TRAIN sources' observed MADs (§4 truncated/robust width).
MAD_FLOOR_QUANTILE = 0.10
#: Robust ECDF winsorisation quantiles (fitted on train values).
ECDF_WINSOR = (0.01, 0.99)

GATE_AUROC = 0.70
GATE_AUPRC_LIFT = 0.10
GATE_MIN_COMMITS = 15
GATE_HELDOUT_CHR = 0.15
GATE_SOURCES_NONINFERIOR = 4

#: Risk-rule ablation modes (all reported even if a model is already safe).
RISK_MODES = ("max_w_d_s", "width_only", "disagreement_only", "seam_only",
              "drop_width", "drop_disagreement", "drop_seam")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# -- pure signal / mixing helpers (unit-tested) --------------------------------


def mix_fill(b, m, eta):
    """z = b + eta * (m - b) on the gap positions (exact at eta in {0, 1})."""
    b = np.asarray(b, dtype=np.float64)
    m = np.asarray(m, dtype=np.float64)
    assert b.shape == m.shape
    if eta == 0.0:
        return b.copy()
    if eta == 1.0:
        return m.copy()
    return b + float(eta) * (m - b)


def mad_floor(train_mads, q=MAD_FLOOR_QUANTILE):
    """Train-source truncation point for the observed-MAD denominator."""
    v = np.asarray(list(train_mads), dtype=np.float64)
    assert len(v) > 0
    return float(np.quantile(v, q))


def norm_by_mad(value, observed_mad, floor):
    """Robust MAD normalisation with the train-source floor."""
    return float(value) / max(float(observed_mad), float(floor), 1e-12)


def disagreement_abs(openfim_fill, tsicl_fill):
    """Mean |OpenFIM - TS-ICL median| over the gap positions."""
    a = np.asarray(openfim_fill, dtype=np.float64)
    t = np.asarray(tsicl_fill, dtype=np.float64)
    assert a.shape == t.shape
    return float(np.mean(np.abs(a - t)))


def deviation_abs(z, b):
    """Mean |z - b| over the gap positions (== eta * base deviation)."""
    z = np.asarray(z, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    assert z.shape == b.shape
    return float(np.mean(np.abs(z - b)))


def seam_components(x, y, lo, hi, scale=None):
    """Value and first-order-slope discontinuities at both gap edges.

    ``lo``/``hi`` are the raw-NaN run bounds (hi exclusive), y the filled
    window. Normalised by ``robust_scale`` of the raw window (v3.8
    convention). Components that would leave the window are skipped.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    scale = float(scale if scale is not None else robust_scale(x))
    scale = max(scale, 1e-12)
    T = len(x)
    out = {}
    if lo >= 1:
        out["left_value"] = abs(float(y[lo]) - float(x[lo - 1])) / scale
    if lo >= 2 and lo + 1 < T:
        out["left_slope"] = abs((float(y[lo + 1]) - float(y[lo]))
                                - (float(x[lo - 1]) - float(x[lo - 2]))
                                ) / scale
    if hi < T:
        out["right_value"] = abs(float(y[hi - 1]) - float(x[hi])) / scale
    if hi + 1 < T and hi >= 2:
        out["right_slope"] = abs((float(x[hi + 1]) - float(x[hi]))
                                 - (float(y[hi - 1]) - float(y[hi - 2]))
                                 ) / scale
    out["max"] = max(out.values()) if out else 0.0
    return out


def robust_ecdf_fit(train_values, winsor=ECDF_WINSOR):
    """Robust empirical CDF fit on train values (winsorised + sorted)."""
    v = np.asarray([v for v in train_values if np.isfinite(v)],
                   dtype=np.float64)
    assert len(v) > 0, "robust ECDF needs at least one train value"
    lo, hi = np.quantile(v, winsor[0]), np.quantile(v, winsor[1])
    clipped = np.sort(np.clip(v, lo, hi))
    return {"sorted": clipped, "lo": float(lo), "hi": float(hi),
            "n": int(len(v)), "winsor": list(winsor)}


def robust_ecdf_eval(fit, v):
    """Winsorised train ECDF value in [0, 1]; None (missing view) -> 1.0."""
    if v is None or not np.isfinite(v):
        return 1.0
    c = min(max(float(v), fit["lo"]), fit["hi"])
    return float(np.searchsorted(fit["sorted"], c, side="right") / fit["n"])


def risk_max(n_width, n_dis, n_seam):
    """R = max of the normalised width / disagreement / seam signals."""
    return float(max(n_width, n_dis, n_seam))


RISK_MODE_SIGNALS = {
    "max_w_d_s": ("width", "disagreement", "seam"),
    "width_only": ("width",),
    "disagreement_only": ("disagreement",),
    "seam_only": ("seam",),
    "drop_width": ("disagreement", "seam"),
    "drop_disagreement": ("width", "seam"),
    "drop_seam": ("width", "disagreement"),
}


def risk_of(norm_signals, mode):
    """Normalised-signal dict -> R under an ablation risk mode."""
    keys = RISK_MODE_SIGNALS[mode]
    return float(max(norm_signals[k] for k in keys))


def clopper_pearson_upper(h, n, alpha=CP_ALPHA):
    """One-sided CP upper confidence bound on a binomial rate."""
    h, n = int(h), int(n)
    if n == 0:
        return 1.0
    if h >= n:
        return 1.0
    return float(_scipy_stats.beta.ppf(1.0 - alpha, h + 1, n - h))


def auroc(scores, labels):
    """Rank (Mann-Whitney) AUROC with average ranks for ties."""
    s = np.asarray(scores, dtype=np.float64)
    y = np.asarray(labels, dtype=np.int64)
    npos, nneg = int(y.sum()), int((1 - y).sum())
    if npos == 0 or nneg == 0:
        return None
    order = np.argsort(s, kind="mergesort")
    sr = s[order]
    ranks = np.empty(len(s), dtype=np.float64)
    r = np.arange(1, len(s) + 1, dtype=np.float64)
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and sr[j + 1] == sr[i]:
            j += 1
        r[i:j + 1] = (i + 1 + j + 1) / 2.0
        i = j + 1
    ranks[order] = r
    return float((ranks[y == 1].sum() - npos * (npos + 1) / 2.0)
                 / (npos * nneg))


def average_precision(scores, labels):
    """Non-interpolated average precision (AUPRC)."""
    s = np.asarray(scores, dtype=np.float64)
    y = np.asarray(labels, dtype=np.int64)
    npos = int(y.sum())
    if npos == 0:
        return None
    order = np.argsort(-s, kind="mergesort")
    ys = y[order]
    tp = np.cumsum(ys)
    prec = tp / np.arange(1, len(ys) + 1)
    return float((prec * ys).sum() / npos)


def select_working_point(grid_rows, chr_upper=CHR_CALIB_UPPER):
    """Max-coverage train grid point with CHR CP95 upper <= ``chr_upper``.

    Tie-break: more train B&S, then larger eta, then smaller tau. If no
    point satisfies the calibration bound, the most conservative point
    (lowest CP upper, then fewest commits) is returned flagged
    ``no_calibrated_point`` -- the commit-count gate will judge it.
    """
    ok = [g for g in grid_rows
          if g["cp_upper"] <= chr_upper and g["n_commits"] > 0]
    if ok:
        sel = sorted(ok, key=lambda g: (-g["n_commits"], -g["n_bs"],
                                        -g["eta"], g["tau"]))[0]
        return {"selected": dict(sel), "no_calibrated_point": False,
                "n_satisfying": len(ok)}
    fallback = sorted(grid_rows, key=lambda g: (g["cp_upper"],
                                                g["n_commits"]))[0]
    return {"selected": dict(fallback), "no_calibrated_point": True,
            "n_satisfying": 0}


def harmful_of_label(lab):
    return bool(lab is not None and float(lab["true_loss"]) > HARM_LOSS)


# -- stage 1: candidates + signals (label-free) ---------------------------------


def _load_p1_fills():
    """Frozen Phase-1 fills indexed by (uid, proposer); freeze-verified."""
    freeze = json.load(P1_FREEZE.open(encoding="utf-8"))
    if _sha256(P1_CANDIDATES) != freeze["merged_sha256"]:
        raise SystemExit("[FATAL] Phase-1 merged candidates changed after "
                         "their freeze")
    idx = {}
    for l in P1_CANDIDATES.open(encoding="utf-8"):
        r = json.loads(l)
        idx[(r["sample_uid"], r["proposer"])] = r
    return idx, freeze


def _bridge_record(meta, base, eta):
    rec = p1.base_record(meta, f"bridge_{base}", p1.BRIDGE_FAMILY,
                         f"eta{eta:g}",
                         {"base": base, "eta": float(eta),
                          "bridge": BRIDGE_REF}, True)
    rec["proposer"] = f"bridge_{base}"
    return rec


def run_candidates():
    t0 = time.time()
    p1_idx, p1_freeze = _load_p1_fills()
    print(f"[p1 freeze verified] digest="
          f"{p1_freeze['record_digest_sha256'][:16]}...", flush=True)
    pop, rebuilt = p1.load_population()

    cand_recs, sig_rows = [], []
    n_endpoint_hash_fail = 0
    n_unsupported = 0
    for uid in sorted(pop):
        meta = pop[uid]
        x = np.asarray(rebuilt[uid]["series"], dtype=np.float64)
        b_rec = p1_idx[(uid, BRIDGE_REF)]
        t_rec = p1_idx[(uid, "tsicl")]
        o_rec = p1_idx[(uid, "openfim")]
        bridge_ok = bool(b_rec["supported"] and b_rec["applicable"])
        tsicl_ok = bool(t_rec["supported"] and t_rec["applicable"])
        openfim_ok = bool(o_rec["supported"] and o_rec["applicable"])
        assert bridge_ok, f"{uid}: frozen linear bridge not applicable"
        b = np.asarray(b_rec["fill_values"], dtype=np.float64)

        # window-level signal components (label-free)
        unc = t_rec.get("uncertainty") or {}
        width_mean = (float(unc["q10_q90_width_mean"])
                      if tsicl_ok and "q10_q90_width_mean" in unc else None)
        obs_mad = float((unc.get("observed_mad")
                         if unc.get("observed_mad") is not None
                         else p1.observed_mad(x)))
        dis_abs = (disagreement_abs(o_rec["fill_values"],
                                    t_rec["fill_values"])
                   if openfim_ok and tsicl_ok else None)
        gap = meta["gap_decisions"][0]
        lo, hi = int(gap["lo"]), int(gap["hi"])

        for base in BASE_PROPOSERS:
            m_rec = p1_idx[(uid, base)]
            base_ok = bool(m_rec["supported"] and m_rec["applicable"])
            for eta in ETAS:
                rec = _bridge_record(meta, base, eta)
                missing_view = not (base_ok and tsicl_ok and openfim_ok)
                if not base_ok:
                    rec = p1.unsupported_record(
                        rec, f"base proposer {base} unsupported: "
                             f"{m_rec.get('unsupported_reason')}")
                    n_unsupported += 1
                    z = None
                    y = None
                else:
                    m = np.asarray(m_rec["fill_values"], dtype=np.float64)
                    z = mix_fill(b, m, eta)
                    y, filled = p1.insert_fill_at_raw_nan(x, z)
                    rec = p1.finalize_record(rec, x, y, filled)
                    # endpoint integrity: eta=0 IS the bridge, eta=1 IS m_j
                    if eta == 0.0 and rec["output_hash"] != \
                            b_rec["output_hash"]:
                        n_endpoint_hash_fail += 1
                    if eta == 1.0 and rec["output_hash"] != \
                            m_rec["output_hash"]:
                        n_endpoint_hash_fail += 1
                rec["config_hash"] = p1.config_hash(
                    {"proposer": rec["proposer"], "params": rec["params"]})
                cand_recs.append(rec)

                if z is not None:
                    seam = seam_components(x, y, lo, hi)
                    dev_abs = deviation_abs(z, b)
                else:
                    seam = {"max": None}
                    dev_abs = None
                sig_rows.append({
                    "sample_uid": uid, "dataset": meta["dataset"],
                    "base": base, "eta": float(eta),
                    "output_hash": rec["output_hash"],
                    "width_mean": width_mean,
                    "observed_mad": obs_mad,
                    "disagreement_abs_mean": dis_abs,
                    "seam_components": seam,
                    "seam_max": seam["max"],
                    "deviation_abs_mean": dev_abs,
                    "unsupported_missing_view": bool(
                        missing_view or z is None),
                    "foundation_imputer_available": bool(tsicl_ok or
                                                       openfim_ok),
                })
        if len(cand_recs) % 500 == 0:
            print(f"[candidates] {len(cand_recs)} "
                  f"({time.time() - t0:.0f}s)", flush=True)

    if n_endpoint_hash_fail:
        raise SystemExit(f"[FATAL] {n_endpoint_hash_fail} endpoint hash "
                         f"mismatches (eta=0 must equal linear_bridge, "
                         f"eta=1 the base proposer)")
    print(f"[candidates] {len(cand_recs)} records, {n_unsupported} "
          f"unsupported, endpoint hashes exact ({time.time() - t0:.1f}s)",
          flush=True)

    # Reference (pooled, label-free) robust normalisation + R. Reference
    # only: deployment decisions use per-fold TRAIN-source fits in evaluate.
    ref_floor = mad_floor([s["observed_mad"] for s in sig_rows])
    by_uid_rows = defaultdict(list)
    for s in sig_rows:
        by_uid_rows[s["sample_uid"]].append(s)
    ref_vals = {"width": [], "disagreement": [], "seam": [], "deviation": []}
    for s in sig_rows:
        if s["width_mean"] is not None:
            ref_vals["width"].append(norm_by_mad(s["width_mean"],
                                                 s["observed_mad"],
                                                 ref_floor))
        if s["disagreement_abs_mean"] is not None:
            ref_vals["disagreement"].append(
                norm_by_mad(s["disagreement_abs_mean"], s["observed_mad"],
                            ref_floor))
        if s["seam_max"] is not None:
            ref_vals["seam"].append(s["seam_max"])
        if s["deviation_abs_mean"] is not None:
            ref_vals["deviation"].append(
                norm_by_mad(s["deviation_abs_mean"], s["observed_mad"],
                            ref_floor))
    ref_fits = {k: robust_ecdf_fit(v) for k, v in ref_vals.items()}
    for s in sig_rows:
        fl = ref_floor
        nw = robust_ecdf_eval(
            ref_fits["width"],
            norm_by_mad(s["width_mean"], s["observed_mad"], fl)
            if s["width_mean"] is not None else None)
        nd = robust_ecdf_eval(
            ref_fits["disagreement"],
            norm_by_mad(s["disagreement_abs_mean"], s["observed_mad"], fl)
            if s["disagreement_abs_mean"] is not None else None)
        ns = robust_ecdf_eval(ref_fits["seam"], s["seam_max"])
        nv = robust_ecdf_eval(
            ref_fits["deviation"],
            norm_by_mad(s["deviation_abs_mean"], s["observed_mad"], fl)
            if s["deviation_abs_mean"] is not None else None)
        s["reference_normalisation"] = {
            "scope": ("pooled over all 89 windows, label-free; REFERENCE "
                      "ONLY -- deployment normalisation is per-LODO-fold "
                      "train-source"),
            "mad_floor": fl,
            "width": nw, "disagreement": nd, "seam": ns, "deviation": nv,
            "R_ref": risk_max(nw, nd, ns),
        }

    with OUT_CANDIDATES.open("w", encoding="utf-8") as f:
        for r in cand_recs:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    with OUT_SIGNALS.open("w", encoding="utf-8") as f:
        for s in sig_rows:
            f.write(json.dumps(s, sort_keys=True) + "\n")
    print(f"[candidates] -> {OUT_CANDIDATES.name} ({len(cand_recs)}), "
          f"{OUT_SIGNALS.name} ({len(sig_rows)})", flush=True)
    print("___V39_BRIDGE_CANDIDATES_DONE___", flush=True)
    return 0


# -- stage 2: freeze ---------------------------------------------------------------


def _cand_digest(records):
    slim = sorted(({"sample_uid": r["sample_uid"], "proposer": r["proposer"],
                    "rung": r["rung"], "supported": r["supported"],
                    "output_hash": r["output_hash"]} for r in records),
                  key=lambda r: (r["sample_uid"], r["proposer"], r["rung"]))
    return hashlib.sha256(json.dumps(slim, sort_keys=True).encode()
                          ).hexdigest(), len(slim)


def run_freeze():
    t0 = time.time()
    cand = [json.loads(l) for l in OUT_CANDIDATES.open(encoding="utf-8")]
    sigs = [json.loads(l) for l in OUT_SIGNALS.open(encoding="utf-8")]
    digest, n = _cand_digest(cand)
    freeze = {
        "phase": "v3.9 Phase 2 BRIDGE candidate/signal freeze (labels not "
                 "yet joined)",
        "frozen_at_epoch": time.time(),
        "n_candidates": n,
        "n_signals": len(sigs),
        "n_windows": len({r["sample_uid"] for r in cand}),
        "bases": list(BASE_PROPOSERS), "etas": list(ETAS),
        "candidates_file": OUT_CANDIDATES.name,
        "candidates_sha256": _sha256(OUT_CANDIDATES),
        "signals_file": OUT_SIGNALS.name,
        "signals_sha256": _sha256(OUT_SIGNALS),
        "candidate_digest_sha256": digest,
        "label_freeze_discipline": ("candidate outputs, signals and hashes "
                                    "frozen before any clean/evaluation "
                                    "label is read; evaluate re-verifies "
                                    "every output hash from the stored fill "
                                    "values and cross-checks the eta=1 "
                                    "label sets against the Phase-1 probe"),
        "runtime_sec": time.time() - t0,
    }
    with OUT_FREEZE.open("w", encoding="utf-8") as f:
        json.dump(freeze, f, indent=1)
    print(f"[freeze] {n} candidates, digest={digest[:16]}... -> "
          f"{OUT_FREEZE.name}", flush=True)
    print("___V39_BRIDGE_FREEZE_DONE___", flush=True)
    return 0


# -- stage 3: evaluate (labels joined here, and only here) ------------------------


def _join_labels(cand, rebuilt):
    """Re-derive labels with the exact Phase-1 label path; verify hashes."""
    n_hash_fail, max_drift = 0, 0.0
    for r in cand:
        uid = r["sample_uid"]
        x = np.asarray(rebuilt[uid]["series"], dtype=np.float64)
        clean = np.asarray(rebuilt[uid]["window"].clean_series,
                           dtype=np.float64)
        if not r["supported"]:
            r["labels"] = None
            continue
        y, _f = p1.insert_fill_at_raw_nan(x, r["fill_values"])
        if hash_array(y) != r["output_hash"]:
            n_hash_fail += 1
        obs = np.isfinite(x)
        drift = float(np.max(np.abs(y[obs] - x[obs]))) if obs.any() else 0.0
        max_drift = max(max_drift, drift, r["observed_support_drift"])
        assert drift == 0.0 and r["observed_support_drift"] == 0.0
        lab = compute_action_labels("IMPUTE", x, y, clean,
                                    touched=raw_nan_mask(x), params={})
        r["labels"] = {k: (float(v) if isinstance(v, (int, float,
                                                      np.floating))
                           and v is not None else v)
                       for k, v in lab.items()}
    if n_hash_fail:
        raise SystemExit(f"[FATAL] {n_hash_fail} frozen output hashes do "
                         f"not reproduce from stored fill values")
    return max_drift


def _p1_endpoint_xcheck(cand):
    """eta=1 label sets must equal the Phase-1 probe's per-proposer sets."""
    probe = json.load(P1_PROBE.open(encoding="utf-8"))
    tables = probe["proposer_tables"]
    out = {}
    for base in BASE_PROPOSERS:
        got_bs, got_harm = set(), set()
        for r in cand:
            if r["proposer"] != f"bridge_{base}" or \
                    r["params"]["eta"] != 1.0 or not r["supported"]:
                continue
            if r["labels"]["beneficial_and_safe"]:
                got_bs.add(r["sample_uid"])
            if harmful_of_label(r["labels"]):
                got_harm.add(r["sample_uid"])
        ref = tables[base]
        out[base] = {
            "bs_match": got_bs == set(ref["bs_uids"]),
            "harmful_match": got_harm == set(ref["harmful_uids"]),
            "n_bs": len(got_bs), "n_harmful": len(got_harm),
        }
    got_bs, got_harm = set(), set()
    for r in cand:
        if r["params"]["eta"] == 0.0 and r["proposer"] == "bridge_tsicl" \
                and r["supported"]:
            if r["labels"]["beneficial_and_safe"]:
                got_bs.add(r["sample_uid"])
            if harmful_of_label(r["labels"]):
                got_harm.add(r["sample_uid"])
    ref = tables[BRIDGE_REF]
    out[BRIDGE_REF] = {
        "bs_match": got_bs == set(ref["bs_uids"]),
        "harmful_match": got_harm == set(ref["harmful_uids"]),
        "n_bs": len(got_bs), "n_harmful": len(got_harm),
        "note": "eta=0 checked on the bridge_tsicl rows (identical for all "
                "bases by the endpoint hash gate)",
    }
    return out


class FoldFits:
    """Train-source robust normalisation for one LODO fold."""

    def __init__(self, train_uids, sig_index, cand_index):
        mads = [sig_index[(u, PRIMARY_BASE, 1.0)]["observed_mad"]
                for u in train_uids]
        self.floor = mad_floor(mads)
        vals = {"width": [], "disagreement": [], "seam": [], "deviation": []}
        for u in train_uids:
            for base in BASE_PROPOSERS:
                for eta in ETAS:
                    s = sig_index.get((u, base, eta))
                    if s is None:
                        continue
                    if s["width_mean"] is not None:
                        vals["width"].append(norm_by_mad(
                            s["width_mean"], s["observed_mad"], self.floor))
                    if s["disagreement_abs_mean"] is not None:
                        vals["disagreement"].append(norm_by_mad(
                            s["disagreement_abs_mean"], s["observed_mad"],
                            self.floor))
                    if s["seam_max"] is not None:
                        vals["seam"].append(s["seam_max"])
                    if s["deviation_abs_mean"] is not None:
                        vals["deviation"].append(norm_by_mad(
                            s["deviation_abs_mean"], s["observed_mad"],
                            self.floor))
        # width/disagreement are window-level: dedupe to one value per window
        self.fits = {
            "width": robust_ecdf_fit(sorted(set(vals["width"]))),
            "disagreement": robust_ecdf_fit(
                sorted(set(vals["disagreement"]))),
            "seam": robust_ecdf_fit(vals["seam"]),
            "deviation": robust_ecdf_fit(vals["deviation"]),
        }

    def norm_signals(self, s):
        fl = self.floor
        nw = robust_ecdf_eval(
            self.fits["width"],
            norm_by_mad(s["width_mean"], s["observed_mad"], fl)
            if s["width_mean"] is not None else None)
        nd = robust_ecdf_eval(
            self.fits["disagreement"],
            norm_by_mad(s["disagreement_abs_mean"], s["observed_mad"], fl)
            if s["disagreement_abs_mean"] is not None else None)
        ns = robust_ecdf_eval(self.fits["seam"], s["seam_max"])
        nv = robust_ecdf_eval(
            self.fits["deviation"],
            norm_by_mad(s["deviation_abs_mean"], s["observed_mad"], fl)
            if s["deviation_abs_mean"] is not None else None)
        return {"width": nw, "disagreement": nd, "seam": ns, "deviation": nv}


def _arm_stats(uids, commit_map, cand_index):
    """Five-quantity report for a commit map {uid: (base, eta) or None}."""
    commits, bs, harm, gains = 0, 0, 0, []
    for u in uids:
        pick = commit_map.get(u)
        if pick is None:
            gains.append(0.0)
            continue
        lab = cand_index[(u, pick[0], pick[1])]["labels"]
        commits += 1
        bs += int(bool(lab["beneficial_and_safe"]))
        harm += int(harmful_of_label(lab))
        gains.append(float(lab["true_repair_gain"]))
    n = len(uids)
    return {
        "n_windows": n, "n_commits": commits,
        "proposal_coverage": commits / n if n else None,
        "n_bs": bs, "n_harmful": harm,
        "action_conditional_bs_precision": bs / commits if commits else None,
        "action_conditional_chr": harm / commits if commits else None,
        "chr_cp95_upper": clopper_pearson_upper(harm, commits),
        "bcov_population": bs / n if n else None,
        "abstention_rate": 1.0 - commits / n if n else None,
        "mean_gain_all_windows": float(np.mean(gains)) if gains else None,
        "commit_uids": sorted(u for u in uids if commit_map.get(u)),
    }


def _run_grid(train_uids, test_uids, sig_index, cand_index, fits, base,
              mode):
    """Grid calibration on train + held-out application for (base, mode)."""
    grid_rows = []
    for tau in RISK_QUANTILES:
        for eta in ETAS:
            commits = []
            for u in train_uids:
                s = sig_index.get((u, base, eta))
                if s is None or s["unsupported_missing_view"]:
                    continue
                if not s["foundation_imputer_available"]:
                    continue  # no usable foundation imputer -> KEEP
                r = risk_of(fits.norm_signals(s), mode)
                if r <= tau:
                    commits.append(u)
            harm = sum(int(harmful_of_label(
                cand_index[(u, base, eta)]["labels"])) for u in commits)
            bs = sum(int(bool(
                cand_index[(u, base, eta)]["labels"]
                ["beneficial_and_safe"])) for u in commits)
            grid_rows.append({
                "tau": tau, "eta": eta, "n_commits": len(commits),
                "n_bs": bs, "n_harmful": harm,
                "chr": harm / len(commits) if commits else None,
                "cp_upper": clopper_pearson_upper(harm, len(commits)),
            })
    sel = select_working_point(grid_rows)
    tau, eta = sel["selected"]["tau"], sel["selected"]["eta"]
    test_map = {}
    for u in test_uids:
        s = sig_index.get((u, base, eta))
        if s is None or s["unsupported_missing_view"]:
            test_map[u] = None
            continue
        if not s["foundation_imputer_available"]:
            test_map[u] = None
            continue
        test_map[u] = (base, eta) if risk_of(fits.norm_signals(s),
                                             mode) <= tau else None
    train_map = {}
    for u in train_uids:
        s = sig_index.get((u, base, eta))
        ok = (s is not None and not s["unsupported_missing_view"]
              and s["foundation_imputer_available"]
              and risk_of(fits.norm_signals(s), mode) <= tau)
        train_map[u] = (base, eta) if ok else None
    return {"grid": grid_rows, "selection": sel,
            "train_stats": _arm_stats(train_uids, train_map, cand_index),
            "test_stats": _arm_stats(test_uids, test_map, cand_index),
            "test_map": test_map}


def run_evaluate():
    t0 = time.time()
    if not OUT_FREEZE.exists():
        raise SystemExit("[FATAL] candidates not frozen; run `candidates` "
                         "then `freeze` before `evaluate`")
    freeze = json.load(OUT_FREEZE.open(encoding="utf-8"))
    if _sha256(OUT_CANDIDATES) != freeze["candidates_sha256"] or \
            _sha256(OUT_SIGNALS) != freeze["signals_sha256"]:
        raise SystemExit("[FATAL] Phase-2 candidate/signal files changed "
                         "after freeze")
    print(f"[freeze verified] digest="
          f"{freeze['candidate_digest_sha256'][:16]}...", flush=True)

    pop, rebuilt = p1.load_population()
    cand = [json.loads(l) for l in OUT_CANDIDATES.open(encoding="utf-8")]
    sigs = [json.loads(l) for l in OUT_SIGNALS.open(encoding="utf-8")]
    assert len(cand) == freeze["n_candidates"]
    assert len(sigs) == freeze["n_signals"]

    max_drift = _join_labels(cand, rebuilt)
    print(f"[labels joined] max observed drift={max_drift}", flush=True)

    xcheck = _p1_endpoint_xcheck(cand)
    xcheck_pass = all(v["bs_match"] and v["harmful_match"]
                      for v in xcheck.values())
    print(f"[p1 endpoint xcheck] pass={xcheck_pass} "
          f"{ {k: (v['n_bs'], v['n_harmful']) for k, v in xcheck.items()} }",
          flush=True)

    cand_index = {}
    for r in cand:
        base = r["params"]["base"]
        cand_index[(r["sample_uid"], base, r["params"]["eta"])] = r
    sig_index = {(s["sample_uid"], s["base"], s["eta"]): s for s in sigs}

    uids = sorted(pop)
    uid_src = {u: pop[u]["dataset"] for u in uids}
    sources = sorted(set(uid_src.values()))

    # -- candidate oracle over the eta mixtures (headroom reference) ----------
    oracle_bs_uids = []
    for u in uids:
        best = None
        for base in BASE_PROPOSERS:
            for eta in ETAS:
                r = cand_index[(u, base, eta)]
                if r["supported"] and r["labels"]["beneficial_and_safe"]:
                    g = float(r["labels"]["true_repair_gain"])
                    if best is None or g > best[1]:
                        best = ((base, eta), g)
        if best is not None:
            oracle_bs_uids.append(u)
    oracle = {"n_windows_any_bs_mixture": len(oracle_bs_uids),
              "mixture_oracle_pass": len(oracle_bs_uids) >= GATE_MIN_COMMITS}

    # -- LODO folds ---------------------------------------------------------------
    folds = []
    for held in sources:
        train_uids = [u for u in uids if uid_src[u] != held]
        test_uids = [u for u in uids if uid_src[u] == held]
        fits = FoldFits(train_uids, sig_index, cand_index)
        folds.append({"held_out": held, "train_uids": train_uids,
                      "test_uids": test_uids, "fits": fits})
        print(f"[fold {held}] train={len(train_uids)} "
              f"held-out={len(test_uids)} mad_floor={fits.floor:.4g}",
              flush=True)

    # Primary arm + risk-mode ablations on the primary base, and base
    # ablations under the full R rule.
    arms = {}
    for mode in RISK_MODES:
        arms[f"primary_{mode}"] = (PRIMARY_BASE, mode)
    for base in BASE_PROPOSERS:
        if base != PRIMARY_BASE:
            arms[f"base_{base}_max_w_d_s"] = (base, "max_w_d_s")
    arm_folds = {a: [] for a in arms}
    for f in folds:
        for a, (base, mode) in arms.items():
            res = _run_grid(f["train_uids"], f["test_uids"], sig_index,
                            cand_index, f["fits"], base, mode)
            arm_folds[a].append({"held_out": f["held_out"], **res})

    # Fixed-eta no-gate ablations (commit every applicable window), incl. the
    # single-proposer references.
    fixed_eta = {}
    for base in BASE_PROPOSERS + (BRIDGE_REF,):
        for eta in (ETAS if base != BRIDGE_REF else (None,)):
            key = (f"fixed_{base}_eta{eta:g}" if eta is not None
                   else f"fixed_{BRIDGE_REF}_direct")
            stats_per_src = {}
            commits, bs, harm, gains = 0, 0, 0, []
            for u in uids:
                if base == BRIDGE_REF:
                    pick_base, pick_eta = PRIMARY_BASE, 0.0
                else:
                    pick_base, pick_eta = base, eta
                r = cand_index[(u, pick_base, pick_eta)]
                if not r["supported"]:
                    gains.append(0.0)
                    continue
                lab = r["labels"]
                commits += 1
                bs += int(bool(lab["beneficial_and_safe"]))
                harm += int(harmful_of_label(lab))
                gains.append(float(lab["true_repair_gain"]))
            n = len(uids)
            fixed_eta[key] = {
                "n_windows": n, "n_commits": commits, "n_bs": bs,
                "n_harmful": harm,
                "action_conditional_bs_precision":
                    bs / commits if commits else None,
                "action_conditional_chr": harm / commits if commits else None,
                "chr_cp95_upper": clopper_pearson_upper(harm, commits),
                "bcov_population": bs / n, "abstention_rate": 1 - commits / n,
                "mean_gain_all_windows": float(np.mean(gains)),
                "note": ("no risk gate; reference arm"
                         + (" (eta=0 rows == frozen linear_bridge by the "
                            "endpoint hash gate)" if base == BRIDGE_REF
                            else "")),
            }

    # -- pooled held-out metrics per arm -------------------------------------------
    def pooled(a):
        per = arm_folds[a]
        commits, bs, harm = 0, 0, 0
        gains = []
        commit_uids = []
        per_source = {}
        for f in per:
            st = f["test_stats"]
            commits += st["n_commits"]
            bs += st["n_bs"]
            harm += st["n_harmful"]
            commit_uids.extend(st["commit_uids"])
            per_source[f["held_out"]] = {
                "n_commits": st["n_commits"], "n_bs": st["n_bs"],
                "n_harmful": st["n_harmful"],
                "chr": st["action_conditional_chr"]}
            base_, _mode = arms[a]
            for u, pick in f["test_map"].items():
                if pick is None:
                    gains.append(0.0)
                else:
                    gains.append(float(
                        cand_index[(u, pick[0], pick[1])]["labels"]
                        ["true_repair_gain"]))
        n = len(uids)
        return {"n_windows": n, "n_commits": commits, "n_bs": bs,
                "n_harmful": harm,
                "action_conditional_bs_precision":
                    bs / commits if commits else None,
                "action_conditional_chr": harm / commits if commits else None,
                "chr_cp95_upper": clopper_pearson_upper(harm, commits),
                "bcov_population": bs / n, "abstention_rate": 1 - commits / n,
                "mean_gain_all_windows": float(np.mean(gains)),
                "commit_uids": sorted(commit_uids),
                "per_source": per_source,
                "selected_points": [
                    {"held_out": f["held_out"],
                     "tau": f["selection"]["selected"]["tau"],
                     "eta": f["selection"]["selected"]["eta"],
                     "no_calibrated_point":
                         f["selection"]["no_calibrated_point"],
                     "train_n_commits": f["selection"]["selected"]
                     ["n_commits"],
                     "train_cp_upper": f["selection"]["selected"]
                     ["cp_upper"]} for f in per]}

    pooled_arms = {a: pooled(a) for a in arms}

    # -- signal discrimination (harmful AUROC / AUPRC) ------------------------------
    # LODO-honest scores: each window normalised by its fold's train fits.
    fold_of_uid = {}
    for f in folds:
        for u in f["test_uids"]:
            fold_of_uid[u] = f
    discr = {}
    prevalence_by_base = {}
    for base in BASE_PROPOSERS:
        labels1 = [int(harmful_of_label(
            cand_index[(u, base, 1.0)]["labels"])) for u in uids]
        prevalence_by_base[base] = float(np.mean(labels1))
        for sig_name in ("width", "disagreement", "seam", "deviation"):
            lodo_scores, pooled_scores = [], []
            for u in uids:
                s = sig_index[(u, base, 1.0)]
                f = fold_of_uid[u]
                lodo_scores.append(f["fits"].norm_signals(s)[sig_name])
                pooled_scores.append(
                    s["reference_normalisation"][sig_name])
            key = f"{sig_name}__{base}_eta1"
            discr[key] = {
                "auroc_lodo": auroc(lodo_scores, labels1),
                "auprc_lodo": average_precision(lodo_scores, labels1),
                "auroc_pooled_reference": auroc(pooled_scores, labels1),
                "auprc_pooled_reference": average_precision(pooled_scores,
                                                            labels1),
                "prevalence": prevalence_by_base[base],
            }
        # R (max rule) for this base at eta=1
        lodo_r, pooled_r = [], []
        for u in uids:
            s = sig_index[(u, base, 1.0)]
            f = fold_of_uid[u]
            lodo_r.append(risk_of(f["fits"].norm_signals(s), "max_w_d_s"))
            pooled_r.append(s["reference_normalisation"]["R_ref"])
        discr[f"R_max__{base}_eta1"] = {
            "auroc_lodo": auroc(lodo_r, labels1),
            "auprc_lodo": average_precision(lodo_r, labels1),
            "auroc_pooled_reference": auroc(pooled_r, labels1),
            "auprc_pooled_reference": average_precision(pooled_r, labels1),
            "prevalence": prevalence_by_base[base],
        }

    prim = pooled_arms["primary_max_w_d_s"]
    tsicl_ref = fixed_eta["fixed_tsicl_eta1"]
    discr_primary_R = discr[f"R_max__{PRIMARY_BASE}_eta1"]

    # -- signal gates (§4, one by one) ------------------------------------------------
    gates = {}
    gates["g1_harmful_auroc"] = {
        "rule": f"harmful AUROC >= {GATE_AUROC} (LODO-normalised R, primary "
                f"FM path {PRIMARY_BASE} eta=1)",
        "value": discr_primary_R["auroc_lodo"],
        "threshold": GATE_AUROC,
        "pass": bool(discr_primary_R["auroc_lodo"] is not None
                     and discr_primary_R["auroc_lodo"] >= GATE_AUROC)}
    lift = (discr_primary_R["auprc_lodo"] - discr_primary_R["prevalence"]
            if discr_primary_R["auprc_lodo"] is not None else None)
    gates["g2_auprc_lift"] = {
        "rule": f"AUPRC - random prevalence >= {GATE_AUPRC_LIFT} (same "
                "score/labels as g1)",
        "auprc_lodo": discr_primary_R["auprc_lodo"],
        "prevalence": discr_primary_R["prevalence"],
        "lift": lift, "threshold": GATE_AUPRC_LIFT,
        "pass": bool(lift is not None and lift >= GATE_AUPRC_LIFT)}
    gates["g3_lodo_workpoint_commits"] = {
        "rule": f"a train-selected LODO working point submits >= "
                f"{GATE_MIN_COMMITS} commits on long blocks (pooled "
                "held-out commits of the six fold-selected points; per-fold "
                "detail reported)",
        "pooled_heldout_commits": prim["n_commits"],
        "per_fold_heldout_commits": {
            f["held_out"]: f["test_stats"]["n_commits"]
            for a in ("primary_max_w_d_s",) for f in arm_folds[a]},
        "threshold": GATE_MIN_COMMITS,
        "pass": bool(prim["n_commits"] >= GATE_MIN_COMMITS)}
    gates["g4_heldout_chr"] = {
        "rule": f"pooled held-out CHR <= {GATE_HELDOUT_CHR} (LODO-selected "
                "working points, primary arm)",
        "value": prim["action_conditional_chr"],
        "cp95_upper": prim["chr_cp95_upper"],
        "threshold": GATE_HELDOUT_CHR,
        "pass": bool(prim["action_conditional_chr"] is not None
                     and prim["action_conditional_chr"]
                     <= GATE_HELDOUT_CHR)}
    per_src_noninf = {}
    n_noninf = 0
    for src in sources:
        b = prim["per_source"][src]
        t_bs = sum(int(bool(cand_index[(u, "tsicl", 1.0)]["labels"]
                           ["beneficial_and_safe"]))
                   for u in uids if uid_src[u] == src)
        t_harm = sum(int(harmful_of_label(
            cand_index[(u, "tsicl", 1.0)]["labels"]))
            for u in uids if uid_src[u] == src)
        noninf = bool(b["n_bs"] >= t_bs and b["n_harmful"] <= t_harm)
        n_noninf += int(noninf)
        per_src_noninf[src] = {"bridge_bs": b["n_bs"], "tsicl_bs": t_bs,
                               "bridge_harmful": b["n_harmful"],
                               "tsicl_harmful": t_harm,
                               "noninferior": noninf}
    gates["g5_source_noninferiority"] = {
        "rule": f">= {GATE_SOURCES_NONINFERIOR}/{len(sources)} sources with "
                "bridge B&S count >= tsicl's and harmful count <= tsicl's "
                "(long-gap windows of the source)",
        "n_noninferior": n_noninf, "per_source": per_src_noninf,
        "threshold": GATE_SOURCES_NONINFERIOR,
        "pass": bool(n_noninf >= GATE_SOURCES_NONINFERIOR)}
    pareto = bool((prim["n_bs"] >= tsicl_ref["n_bs"]
                   and prim["n_harmful"] < tsicl_ref["n_harmful"])
                  or (prim["n_bs"] > tsicl_ref["n_bs"]
                      and prim["n_harmful"] == tsicl_ref["n_harmful"]))
    gates["g6_pareto_vs_best_single_proposer"] = {
        "rule": ("vs the best single proposer (tsicl eta=1 direct): B&S "
                 "non-decreasing with harmful reduced, or more B&S at the "
                 "same harmful count"),
        "bridge": {"n_bs": prim["n_bs"], "n_harmful": prim["n_harmful"]},
        "tsicl_direct": {"n_bs": tsicl_ref["n_bs"],
                         "n_harmful": tsicl_ref["n_harmful"]},
        "pass": pareto}
    all_pass = bool(all(g["pass"] for g in gates.values()))

    # -- conditional branch: light monotone risk head (one pre-registered try) ------
    branch = {"needed": not all_pass and oracle["mixture_oracle_pass"],
              "executed": False}
    if branch["needed"]:
        branch = _risk_head_branch(folds, sig_index, cand_index, uids,
                                   uid_src, gates, branch)
        if branch.get("gates_after"):
            gates = branch["gates_after"]
            all_pass = bool(all(g["pass"] for g in gates.values()))

    verdict = ("bridge_signals_passed" if all_pass and not branch["executed"]
               else "risk_head_passed" if all_pass
               else "stop_signal_quality_insufficient")

    probe_out = {
        "phase": "v3.9 Phase 2: BRIDGE long-gap action, risk-gated eta "
                 "shrinkage (docs/v3_9_mirage_preregistration.md §4)",
        "definitions": {
            "mixing": "z(j,eta) = b + eta*(m_j - b) on the raw NaN mask "
                      "only; observed-support drift exactly 0",
            "bases": list(BASE_PROPOSERS), "primary_base": PRIMARY_BASE,
            "etas": list(ETAS), "risk_quantiles": list(RISK_QUANTILES),
            "risk_score": ("per-signal robust empirical CDF (train sources "
                           "of each LODO fold, winsorised 1%/99%); R = "
                           "max(width, disagreement, seam)"),
            "posterior_width": ("TS-ICL q90-q10 width over the gap / "
                                "max(observed MAD, train q10 MAD floor) -- "
                                "truncated/robust per §4"),
            "harmful": f"true_loss > {HARM_LOSS}",
            "calibration": ("per fold: train-source-only normalisation; "
                            "max-coverage grid point with train CHR CP95 "
                            f"upper <= {CHR_CALIB_UPPER}; held-out source "
                            "never normalises, selects or calibrates"),
            "label_path": ("experiments/v33_labels.py::compute_action_labels"
                           " family 'IMPUTE', joined ONLY after the Phase-2 "
                           "freeze; eta=1 label sets cross-checked against "
                           "the Phase-1 probe"),
            "forbidden_signals": ("v3.4 shadow score and v3.5 prequential "
                                  "score are NOT used anywhere in this "
                                  "phase"),
        },
        "freeze": {k: freeze[k] for k in ("n_candidates", "n_signals",
                                          "n_windows",
                                          "candidate_digest_sha256",
                                          "candidates_sha256",
                                          "signals_sha256")},
        "integrity": {
            "observed_support_drift_max": max_drift,
            "p1_endpoint_label_xcheck": xcheck,
            "p1_endpoint_label_xcheck_pass": xcheck_pass,
        },
        "candidate_mixture_oracle": oracle,
        "signal_discrimination": discr,
        "primary_arm_pooled": prim,
        "arms_pooled": pooled_arms,
        "fixed_eta_references": fixed_eta,
        "fold_details": {a: [{"held_out": f["held_out"],
                              "selection": f["selection"],
                              "train_stats": f["train_stats"],
                              "test_stats": f["test_stats"]}
                             for f in arm_folds[a]] for a in arms},
        "signal_gates": gates,
        "all_signal_gates_pass": all_pass,
        "risk_head_branch": branch,
        "verdict": verdict,
        "input_hashes": {
            "v39_longgap_candidates": _sha256(P1_CANDIDATES),
            "v39_longgap_candidates_freeze": _sha256(P1_FREEZE),
            "v39_longgap_probe": _sha256(P1_PROBE),
            "v33_training_data": _sha256(p1.ROWS_PATH),
            "v38_explicit_impute_records": _sha256(p1.EXPLICIT_RECORDS),
            "p0_corpus_manifest_a": _sha256(p1.MANIFEST_PATH),
        },
        "code_hashes": {
            "experiments/v39_bridge_probe.py": _sha256(
                Path(__file__).resolve()),
            "experiments/v39_longgap_probe.py": _sha256(
                ROOT / "experiments" / "v39_longgap_probe.py"),
            "experiments/v33_labels.py": _sha256(
                ROOT / "experiments" / "v33_labels.py"),
            "experiments/v38_impute_mask_audit.py": _sha256(
                ROOT / "experiments" / "v38_impute_mask_audit.py"),
        },
        "runtime_sec": time.time() - t0,
    }
    with OUT_PROBE.open("w", encoding="utf-8") as f:
        json.dump(probe_out, f, indent=1, ensure_ascii=False, default=str)
    print(f"[probe] -> {OUT_PROBE.name}", flush=True)

    manifest = {
        "phase": "v3.9 Phase 2 BRIDGE integrity manifest",
        "preregistration": "docs/v3_9_mirage_preregistration.md §4",
        "grid": {"risk_quantiles": list(RISK_QUANTILES),
                 "etas": list(ETAS), "bases": list(BASE_PROPOSERS),
                 "primary_base": PRIMARY_BASE,
                 "chr_calib_cp95_upper": CHR_CALIB_UPPER,
                 "mad_floor_quantile": MAD_FLOOR_QUANTILE,
                 "ecdf_winsor": list(ECDF_WINSOR)},
        "signal_gates": {k: v["pass"] for k, v in gates.items()},
        "all_pass": all_pass,
        "verdict": verdict,
        "candidate_digest_sha256": freeze["candidate_digest_sha256"],
        "input_hashes": probe_out["input_hashes"],
        "code_hashes": probe_out["code_hashes"],
        "output_sha256": {
            "results/v39_bridge_candidates.jsonl": _sha256(OUT_CANDIDATES),
            "results/v39_bridge_signals.jsonl": _sha256(OUT_SIGNALS),
            "results/v39_bridge_probe.json": _sha256(OUT_PROBE),
        },
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "runtime_sec": time.time() - t0,
    }
    with OUT_MANIFEST.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False, default=str)
    print(f"[manifest] verdict={verdict} all_pass={all_pass} -> "
          f"{OUT_MANIFEST.name}", flush=True)
    print(f"[done] runtime={time.time() - t0:.1f}s", flush=True)
    print("___V39_BRIDGE_EVALUATE_DONE___", flush=True)
    return 0


def _risk_head_branch(folds, sig_index, cand_index, uids, uid_src,
                      primary_gates, branch):
    """The single pre-registered conditional training (§4).

    Monotone isotonic heads on each of the five normalised signals and on
    R; the head is chosen by source-group DRO (worst train-source Brier
    loss). No HGB, no deep nets, no legacy PICS features. The same fixed
    grid/calibration protocol is then re-run once with the head score as
    the risk score.
    """
    from sklearn.isotonic import IsotonicRegression
    print("[branch] primary gates failed; running the ONE pre-registered "
          "risk-head training", flush=True)
    feats = ("width", "disagreement", "seam", "deviation")
    fold_results = []
    for f in folds:
        train_uids, test_uids, fits = f["train_uids"], f["test_uids"], \
            f["fits"]
        X, y, src_of = defaultdict(list), [], {}
        for u in train_uids:
            s = sig_index[(u, PRIMARY_BASE, 1.0)]
            ns = fits.norm_signals(s)
            for k in feats:
                X[k].append(ns[k])
            X["R"].append(risk_of(ns, "max_w_d_s"))
            y.append(int(harmful_of_label(
                cand_index[(u, PRIMARY_BASE, 1.0)]["labels"])))
            src_of[len(y) - 1] = uid_src[u]
        y = np.asarray(y)
        heads, dro_loss = {}, {}
        for k in list(feats) + ["R"]:
            iso = IsotonicRegression(out_of_bounds="clip",
                                     y_min=0.0, y_max=1.0)
            iso.fit(np.asarray(X[k]), y)
            p = iso.predict(np.asarray(X[k]))
            per_src = defaultdict(list)
            for i, pi in enumerate(p):
                per_src[src_of[i]].append((pi - y[i]) ** 2)
            dro_loss[k] = max(float(np.mean(v)) for v in per_src.values())
            heads[k] = iso
        best = sorted(dro_loss, key=lambda k: (dro_loss[k], k))[0]
        head = heads[best]
        fold_results.append({"held_out": f["held_out"],
                             "head_signal": best,
                             "worst_source_brier": dro_loss[best],
                             "head": head, "fits": fits})

        def head_score(u, eta, _f=f, _head=head, _best=best):
            s = sig_index[(u, PRIMARY_BASE, eta)]
            ns = _f["fits"].norm_signals(s)
            v = (risk_of(ns, "max_w_d_s") if _best == "R" else ns[_best])
            return float(_head.predict([v])[0])

        f["head_score"] = head_score
    # re-run the grid once with head scores as the risk score
    head_folds = []
    for f, fr in zip(folds, fold_results):
        grid_rows = []
        train_scores = [f["head_score"](u, 1.0) for u in f["train_uids"]]
        for tau in RISK_QUANTILES:
            thr = float(np.quantile(train_scores, tau))
            for eta in ETAS:
                commits = [u for u in f["train_uids"]
                           if f["head_score"](u, eta) <= thr]
                harm = sum(int(harmful_of_label(
                    cand_index[(u, PRIMARY_BASE, eta)]["labels"]))
                    for u in commits)
                bs = sum(int(bool(cand_index[(u, PRIMARY_BASE, eta)]
                                  ["labels"]["beneficial_and_safe"]))
                         for u in commits)
                grid_rows.append({"tau": tau, "eta": eta,
                                  "n_commits": len(commits), "n_bs": bs,
                                  "n_harmful": harm,
                                  "chr": harm / len(commits)
                                  if commits else None,
                                  "cp_upper": clopper_pearson_upper(
                                      harm, len(commits))})
        sel = select_working_point(grid_rows)
        tau, eta = sel["selected"]["tau"], sel["selected"]["eta"]
        thr = float(np.quantile(train_scores, tau))
        test_map = {u: ((PRIMARY_BASE, eta)
                        if f["head_score"](u, eta) <= thr else None)
                    for u in f["test_uids"]}
        head_folds.append({"held_out": f["held_out"], "selection": sel,
                           "test_map": test_map,
                           "test_stats": _arm_stats(f["test_uids"], test_map,
                                                    cand_index)})
    commits = sum(f["test_stats"]["n_commits"] for f in head_folds)
    bs = sum(f["test_stats"]["n_bs"] for f in head_folds)
    harm = sum(f["test_stats"]["n_harmful"] for f in head_folds)
    chr_ = harm / commits if commits else None
    gates2 = dict(primary_gates)
    gates2["g3_lodo_workpoint_commits"] = {
        **primary_gates["g3_lodo_workpoint_commits"],
        "pooled_heldout_commits": commits,
        "pass": bool(commits >= GATE_MIN_COMMITS)}
    gates2["g4_heldout_chr"] = {
        **primary_gates["g4_heldout_chr"], "value": chr_,
        "cp95_upper": clopper_pearson_upper(harm, commits),
        "pass": bool(chr_ is not None and chr_ <= GATE_HELDOUT_CHR)}
    per_src = defaultdict(lambda: {"n_bs": 0, "n_harmful": 0, "n_commits": 0})
    for f in head_folds:
        for u, pick in f["test_map"].items():
            if pick is None:
                continue
            lab = cand_index[(u, pick[0], pick[1])]["labels"]
            per_src[uid_src[u]]["n_commits"] += 1
            per_src[uid_src[u]]["n_bs"] += int(bool(
                lab["beneficial_and_safe"]))
            per_src[uid_src[u]]["n_harmful"] += int(harmful_of_label(lab))
    n_noninf = 0
    detail = {}
    for src in sorted(set(uid_src.values())):
        b = per_src[src]
        t_bs = sum(int(bool(cand_index[(u, "tsicl", 1.0)]["labels"]
                            ["beneficial_and_safe"]))
                   for u in uids if uid_src[u] == src)
        t_harm = sum(int(harmful_of_label(
            cand_index[(u, "tsicl", 1.0)]["labels"]))
            for u in uids if uid_src[u] == src)
        noninf = bool(b["n_bs"] >= t_bs and b["n_harmful"] <= t_harm)
        n_noninf += int(noninf)
        detail[src] = {"bridge_bs": b["n_bs"], "tsicl_bs": t_bs,
                       "bridge_harmful": b["n_harmful"],
                       "tsicl_harmful": t_harm, "noninferior": noninf}
    gates2["g5_source_noninferiority"] = {
        **primary_gates["g5_source_noninferiority"],
        "n_noninferior": n_noninf, "per_source": detail,
        "pass": bool(n_noninf >= GATE_SOURCES_NONINFERIOR)}
    tsicl_bs = sum(int(bool(cand_index[(u, "tsicl", 1.0)]["labels"]
                            ["beneficial_and_safe"])) for u in uids)
    tsicl_harm = sum(int(harmful_of_label(
        cand_index[(u, "tsicl", 1.0)]["labels"])) for u in uids)
    pareto = bool((bs >= tsicl_bs and harm < tsicl_harm)
                  or (bs > tsicl_bs and harm == tsicl_harm))
    gates2["g6_pareto_vs_best_single_proposer"] = {
        **primary_gates["g6_pareto_vs_best_single_proposer"],
        "bridge": {"n_bs": bs, "n_harmful": harm}, "pass": pareto}
    branch.update({
        "executed": True,
        "rule": ("ONE pre-registered training: monotone isotonic heads on "
                 "the five normalised signals + R, model choice by "
                 "source-group DRO (worst train-source Brier); the fixed "
                 "grid/calibration protocol re-run once with the head score "
                 "as the risk score"),
        "folds": [{k: v for k, v in fr.items()
                   if k not in ("head", "fits")} for fr in fold_results],
        "pooled": {"n_commits": commits, "n_bs": bs, "n_harmful": harm,
                   "chr": chr_},
        "gates_after": gates2,
    })
    return branch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["candidates", "freeze", "evaluate"])
    args = ap.parse_args()
    if args.stage == "candidates":
        return run_candidates()
    if args.stage == "freeze":
        return run_freeze()
    if args.stage == "evaluate":
        return run_evaluate()
    raise SystemExit(f"unknown stage {args.stage}")


if __name__ == "__main__":
    sys.exit(main())
