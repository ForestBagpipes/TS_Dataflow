"""v3.8 Phase 1: IMPUTE_EXPLICIT explicit-missing operator probe.

Pre-registered in ``docs/v3_8_fact_preregistration.md`` §2 (operator and
certificate layer) and §4 (Phase-1 arms, gap-certificate tiers, integration
gates). CPU-only, API 0. Prototype lives entirely in ``experiments/``; no
``src/`` module is modified.

Operator contract (§2.1, §2.3):

  * touched mask = ``~isfinite(raw_series)`` exactly; finite flatlines,
    natural plateaus and inferred frozen runs are never in the mask;
  * no originally-finite observation is modified (observed-support drift is
    exactly 0, asserted per candidate);
  * linear interpolation between the gap's two finite anchors;
  * a raw-NaN run is certified only when it does NOT touch a window endpoint,
    has a finite anchor on both sides, and its length clears the tier cap;
  * gap-certificate tiers are FIXED before any held-out result is seen:
    tight <=4, medium <=8, wide <=16; gaps longer than 16 always abstain;
  * an abstained gap keeps the deployment KEEP value (the probe-materialised
    forward-fill, ``introact_ts.probe.materialize_for_probe``), so every
    output is fully finite.

Arm C (IMPUTE_EXPLICIT_LINEAR main variant) IS the wide tier: the only fixed
length cap defined in the pre-registration is 16, and the main variant carries
the widest certificate. Arm D reports the tier ladder tight/medium/wide, so
D-wide and C are the same candidate set by definition.

Arms (on the 445 windows that carry >= 1 IMPUTE candidate in Phase 0):
  A  current IMPUTE outputs (labels reused from
     results/v38_impute_mask_records.jsonl, one record per candidate);
  B  materialised KEEP / forward-fill (degenerate: gain exactly 0);
  C  IMPUTE_EXPLICIT_LINEAR (= wide tier);
  D  EXPLICIT x {tight, medium, wide} gap certificates;
  E  oracle candidate choice over A u C u D (upper bound only).

Labels use the v3.3 action-semantic path unchanged
(``experiments/v33_labels.py::compute_action_labels`` with family "IMPUTE":
KEEP counterfactual = materialize_for_probe(original), canonical uncentered
finite-mask NMSE, loss = damage(worse, discard_share), safe = loss <= 0.03,
beneficial = gain > 1e-9).

Gate populations (fixed here, before results):
  gates 1/2/4/5  actual-NaN windows (Phase-0 layer in
                 {actual_nan_only, mixed}), one wide candidate per window;
  gate 3         ALL EXPLICIT candidates of every tier on all 445 windows;
  gate 6         FACT pool = real candidate table minus every inherited
                 IMPUTE row, plus tight/medium/wide EXPLICIT candidates on
                 the actual-NaN windows (family IMPUTE_EXPLICIT; DENOISE and
                 DESPIKE unchanged; RESEGMENT closed), oracle = per-window
                 max-gain beneficial_and_safe, metrics via the v3.3
                 ``_episode_metrics`` definitions.

Usage:
    python experiments/v38_explicit_impute_probe.py --digest /tmp/v38_p1_a.json
    python experiments/v38_explicit_impute_probe.py            # full run
    python experiments/v38_explicit_impute_probe.py --no-tsfm  # skip TSFM gain
"""

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from metrics_common import canonical_nmse, ref_var  # noqa: E402
from v33_labels import compute_action_labels, hash_array  # noqa: E402
from v38_impute_mask_audit import (  # noqa: E402
    rebuild_corpus, verify_against_manifest, raw_nan_mask, mask_hash,
)
from introact_ts.actions import robust_scale, _mask_runs  # noqa: E402
from introact_ts.probe import materialize_for_probe, reference_scale  # noqa: E402
from introact_ts.contextual_shield import EPISODE_FAMILY_ORDER  # noqa: E402
from v32_compare_arms import PROTECTED_STRATA  # noqa: E402
import v33_compare_arms as v33  # noqa: E402

ROWS_PATH = ROOT / "results" / "v33_training_data.jsonl"
MANIFEST_PATH = ROOT / "results" / "p0_corpus_manifest_a.json"
REPLAY_PATH = ROOT / "results" / "v38_oracle_replay.json"
PHASE0_RECORDS = ROOT / "results" / "v38_impute_mask_records.jsonl"
FROZEN_V33 = ROOT / "results" / "v33_clean_rerun.json"
OUT_RECORDS = ROOT / "results" / "v38_explicit_impute_records.jsonl"
OUT_JSON = ROOT / "results" / "v38_explicit_impute_probe.json"

#: Gap certificate tiers, FIXED by the pre-registration (§4): internal gap
#: length <= tier cap; anything longer abstains. Never edited after seeing
#: held-out results.
GAP_CERT_TIERS = {"tight": 4, "medium": 8, "wide": 16}
MAIN_VARIANT = "wide"

HARM_LOSS = 0.03
GAIN_EPS = 1e-9
ACTUAL_NAN_LAYERS = ("actual_nan_only", "mixed")
EXPLICIT_FAMILY = "IMPUTE_EXPLICIT"
#: Families reachable by the FACT-pool unrestricted oracle: inherited IMPUTE
#: is removed, IMPUTE_EXPLICIT takes its place, RESEGMENT stays closed.
FACT_ALLOWED = ("DENOISE", "DESPIKE", EXPLICIT_FAMILY)

#: Gate thresholds (§4 / task contract), fixed before the run.
GATE_BS = 0.80
GATE_HARMFUL = 0.10
GATE_BENEFICIAL_WINDOWS = 30
GATE_SOURCES_NONINFERIOR = 4
GATE6 = {"bcov": 0.30, "gain": 0.10, "chr": 0.10, "pme": 0.0055,
         "damage": 0.0402}
#: Coverage-potential rule for the Phase-2B route (task contract).
P2B_BS = 0.60
P2B_HARMFUL = 0.25

TOL = 1e-9


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# -- the experimental operator ------------------------------------------------


def gap_certificate(x, max_gap):
    """Per raw-NaN run: certified for interpolation or the abstain reason.

    A run is certified iff it touches no window endpoint, has a finite anchor
    on both sides, and its length is <= ``max_gap``. For a maximal NaN run an
    in-range neighbour is finite by construction, so ``one_sided_anchor`` is
    only reachable at the endpoints (kept as a distinct reason for the
    contract) or when the whole window is NaN (``no_anchor``).
    """
    x = np.asarray(x, dtype=np.float64)
    T = len(x)
    nm = ~np.isfinite(x)
    out = []
    for lo, hi in _mask_runs(nm):
        left = bool(lo > 0 and np.isfinite(x[lo - 1]))
        right = bool(hi < T and np.isfinite(x[hi]))
        length = int(hi - lo)
        if not left and not right:
            certified, reason = False, "no_anchor"
        elif lo == 0 or hi == T:
            certified, reason = False, "boundary_gap"
        elif not (left and right):
            certified, reason = False, "one_sided_anchor"
        elif length > max_gap:
            certified, reason = False, "overlong_gap"
        else:
            certified, reason = True, None
        out.append({"lo": int(lo), "hi": int(hi), "length": length,
                    "left_anchor": left, "right_anchor": right,
                    "certified": certified, "abstain_reason": reason})
    return out


def impute_explicit_linear(series, max_gap=GAP_CERT_TIERS[MAIN_VARIANT]):
    """IMPUTE_EXPLICIT_LINEAR prototype (§2/§4 contract).

    Base output is the deployment KEEP (materialised forward-fill), so the
    result is always fully finite; each certified raw-NaN run is then
    overwritten by exact linear interpolation between its two anchors.
    Nothing outside the raw NaN mask is ever written.

    Returns a dict: series, declared touched mask (the raw NaN mask, bit
    exact), filled mask (subset actually interpolated), applicable (True iff
    at least one point was filled), and the per-gap certificate decisions.
    """
    x = np.asarray(series, dtype=np.float64)
    nm = ~np.isfinite(x)
    y = materialize_for_probe(x)
    decisions = gap_certificate(x, max_gap)
    filled = np.zeros(len(x), dtype=bool)
    for d in decisions:
        if not d["certified"]:
            continue
        lo, hi = d["lo"], d["hi"]
        a, b = x[lo - 1], x[hi]
        frac = np.arange(1, hi - lo + 1, dtype=np.float64) / (hi - lo + 1.0)
        y[lo:hi] = a + (b - a) * frac
        filled[lo:hi] = True
    obs = np.isfinite(x)
    assert np.array_equal(y[obs], x[obs]), "observed-support drift"
    assert bool(np.isfinite(y).all()), "output must be fully finite"
    return {
        "series": y,
        "touched": nm.copy(),
        "filled": filled,
        "applicable": bool(filled.any()),
        "gap_decisions": decisions,
        "n_filled": int(filled.sum()),
        "n_raw_nan": int(nm.sum()),
    }


def label_candidate(x, y, clean, touched):
    """The v3.3 action-semantic label path, unchanged (family "IMPUTE" so the
    KEEP counterfactual is materialize_for_probe(original))."""
    return compute_action_labels("IMPUTE", x, y, clean, touched=touched,
                                 params={})


def diagnostics(x, y, clean, res):
    """Mechanism diagnostics (never a replacement for canonical labels).

    missing-support NMSE/NRMSE: error restricted to raw NaN positions, before
    (materialised KEEP) and after, normalised by ref_var / robust_scale of the
    clean reference. observed-support drift: max |y - x| over originally
    finite positions (must be exactly 0). seam jump: |fill - anchor| at each
    certified gap edge, normalised by robust_scale of the raw window. filled
    fraction: filled / raw-NaN points.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    c = np.asarray(clean, dtype=np.float64)
    nm = ~np.isfinite(x)
    xk = materialize_for_probe(x)
    rv = ref_var(c)
    scale = robust_scale(c)
    out = {}
    if nm.any():
        mse_b = float(np.mean((xk[nm] - c[nm]) ** 2))
        mse_a = float(np.mean((y[nm] - c[nm]) ** 2))
        out["missing_support_nmse_before"] = mse_b / rv if rv >= 1e-12 else mse_b
        out["missing_support_nmse_after"] = mse_a / rv if rv >= 1e-12 else mse_a
        out["missing_support_nrmse_before"] = float(np.sqrt(mse_b)) / scale
        out["missing_support_nrmse_after"] = float(np.sqrt(mse_a)) / scale
    else:
        out["missing_support_nmse_before"] = None
        out["missing_support_nmse_after"] = None
        out["missing_support_nrmse_before"] = None
        out["missing_support_nrmse_after"] = None
    obs = np.isfinite(x)
    out["observed_support_drift"] = (
        float(np.max(np.abs(y[obs] - x[obs]))) if obs.any() else 0.0)
    wscale = robust_scale(x)
    seams = []
    for d in res["gap_decisions"]:
        if not d["certified"]:
            continue
        lo, hi = d["lo"], d["hi"]
        seams.append(abs(float(y[lo]) - float(x[lo - 1])) / wscale)
        seams.append(abs(float(y[hi - 1]) - float(x[hi])) / wscale)
    out["seam_jump_max"] = float(max(seams)) if seams else 0.0
    out["seam_jump_mean"] = float(np.mean(seams)) if seams else 0.0
    out["filled_fraction"] = (res["n_filled"] / res["n_raw_nan"]
                              if res["n_raw_nan"] else 0.0)
    return out


# -- per-window candidate construction -----------------------------------------


def process_window(task):
    """Arms B/C/D candidates for one of the 445 IMPUTE-candidate windows."""
    uid, series, clean, meta = task
    x = np.asarray(series, dtype=np.float64)
    c = np.asarray(clean, dtype=np.float64)
    nm = raw_nan_mask(x)
    recs = []

    # Arm B: materialised KEEP / forward-fill. By construction y == the KEEP
    # counterfactual, so the label path must yield gain exactly 0.
    y_keep = materialize_for_probe(x)
    lab = label_candidate(x, y_keep, c, None)
    assert abs(lab["true_repair_gain"]) <= 1e-12, "KEEP arm must have gain 0"
    recs.append({
        "sample_uid": uid, **meta,
        "arm": "B", "family": "KEEP_MATERIALIZED", "variant": "keep_ff",
        "rung": "keep",
        "params": {"method": "forward_fill"},
        "applicable": True,
        "n_raw_nan": int(nm.sum()), "n_filled": 0,
        "gap_decisions": [], "abstain_reasons": {},
        "labels": lab,
        "diag": None,
        "output_hash": hash_array(y_keep),
        "touched_mask_hash": None,
        "filled_mask_hash": None,
    })

    # Arms C/D: EXPLICIT x tier ladder (wide IS arm C, the main variant).
    for tier, cap in GAP_CERT_TIERS.items():
        res = impute_explicit_linear(x, max_gap=cap)
        lab = label_candidate(x, res["series"], c, res["touched"])
        diag = diagnostics(x, res["series"], c, res)
        reasons = Counter(d["abstain_reason"] for d in res["gap_decisions"]
                          if not d["certified"])
        recs.append({
            "sample_uid": uid, **meta,
            "arm": ("C" if tier == MAIN_VARIANT else "D"),
            "family": EXPLICIT_FAMILY, "variant": tier,
            "rung": f"explicit_{tier}",
            "params": {"method": "explicit_linear", "max_gap": cap},
            "applicable": bool(res["applicable"]),
            "n_raw_nan": res["n_raw_nan"], "n_filled": res["n_filled"],
            "gap_decisions": res["gap_decisions"],
            "abstain_reasons": dict(reasons),
            "labels": lab,
            "diag": diag,
            "output_hash": hash_array(res["series"]),
            "touched_mask_hash": mask_hash(res["touched"]),
            "filled_mask_hash": mask_hash(res["filled"]),
        })
    return recs


# -- aggregations ---------------------------------------------------------------


def _cand_stats(labels_iter):
    rows = list(labels_iter)
    if not rows:
        return {"n_candidates": 0}
    gains = [r["true_repair_gain"] for r in rows]
    losses = [r["true_loss"] for r in rows]
    return {
        "n_candidates": len(rows),
        "bs_rate": float(np.mean([bool(r["beneficial_and_safe"])
                                  for r in rows])),
        "harmful_rate": float(np.mean([r["true_loss"] > HARM_LOSS
                                       for r in rows])),
        "mean_gain": float(np.mean(gains)),
        "median_gain": float(np.median(gains)),
        "mean_loss": float(np.mean(losses)),
        "median_loss": float(np.median(losses)),
        "n_beneficial_unique_windows":
            len({r["sample_uid"] for r in rows if r["beneficial"]}),
    }


def _window_oracle(by_uid_rows):
    """Per-window max-gain b&s pick over contaminated windows."""
    cont = {uid: rs for uid, rs in by_uid_rows.items()
            if rs[0]["stratum"] == "contaminated"}
    if not cont:
        return {"n_contaminated_windows": 0, "bcov": None, "gain": None,
                "n_oracle_commits": 0, "picks": {}}
    improved, gains, picks = [], [], {}
    for uid, rs in sorted(cont.items()):
        bs = [r for r in rs if r["beneficial_and_safe"]]
        if bs:
            best = max(bs, key=lambda r: r["true_repair_gain"])
            improved.append(1.0)
            gains.append(float(best["true_repair_gain"]))
            picks[uid] = best.get("variant", best.get("family"))
        else:
            improved.append(0.0)
            gains.append(0.0)
    return {"n_contaminated_windows": len(cont),
            "bcov": float(np.mean(improved)),
            "gain": float(np.mean(gains)),
            "n_oracle_commits": int(sum(improved)),
            "picks": picks}


def _flat_labels(r):
    """Uniform label view for Phase-0 records and new candidates."""
    lab = r["eval_labels"] if "eval_labels" in r else r["labels"]
    return {"sample_uid": r["sample_uid"], "stratum": r["stratum"],
            "true_repair_gain": float(lab["true_repair_gain"]),
            "true_loss": float(lab["true_loss"]),
            "beneficial": bool(lab["beneficial"]),
            "beneficial_and_safe": bool(lab["beneficial_and_safe"])}


def arm_tables(impute_recs_p0, new_recs):
    """Five-arm comparison on the 445 IMPUTE-candidate windows."""
    arms = {}
    a_rows = [_flat_labels(r) for r in impute_recs_p0]
    arms["A_current_IMPUTE"] = a_rows
    for key, variant in (("B_materialized_KEEP", "keep_ff"),
                         ("C_EXPLICIT_LINEAR_wide", MAIN_VARIANT),
                         ("D_EXPLICIT_tight", "tight"),
                         ("D_EXPLICIT_medium", "medium"),
                         ("D_EXPLICIT_wide", MAIN_VARIANT)):
        arms[key] = [_flat_labels(r) for r in new_recs
                     if r["variant"] == variant]
    out = {}
    for name, rows in arms.items():
        by_uid = defaultdict(list)
        for r in rows:
            by_uid[r["sample_uid"]].append(r)
        out[name] = {**_cand_stats(rows),
                     "n_unique_windows": len(by_uid),
                     "window_oracle": {k: v for k, v in
                                       _window_oracle(by_uid).items()
                                       if k != "picks"}}
    # Arm E: oracle over the union A u C u D (upper bound).
    union = defaultdict(list)
    for name, rows in arms.items():
        if name == "B_materialized_KEEP":
            continue
        for r in rows:
            rr = dict(r)
            rr["variant"] = name
            union[rr["sample_uid"]].append(rr)
    e = _window_oracle(union)
    out["E_oracle_candidate_choice"] = {
        "n_candidates": sum(len(v) for v in union.values()),
        "n_unique_windows": len(union),
        "window_oracle": {k: v for k, v in e.items() if k != "picks"},
        "pick_composition": dict(Counter(e["picks"].values())),
        "note": "upper bound only: per-window max-gain beneficial_and_safe "
                "over A u C u D candidates",
    }
    return out


def stratified(impute_recs_p0, new_recs):
    """Candidate-level rates by layer / source / true corruption / rung."""
    def _group(rows, keyfn):
        g = defaultdict(list)
        for r in rows:
            g[keyfn(r)].append(_flat_labels(r))
        return {k: _cand_stats(v) for k, v in sorted(g.items())}

    out = {}
    a = [r for r in impute_recs_p0]
    out["A_current_IMPUTE"] = {
        "by_layer": _group(a, lambda r: r["layer"]),
        "by_source": _group(a, lambda r: r["dataset"]),
        "by_true_corruption": _group(a, lambda r: r["true_kind"]),
        "by_rung": _group(a, lambda r: r["rung"]),
    }
    for variant in ("keep_ff", "tight", "medium", MAIN_VARIANT):
        rows = [r for r in new_recs if r["variant"] == variant]
        out[f"EXPLICIT_{variant}"] = {
            "by_layer": _group(rows, lambda r: r["layer"]),
            "by_source": _group(rows, lambda r: r["dataset"]),
            "by_true_corruption": _group(rows, lambda r: r["true_kind"]),
        }
    return out


# -- FACT pool unrestricted oracle (gate 6) --------------------------------------


def fact_pool_rows(real_rows, new_recs, actual_nan_uids):
    """Existing pool minus inherited IMPUTE, plus EXPLICIT candidates on the
    actual-NaN windows. DENOISE/DESPIKE unchanged; RESEGMENT stays closed.

    Windows whose only candidates were inherited IMPUTE would silently drop
    out of the evaluation frame; they are kept as no-commit windows via a
    KEEP placeholder row (never oracle-reachable), so the oracle denominator
    stays the full 771-window frame of the frozen v3.3 metrics."""
    base = [r for r in real_rows if r["family"] != "IMPUTE"]
    added = []
    for r in new_recs:
        if r["family"] != EXPLICIT_FAMILY:
            continue
        if r["sample_uid"] not in actual_nan_uids:
            continue
        lab = r["labels"]
        added.append({
            "sample_uid": r["sample_uid"], "dataset": r["dataset"],
            "stratum": r["stratum"], "true_kind": r["true_kind"],
            "corrupted_hash": r["corrupted_hash"],
            "family": EXPLICIT_FAMILY, "rung": r["rung"],
            "params": r["params"],
            "true_loss": float(lab["true_loss"]),
            "true_repair_gain": float(lab["true_repair_gain"]),
            "beneficial": float(lab["beneficial"]),
            "beneficial_and_safe": float(lab["beneficial_and_safe"]),
        })
    kept_uids = {r["sample_uid"] for r in base} | set(actual_nan_uids)
    placeholders = []
    seen = {}
    for r in real_rows:
        uid = r["sample_uid"]
        if uid in kept_uids or uid in seen:
            continue
        seen[uid] = True
        placeholders.append({
            "sample_uid": uid, "dataset": r["dataset"],
            "stratum": r["stratum"], "true_kind": r["true_kind"],
            "corrupted_hash": r["corrupted_hash"],
            "family": "KEEP", "rung": "keep", "params": {},
            "true_loss": 0.0, "true_repair_gain": 0.0,
            "beneficial": 0.0, "beneficial_and_safe": 0.0,
        })
    return base + added + placeholders, len(base), len(added), \
        len(placeholders)


def unrestricted_oracle(rows, allowed):
    """Per-window max-gain beneficial_and_safe pick (v3.3 rule), then the
    v3.3 _episode_metrics definitions. ``allowed`` replaces
    EPISODE_FAMILY_ORDER membership (RESEGMENT closed in both)."""
    by_uid = defaultdict(list)
    for r in rows:
        by_uid[r["sample_uid"]].append(r)
    committed = {}
    for uid, rs in by_uid.items():
        bs = [r for r in rs
              if r["beneficial_and_safe"] and r["family"] in allowed]
        pick = max(bs, key=lambda r: r["true_repair_gain"]) if bs else None
        committed[uid] = ((pick, rs.index(pick), "oracle", None)
                          if pick is not None else None)
    return v33._episode_metrics(rows, committed)


def fact_oracle_report(real_rows, new_recs, actual_nan_uids, frozen_oracle):
    fact_rows, n_base, n_added, n_placeholder = fact_pool_rows(
        real_rows, new_recs, actual_nan_uids)
    met = unrestricted_oracle(fact_rows, FACT_ALLOWED)
    headline = {
        "bcov": float(met["beneficial_coverage"]),
        "gain": float(met["mean_repair_gain_contaminated"]),
        "chr": float(met["conditional_harm_rate"]),
        "pme": float(met["protected_mis_edit_rate"]),
        "damage": float(met["damage"]),
        "n_windows": int(met["n_windows"]),
        "committed": int(met["committed"]),
        "commit_by_family": dict(Counter(
            r["family"] for r in
            _committed_picks(fact_rows, FACT_ALLOWED).values()
            if r is not None)),
    }
    # Integrity cross-check: the same code path on the ORIGINAL pool must
    # reproduce the frozen v3.3 unrestricted oracle within 1e-9.
    ref_met = unrestricted_oracle(real_rows, EPISODE_FAMILY_ORDER)
    xcheck = {}
    ok = True
    for got_k, ref_k in (("beneficial_coverage", "bcov"),
                         ("mean_repair_gain_contaminated", "gain"),
                         ("conditional_harm_rate", "chr"),
                         ("protected_mis_edit_rate", "pme"),
                         ("damage", "damage")):
        got, ref = float(ref_met[got_k]), float(frozen_oracle[
            {"bcov": "beneficial_coverage",
             "gain": "mean_repair_gain_contaminated",
             "chr": "conditional_harm_rate",
             "pme": "protected_mis_edit_rate",
             "damage": "damage"}[ref_k]])
        d = abs(got - ref)
        xcheck[ref_k] = {"got": got, "ref": ref, "abs_diff": d,
                         "ok": bool(d < TOL)}
        ok = ok and d < TOL
    return headline, {"pool": {"n_rows": len(fact_rows),
                               "n_base_non_impute": n_base,
                               "n_explicit_added": n_added,
                               "n_keep_placeholders": n_placeholder,
                               "frame": "all 771 real windows; windows left "
                                        "without candidates stay in the "
                                        "frame as no-commit KEEP "
                                        "placeholders",
                               "allowed_families": list(FACT_ALLOWED)},
                      "original_pool_xcheck": xcheck,
                      "original_pool_xcheck_pass": bool(ok)}


def _committed_picks(rows, allowed):
    by_uid = defaultdict(list)
    for r in rows:
        by_uid[r["sample_uid"]].append(r)
    out = {}
    for uid, rs in by_uid.items():
        bs = [r for r in rs
              if r["beneficial_and_safe"] and r["family"] in allowed]
        out[uid] = (max(bs, key=lambda r: r["true_repair_gain"])
                    if bs else None)
    return out


# -- downstream TSFM gain (subset) ----------------------------------------------


def tsfm_gain_subset(tasks_by_uid, wide_by_uid, n_subset, device="cpu"):
    """probe_window utility delta of the wide output vs the raw window (whose
    probed form IS the materialised KEEP), judge-only, on a stratified subset.

    Scope (documented, diagnostic only): actual-NaN windows where the wide
    variant filled >= 1 point, evenly spaced within each source, at most
    ceil(n_subset/6) per source. Backend = the pipeline's curation judge
    (chronos bolt-base, first entry of the multi-family preset), CPU.
    """
    from introact_ts.backends import PRESETS, make_pool
    from introact_ts.probe import probe_window

    eligible = defaultdict(list)
    for uid, rec in wide_by_uid.items():
        if rec["layer"] in ACTUAL_NAN_LAYERS and rec["n_filled"] > 0:
            eligible[rec["dataset"]].append(uid)
    per_src = max(1, -(-n_subset // 6))
    chosen = []
    for ds in sorted(eligible):
        uids = sorted(eligible[ds])
        if len(uids) > per_src:
            idx = np.linspace(0, len(uids) - 1, per_src).astype(int)
            uids = [uids[i] for i in sorted(set(idx))]
        chosen.extend(uids)

    models = make_pool([PRESETS["multi-family"]["curation"][0]],
                       device=device)
    rows = []
    t0 = time.time()
    for i, uid in enumerate(sorted(chosen)):
        _, series, clean, meta = tasks_by_uid[uid]
        x = np.asarray(series, dtype=np.float64)
        y = np.asarray(
            impute_explicit_linear(x, GAP_CERT_TIERS[MAIN_VARIANT])["series"],
            dtype=np.float64)
        scale = reference_scale(x)
        u_before = probe_window(x, models, scale).utility
        u_after = probe_window(y, models, scale).utility
        rows.append({"sample_uid": uid, "dataset": meta["dataset"],
                     "layer": meta["layer"],
                     "utility_before": float(u_before),
                     "utility_after": float(u_after),
                     "tsfm_gain": float(u_after - u_before)})
        print(f"[tsfm {i + 1}/{len(chosen)}] {meta['dataset']} "
              f"du={u_after - u_before:+.4f} "
              f"({time.time() - t0:.0f}s elapsed)", flush=True)
    gains = [r["tsfm_gain"] for r in rows]
    return {
        "scope": {
            "backend": "chronos:amazon/chronos-bolt-base (judge of the "
                       "multi-family curation preset), judge-only probe, CPU",
            "definition": "probe_window(wide_output).utility - "
                          "probe_window(raw_window).utility; the raw window "
                          "is materialised (forward-filled) inside "
                          "probe_window, so the baseline IS arm B",
            "selection": ("actual-NaN windows with wide n_filled>0, evenly "
                          "spaced per source, <= ceil(n_subset/6) per source"),
            "n_requested": n_subset,
        },
        "n_windows": len(rows),
        "mean_gain": float(np.mean(gains)) if gains else None,
        "median_gain": float(np.median(gains)) if gains else None,
        "frac_positive": float(np.mean([g > 0 for g in gains]))
        if gains else None,
        "per_window": rows,
        "runtime_sec": time.time() - t0,
    }


# -- digest (two-process determinism gate) ---------------------------------------


def digest_of_records(recs):
    slim = sorted(({"sample_uid": r["sample_uid"], "variant": r["variant"],
                    "output_hash": r["output_hash"],
                    "gain": round(r["labels"]["true_repair_gain"], 12),
                    "loss": round(r["labels"]["true_loss"], 12)}
                   for r in recs),
                  key=lambda r: (r["sample_uid"], r["variant"]))
    blob = json.dumps(slim, sort_keys=True).encode("utf-8")
    return {"n_records": len(slim),
            "sha256": hashlib.sha256(blob).hexdigest(), "records": slim}


def synthetic_battery_digest():
    """Fixed synthetic battery -> sha256 of operator outputs.

    Used by the two-process determinism test; self-contained (no corpus)."""
    specs = []
    rng = np.random.RandomState(20260903)
    t = np.arange(128, dtype=np.float64)
    base = np.sin(2 * np.pi * t / 16.0) + 0.05 * rng.randn(128)
    for gaps in (((10, 14), (40, 44), (90, 100)),
                 ((0, 6), (60, 63)),
                 ((120, 128), (30, 50)),
                 ((20, 21),)):
        x = base.copy()
        for lo, hi in gaps:
            x[lo:hi] = np.nan
        specs.append(x)
    x = base.copy()
    x[50:80] = x[49]  # finite flatline run, must never be touched
    specs.append(x)
    out = []
    for x in specs:
        for tier, cap in sorted(GAP_CERT_TIERS.items()):
            res = impute_explicit_linear(x, cap)
            out.append({"tier": tier, "output_hash": hash_array(res["series"]),
                        "filled": res["filled"].tobytes().hex()})
    blob = json.dumps(out, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# -- main -------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--digest", default=None,
                    help="digest-only mode: full-candidate digest, no TSFM")
    ap.add_argument("--no-tsfm", action="store_true")
    ap.add_argument("--tsfm-subset", type=int, default=24)
    ap.add_argument("--tsfm-device", default="cpu")
    args = ap.parse_args()

    t0 = time.time()

    # Gate 0: Phase-0 replay must have passed.
    rep = json.load(REPLAY_PATH.open(encoding="utf-8"))
    replay_pass = bool(rep.get("all_replays_pass"))
    print(f"[gate replay] pass={replay_pass}", flush=True)
    if not replay_pass:
        print("[FATAL] Phase-0 replay gate failed; Phase-1 conclusions void",
              flush=True)
        return 1

    # Rebuild + verify the raw corpus (same discipline as Phase 0).
    t1 = time.time()
    recs, dropped = rebuild_corpus()
    print(f"[rebuild] {len(recs)} windows in {time.time() - t1:.1f}s",
          flush=True)
    manifest = json.load(MANIFEST_PATH.open(encoding="utf-8"))
    uid_gate = verify_against_manifest(recs, manifest)
    print(f"[gate uids] pass={uid_gate['pass']}", flush=True)
    if not uid_gate["pass"]:
        return 1

    # Phase-0 IMPUTE records define the 445 windows and their layers.
    p0 = [json.loads(l) for l in PHASE0_RECORDS.open(encoding="utf-8")]
    win_meta = {}
    for r in p0:
        win_meta.setdefault(r["sample_uid"], {
            "dataset": r["dataset"], "stratum": r["stratum"],
            "true_kind": r["true_kind"], "layer": r["layer"],
            "corrupted_hash": r["corrupted_hash"]})
    print(f"[phase0] {len(p0)} IMPUTE candidates, "
          f"{len(win_meta)} unique windows", flush=True)

    rebuilt = {r["sample_uid"]: r for r in recs}
    missing = [uid for uid in win_meta if uid not in rebuilt]
    if missing:
        print(f"[FATAL] {len(missing)} candidate windows not rebuilt",
              flush=True)
        return 1
    tasks = []
    for uid in sorted(win_meta):
        w = rebuilt[uid]
        assert w["corrupted_hash"] == win_meta[uid]["corrupted_hash"]
        tasks.append((uid, w["series"],
                      np.asarray(w["window"].clean_series, dtype=np.float64),
                      win_meta[uid]))

    t2 = time.time()
    new_recs = []
    for task in tasks:
        new_recs.extend(process_window(task))
    print(f"[candidates] {len(new_recs)} new candidates "
          f"(B + 3 tiers x {len(tasks)} windows) in "
          f"{time.time() - t2:.1f}s", flush=True)

    # Hard certificate assertions over every EXPLICIT candidate.
    nmismatch_touched = 0
    max_drift = 0.0
    for r in new_recs:
        if r["family"] != EXPLICIT_FAMILY:
            continue
        uid = r["sample_uid"]
        x = np.asarray(rebuilt[uid]["series"], dtype=np.float64)
        nm = raw_nan_mask(x)
        if mask_hash(nm) != r["touched_mask_hash"]:
            nmismatch_touched += 1
        max_drift = max(max_drift, r["diag"]["observed_support_drift"])
    print(f"[certificate] touched!=raw_nan: {nmismatch_touched}, "
          f"max observed drift: {max_drift}", flush=True)

    if args.digest:
        dig = digest_of_records(new_recs)
        payload = {"phase": "v3.8 Phase 1 digest", "n_windows": len(tasks),
                   **{k: v for k, v in dig.items() if k != "records"},
                   "records": dig["records"],
                   "runtime_sec": time.time() - t0}
        with open(args.digest, "w", encoding="utf-8") as f:
            json.dump(payload, f, sort_keys=True)
        print(f"[digest] sha256={dig['sha256']} -> {args.digest}", flush=True)
        print("___V38_EXPLICIT_DIGEST_DONE___", flush=True)
        return 0

    with OUT_RECORDS.open("w", encoding="utf-8") as f:
        for r in sorted(new_recs,
                        key=lambda r: (r["sample_uid"], r["variant"])):
            f.write(json.dumps(r, sort_keys=True, default=str) + "\n")
    print(f"[records] {len(new_recs)} -> {OUT_RECORDS.name}", flush=True)

    # Five-arm comparison + stratification.
    arms = arm_tables(p0, new_recs)
    strata = stratified(p0, new_recs)

    # Abstain reason distribution (per tier, gap level and window level).
    abstain = {}
    for tier in ("tight", "medium", MAIN_VARIANT):
        rows = [r for r in new_recs if r["variant"] == tier]
        gap_reasons = Counter()
        for r in rows:
            gap_reasons.update(r["abstain_reasons"])
        win_no_fill = Counter()
        for r in rows:
            if r["n_raw_nan"] == 0:
                win_no_fill["no_raw_nan"] += 1
            elif r["n_filled"] == 0:
                win_no_fill["all_gaps_abstained"] += 1
            elif r["n_filled"] < r["n_raw_nan"]:
                win_no_fill["partial_fill"] += 1
            else:
                win_no_fill["full_fill"] += 1
        abstain[tier] = {"gap_level": dict(gap_reasons),
                         "window_level": dict(win_no_fill)}

    # Diagnostic aggregates per tier.
    diag_agg = {}
    for tier in ("tight", "medium", MAIN_VARIANT):
        rows = [r for r in new_recs
                if r["variant"] == tier and r["n_raw_nan"] > 0]
        if not rows:
            continue
        d = [r["diag"] for r in rows]
        diag_agg[tier] = {
            "n_windows_with_raw_nan": len(rows),
            "missing_support_nmse_before_mean":
                float(np.mean([x["missing_support_nmse_before"]
                               for x in d])),
            "missing_support_nmse_after_mean":
                float(np.mean([x["missing_support_nmse_after"] for x in d])),
            "missing_support_nrmse_after_median":
                float(np.median([x["missing_support_nrmse_after"]
                                 for x in d])),
            "observed_support_drift_max":
                float(max(x["observed_support_drift"] for x in d)),
            "seam_jump_mean":
                float(np.mean([x["seam_jump_mean"] for x in d])),
            "seam_jump_max":
                float(max(x["seam_jump_max"] for x in d)),
            "filled_fraction_mean":
                float(np.mean([x["filled_fraction"] for x in d])),
        }

    # -- integration gates (wide = main variant) --------------------------------
    uid_layer = {uid: m["layer"] for uid, m in win_meta.items()}
    actual_nan_uids = {uid for uid, l in uid_layer.items()
                       if l in ACTUAL_NAN_LAYERS}
    wide = [r for r in new_recs
            if r["variant"] == MAIN_VARIANT
            and r["sample_uid"] in actual_nan_uids]
    wide_labels = [_flat_labels(r) for r in wide]
    a_on_actual = [_flat_labels(r) for r in p0
                   if r["sample_uid"] in actual_nan_uids]

    g1_stats = _cand_stats(wide_labels)
    gates = {}
    gates["g1_bs_rate_actual_nan"] = {
        "rule": f"b&s rate of the wide variant on actual-NaN windows "
                f"(layers {ACTUAL_NAN_LAYERS}) >= {GATE_BS}",
        "value": g1_stats["bs_rate"], "threshold": GATE_BS,
        "n_candidates": g1_stats["n_candidates"],
        "pass": bool(g1_stats["bs_rate"] >= GATE_BS)}
    gates["g2_harmful_rate_actual_nan"] = {
        "rule": f"harmful rate (true_loss > {HARM_LOSS}) of the wide variant "
                f"on actual-NaN windows <= {GATE_HARMFUL}",
        "value": g1_stats["harmful_rate"], "threshold": GATE_HARMFUL,
        "pass": bool(g1_stats["harmful_rate"] <= GATE_HARMFUL)}
    gates["g3_observed_drift_zero"] = {
        "rule": "observed-support drift exactly 0 for every EXPLICIT "
                "candidate (all tiers, all 445 windows)",
        "max_drift": max_drift, "n_checked": sum(
            1 for r in new_recs if r["family"] == EXPLICIT_FAMILY),
        "pass": bool(max_drift == 0.0 and nmismatch_touched == 0)}
    gates["g4_beneficial_unique_windows"] = {
        "rule": f">= {GATE_BENEFICIAL_WINDOWS} unique actual-NaN windows with "
                f"a beneficial wide candidate",
        "value": g1_stats["n_beneficial_unique_windows"],
        "threshold": GATE_BENEFICIAL_WINDOWS,
        "pass": bool(g1_stats["n_beneficial_unique_windows"]
                     >= GATE_BENEFICIAL_WINDOWS)}

    by_src_wide = defaultdict(list)
    for r in wide_labels:
        by_src_wide[win_meta[r["sample_uid"]]["dataset"]].append(r)
    by_src_a = defaultdict(list)
    for r in a_on_actual:
        by_src_a[win_meta[r["sample_uid"]]["dataset"]].append(r)
    src_detail = {}
    n_noninferior = 0
    for ds in sorted(set(by_src_wide) | set(by_src_a)):
        sw = _cand_stats(by_src_wide.get(ds, []))
        sa = _cand_stats(by_src_a.get(ds, []))
        noninf = bool(sw.get("bs_rate", 0.0) >= sa.get("bs_rate", 1.0)
                      and sw.get("harmful_rate", 1.0)
                      <= sa.get("harmful_rate", 0.0))
        n_noninferior += int(noninf)
        src_detail[ds] = {"wide_bs": sw.get("bs_rate"),
                          "impute_bs": sa.get("bs_rate"),
                          "wide_harmful": sw.get("harmful_rate"),
                          "impute_harmful": sa.get("harmful_rate"),
                          "n_wide": sw.get("n_candidates", 0),
                          "n_impute": sa.get("n_candidates", 0),
                          "noninferior": noninf}
    gates["g5_source_noninferiority"] = {
        "rule": f">= {GATE_SOURCES_NONINFERIOR}/6 sources with "
                f"bs_wide >= bs_IMPUTE AND harmful_wide <= harmful_IMPUTE "
                f"(candidate-level rates on the source's actual-NaN windows)",
        "n_noninferior": n_noninferior,
        "threshold": GATE_SOURCES_NONINFERIOR,
        "per_source": src_detail,
        "pass": bool(n_noninferior >= GATE_SOURCES_NONINFERIOR)}

    rows_all = v33._load_rows(str(ROWS_PATH))
    real = [r for r in rows_all if not r["dataset"].startswith("ood:")]
    frozen_oracle = json.load(FROZEN_V33.open(
        encoding="utf-8"))["arms"]["oracle_relabel"]
    fact_head, fact_extra = fact_oracle_report(real, new_recs,
                                               actual_nan_uids,
                                               frozen_oracle)
    g6_checks = {
        "bcov": {"value": fact_head["bcov"], "op": ">=",
                 "threshold": GATE6["bcov"],
                 "pass": bool(fact_head["bcov"] >= GATE6["bcov"])},
        "gain": {"value": fact_head["gain"], "op": ">=",
                 "threshold": GATE6["gain"],
                 "pass": bool(fact_head["gain"] >= GATE6["gain"])},
        "chr": {"value": fact_head["chr"], "op": "<=",
                "threshold": GATE6["chr"],
                "pass": bool(fact_head["chr"] <= GATE6["chr"])},
        "pme": {"value": fact_head["pme"], "op": "<=",
                "threshold": GATE6["pme"],
                "pass": bool(fact_head["pme"] <= GATE6["pme"])},
        "damage": {"value": fact_head["damage"], "op": "<=",
                   "threshold": GATE6["damage"],
                   "pass": bool(fact_head["damage"] <= GATE6["damage"])},
    }
    gates["g6_fact_pool_unrestricted_oracle"] = {
        "rule": "FACT pool (inherited IMPUTE removed; IMPUTE_EXPLICIT "
                "tight/medium/wide added on actual-NaN windows; "
                "DENOISE/DESPIKE unchanged; RESEGMENT closed; windows left "
                "without candidates kept as no-commit KEEP placeholders so "
                "the frame stays the frozen 771 real windows) unrestricted "
                "per-window max-gain b&s oracle must reach bcov>=0.30, "
                "gain>=0.10, CHR<=0.10, pme<=0.0055, damage<=0.0402",
        "checks": g6_checks,
        "headline": fact_head,
        "pool": fact_extra["pool"],
        "original_pool_xcheck_pass":
            fact_extra["original_pool_xcheck_pass"],
        "pass": bool(all(c["pass"] for c in g6_checks.values())
                     and fact_extra["original_pool_xcheck_pass"])}

    all_pass = all(g["pass"] for g in gates.values())
    coverage_potential = bool(g1_stats["bs_rate"] >= P2B_BS
                              and g1_stats["harmful_rate"] <= P2B_HARMFUL)
    if all_pass:
        verdict = "candidate_headroom_reached"  # -> Phase 2A
    elif coverage_potential:
        verdict = "coverage_potential_route_to_phase2B_adapter"
    else:
        verdict = "operator_retired"
    gates_verdict = {
        "all_pass": bool(all_pass),
        "coverage_potential_rule":
            f"wide b&s >= {P2B_BS} and harmful <= {P2B_HARMFUL} on "
            f"actual-NaN windows (applies when any of gates 1-5 fails)",
        "coverage_potential": coverage_potential,
        "verdict": verdict,
    }
    print(f"[gates] { {k: v['pass'] for k, v in gates.items()} } "
          f"verdict={verdict}", flush=True)

    # Downstream TSFM gain (diagnostic subset).
    tsfm = {"skipped": True}
    if not args.no_tsfm:
        tasks_by_uid = {t[0]: t for t in tasks}
        wide_by_uid = {r["sample_uid"]: r for r in new_recs
                       if r["variant"] == MAIN_VARIANT}
        tsfm = tsfm_gain_subset(tasks_by_uid, wide_by_uid,
                                args.tsfm_subset, device=args.tsfm_device)

    dig = digest_of_records(new_recs)
    out = {
        "phase": "v3.8 Phase 1: IMPUTE_EXPLICIT explicit-missing operator "
                 "probe (docs/v3_8_fact_preregistration.md §2, §4)",
        "definitions": {
            "operator": "touched = ~isfinite(raw) exactly; observed support "
                        "never modified; linear interpolation between two "
                        "finite anchors; certified gaps only",
            "gap_certificate_tiers": GAP_CERT_TIERS,
            "tiers_frozen": ("fixed by the pre-registration before any "
                             "held-out result was seen"),
            "main_variant": ("wide (arm C IS the wide tier; the only fixed "
                             "length cap defined in §4 is 16)"),
            "abstain_output": "deployment KEEP (materialize_for_probe "
                              "forward-fill), so every output is finite",
            "label_path": "experiments/v33_labels.py::compute_action_labels "
                          "with family 'IMPUTE' (materialised KEEP "
                          "counterfactual, canonical uncentered finite-mask "
                          "NMSE, loss=damage(worse, discard), safe<=0.03, "
                          "beneficial gain>1e-9)",
            "harmful": f"true_loss > {HARM_LOSS}",
            "gate_populations": "gates 1/2/4/5 on actual-NaN windows "
                                "(actual_nan_only + mixed); gate 3 on all "
                                "EXPLICIT candidates; gate 6 on the FACT pool",
        },
        "integrity": {
            "phase0_replay_pass": replay_pass,
            "corpus_manifest_gate": uid_gate,
            "touched_mask_mismatches": nmismatch_touched,
            "records_digest_sha256": dig["sha256"],
            "synthetic_battery_sha256": synthetic_battery_digest(),
        },
        "n_windows_with_impute_candidate": len(tasks),
        "n_new_candidates": len(new_recs),
        "arms": arms,
        "stratified": strata,
        "diagnostics_by_tier": diag_agg,
        "abstain_reasons": abstain,
        "downstream_tsfm_gain": tsfm,
        "gates": gates,
        "gates_verdict": gates_verdict,
        "input_hashes": {
            "v33_training_data": _sha256(ROWS_PATH),
            "p0_corpus_manifest_a": _sha256(MANIFEST_PATH),
            "v38_oracle_replay": _sha256(REPLAY_PATH),
            "v38_impute_mask_records": _sha256(PHASE0_RECORDS),
            "v33_clean_rerun": _sha256(FROZEN_V33),
        },
        "code_hashes": {
            "experiments/v38_explicit_impute_probe.py": _sha256(
                Path(__file__).resolve()),
            "experiments/v33_labels.py": _sha256(
                ROOT / "experiments" / "v33_labels.py"),
            "src/introact_ts/probe.py": _sha256(
                ROOT / "src" / "introact_ts" / "probe.py"),
            "src/introact_ts/actions.py": _sha256(
                ROOT / "src" / "introact_ts" / "actions.py"),
        },
        "output_sha256": {
            "results/v38_explicit_impute_records.jsonl":
                _sha256(OUT_RECORDS),
        },
        "runtime_sec": time.time() - t0,
    }
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)
    print(f"[done] verdict={verdict} runtime={time.time() - t0:.1f}s -> "
          f"{OUT_JSON.name}", flush=True)
    print("___V38_EXPLICIT_PROBE_DONE___", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
