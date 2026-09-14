"""v3.5 Phase 1: all-candidate ACV probe -- records stage (deployment-only).

Pre-registered in ``docs/v3_5_acv_preregistration.md`` §2 and §5. For every
one of the 2414 candidates of the frozen v3.3 candidate table this script
computes the two action-conditioned evidence blocks against the frozen TSFM
pool and writes ``results/v35_acv_records.jsonl``:

1. Prequential (§2): KEEP and APPLY histories are fed to the same frozen
   judge model to forecast the *identical* post-action anchor target block
   of original finite observations. ``gain = err(KEEP -> Y) - err(APPLY -> Y)``.
2. Support conformity (§2): the changed support is masked out exactly, each
   pool model reconstructs it from out-of-support context alone, and the
   KEEP values on the support are compared with the candidate's values
   against that reconstruction.

Frozen measurement decisions (do not tune after seeing any result):

- Error metric: ``nmse_fixed_window_scale`` -- mean squared error on the
  target block divided by ``scale**2``. One metric, fixed here.
- Reference scale: ``probe.reference_scale`` of the corrupted window (the
  blockwise-median robust spread of its finite observations), computed once
  per window and shared by KEEP and APPLY, so the ruler never moves with the
  edit (see probe.py's module docstring). This mirrors the fixed-normaliser
  convention of metrics_common while staying deployment-available (the
  evaluation-namespace reference series is never read here).
- lcb = mean - 1.645 * std(ddof=1) / sqrt(n); with n == 1 the lcb is the
  single gain itself (i.e. gain_min); with n == 0 every statistic stays
  None -- missing evidence is never filled with 0 (§2).
- Anchor rule: multi-horizon (one anchor per feasible horizon 8/16/32 per
  support run, capped at 3; see v35_acv_common).
- Forecast context: KEEP and APPLY contexts have identical length
  ``L = anchor_start - retain_lo`` (§2.4: same target, anchor, context
  length, reference scale and checkpoint). The APPLY series is the operator
  output, materialised with ``materialize_for_probe`` before the model sees
  it -- exactly what the frozen pipeline feeds the TSFM (probe.py); the
  materialiser is the identity on finite outputs, so this only matters for
  RESEGMENT outputs that retain NaN gaps. The anchor *target* is always the
  original finite observations, never a materialised value.
- An anchor is skipped (counted, not silently dropped) when the shared
  context length would be shorter than MIN_FORECAST_CONTEXT points.
- Support conformity is computed for IMPUTE / DESPIKE / DENOISE candidates
  whose changed support is non-empty and leaves at least
  MIN_CONFORMITY_CONTEXT eligible context points. RESEGMENT is excluded:
  its support is the *discarded* region, the candidate carries no values
  there, and the KEEP-vs-candidate comparison against a reconstruction is
  undefined. This is recorded as an applicability boundary, not masked.

Integrity discipline: this stage reads only the whitelisted identity fields
of the candidate table (ALLOWED_ROW_KEYS). No evaluation fields of any kind
are read, joined, or named here; the test suite scans this file for them.
The operator is re-run and its output hash verified against the frozen
table for every candidate (gate 1 of §4); the KEEP materialisation hash is
verified the same way.

Usage:
    python experiments/v35_acv_probe.py --device cuda
"""

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from v33_labels import hash_array  # noqa: E402
import v35_acv_common as acv  # noqa: E402
from introact_ts.probe import materialize_for_probe, reference_scale  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402

# -- frozen probe configuration (pre-registered §2/§5, do not tune) ------------

#: Judge = models[0] of the v3.3 curation pool, unchanged since v3.3.
POOL_SPECS = list(PRESETS["multi-family"]["curation"])
JUDGE_SPEC = POOL_SPECS[0]

#: Pool construction horizon. Forecast jobs always pass an explicit horizon
#: (<= 32), so this never changes prequential semantics; it only raises
#: TimesFM 2.5's compiled decode cap (2 x output patch = 256) so that long
#: support runs can be backcast/forecast for conformity reconstruction.
#: Spans beyond POOL_HORIZON are invalid views for TimesFM (skipped and
#: counted, never fabricated); the Chronos models decode autoregressively
#: and take any span.
POOL_HORIZON = 256
#: Per-adapter reconstruction span caps, by class name.
MODEL_SPAN_CAPS = {"TimesFMTSFM": POOL_HORIZON}

ERROR_METRIC = "nmse_fixed_window_scale"
LCB_Z = 1.645
#: Minimum shared context length for a prequential anchor forecast.
MIN_FORECAST_CONTEXT = 8
#: Conformity views are per (pool model, support run).
CONFORMITY_FAMILIES = ("IMPUTE", "DESPIKE", "DENOISE")

#: The only candidate-table fields this stage may read.
ALLOWED_ROW_KEYS = (
    "sample_uid", "window_id", "dataset", "stratum", "family", "rung",
    "params", "missing_fraction", "corrupted_hash", "output_hash",
    "keep_input_hash",
)

CODE_FILES = (
    "experiments/v35_acv_probe.py",
    "experiments/v35_acv_common.py",
    "src/introact_ts/probe.py",
    "src/introact_ts/actions.py",
    "src/introact_ts/backends/base.py",
    "src/introact_ts/backends/chronos.py",
    "src/introact_ts/backends/timesfm.py",
)


def probe_config() -> dict:
    """The frozen measurement configuration, hashed into every record."""
    return {
        "error_metric": ERROR_METRIC,
        "scale_rule": "reference_scale(corrupted window), fixed per window, "
                      "shared by KEEP and APPLY",
        "lcb_rule": "mean - 1.645*std(ddof=1)/sqrt(n); n==1 -> gain itself",
        "horizons": list(acv.HORIZONS),
        "max_anchors": acv.MAX_ANCHORS,
        "anchor_rule": "multi_horizon",
        "min_forecast_context": MIN_FORECAST_CONTEXT,
        "min_conformity_context": acv.MIN_CONFORMITY_CONTEXT,
        "conformity_families": list(CONFORMITY_FAMILIES),
        "pool_horizon": POOL_HORIZON,
        "model_span_caps": MODEL_SPAN_CAPS,
        "judge": JUDGE_SPEC,
        "pool": POOL_SPECS,
    }


def config_hash() -> str:
    return hashlib.sha256(
        json.dumps(probe_config(), sort_keys=True).encode()).hexdigest()


def code_hashes() -> dict:
    out = {}
    for rel in CODE_FILES:
        p = ROOT / rel
        if p.exists():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def resolve_revision(spec: str) -> str:
    """HF cache snapshot revision for a model spec, or 'local'/'unknown'."""
    family, ckpt = spec.split(":", 1) if ":" in spec else (spec, None)
    if family == "surrogate" or ckpt is None:
        return "local"
    import os
    hub = Path(os.environ.get("HF_HOME", "")) / "hub"
    ref = hub / ("models--" + ckpt.replace("/", "--")) / "refs" / "main"
    try:
        return ref.read_text().strip()
    except OSError:
        return "unknown"


# -- evidence statistics ---------------------------------------------------------


def gain_stats(gains) -> dict:
    """Pre-registered summary of a gain vector (§2.5/§2.7).

    Empty input -> every statistic None (missing evidence is reported as
    missing, never as 0). n==1 -> std None and lcb = the gain itself.
    """
    g = [float(v) for v in gains]
    if not g:
        return {"n": 0, "mean": None, "median": None, "min": None,
                "std": None, "win_rate": None, "lcb": None}
    arr = np.asarray(g, dtype=np.float64)
    n = len(arr)
    mean = float(arr.mean())
    std = float(arr.std(ddof=1)) if n >= 2 else None
    lcb = (mean - LCB_Z * std / np.sqrt(n)) if n >= 2 else float(arr.min())
    return {"n": n, "mean": mean, "median": float(np.median(arr)),
            "min": float(arr.min()), "std": std,
            "win_rate": float(np.mean(arr > 0)), "lcb": float(lcb)}


# -- per-candidate job builder (no model, pure) -----------------------------------


def build_candidate_jobs(sample_uid: str, series: np.ndarray, family: str,
                         params: dict) -> dict:
    """All model inputs for one candidate, as a pure function of the window.

    Returns the structural record (support, anchors) plus explicit forecast
    and reconstruction job specs. Deterministic in (uid, series, family,
    params); multiprocess and repeated runs build bit-identical jobs.
    """
    x = np.asarray(series, dtype=np.float64)
    T = len(x)
    out = acv.rerun_operator(x, family, params)
    y = np.asarray(out.series, dtype=np.float64)
    if out.applicable:
        support = acv.changed_support_mask(x, family, out)
        retain = acv.retain_span(family, out, T)
    else:
        support = np.zeros(T, dtype=bool)
        retain = (0, T)
    anchors = acv.select_anchors(sample_uid, x, support, retain=retain)
    x_keep = materialize_for_probe(x)
    y_q = materialize_for_probe(y)  # identity on finite outputs
    scale = reference_scale(x)
    rlo = int(retain[0])

    # Invariants re-checked on every build (§4 gates 4-5, §2.4 shared inputs).
    for a in anchors:
        assert not support[a["start"]:a["end"]].any()
        assert np.isfinite(x[a["start"]:a["end"]]).all()

    preq_jobs = []
    n_skipped = 0
    for a in anchors:
        L = a["start"] - rlo
        if L < MIN_FORECAST_CONTEXT:
            n_skipped += 1
            continue
        keep_ctx = x_keep[a["start"] - L:a["start"]]
        apply_ctx = y_q[:a["start"] - rlo]
        assert len(keep_ctx) == len(apply_ctx) == L
        target = x[a["start"]:a["end"]]
        preq_jobs.append({
            "run_lo": a["run_lo"], "run_hi": a["run_hi"],
            "horizon": a["horizon"], "start": a["start"], "end": a["end"],
            "context_len": int(L),
            "keep_ctx": keep_ctx, "apply_ctx": apply_ctx,
            "target": target,
            "keep_ctx_hash": hash_array(keep_ctx),
            "apply_ctx_hash": hash_array(apply_ctx),
            "target_hash": hash_array(target),
        })

    conformity = {"applicable": False, "reason": None, "spans": [],
                  "keep_vals": [], "cand_vals": []}
    context_n = int(acv.eligible_anchor_mask(x, support, retain).sum())
    if not support.any():
        conformity["reason"] = "empty_support"
    elif family not in CONFORMITY_FAMILIES:
        # RESEGMENT: the support is the discarded region; the candidate has
        # no values there, so the KEEP-vs-candidate comparison is undefined.
        conformity["reason"] = "resegment_discards_support"
    elif context_n < acv.MIN_CONFORMITY_CONTEXT:
        conformity["reason"] = "insufficient_context"
    else:
        spans = acv.support_runs(support)
        conformity = {
            "applicable": True, "reason": None,
            "spans": [[int(lo), int(hi)] for lo, hi in spans],
            "keep_vals": [x_keep[lo:hi] for lo, hi in spans],
            "cand_vals": [y_q[lo:hi] for lo, hi in spans],
        }

    return {
        "sample_uid": sample_uid, "family": family,
        "applicable": bool(out.applicable),
        "output_hash": hash_array(y) if out.applicable else None,
        "keep_input_hash": hash_array(x_keep),
        "support_n": int(support.sum()),
        "support_runs": [[int(lo), int(hi)] for lo, hi
                         in acv.support_runs(support)],
        "retain_span": [int(retain[0]), int(retain[1])],
        "anchors": anchors,
        "geometry": acv.geometry_of(x),
        "reference_scale": float(scale),
        "x_keep": x_keep,
        "preq_jobs": preq_jobs,
        "n_anchor_skipped_short_context": n_skipped,
        "conformity": conformity,
    }


def verify_job_targets(series: np.ndarray, job: dict) -> None:
    """Anchor-target integrity: every job target must equal the original
    window's slice bit for bit. Raises AssertionError on any tampering."""
    x = np.asarray(series, dtype=np.float64)
    for j in job["preq_jobs"]:
        want = x[j["start"]:j["end"]]
        got = np.asarray(j["target"], dtype=np.float64)
        assert got.shape == want.shape and np.array_equal(got, want), \
            "anchor target differs from the original window slice"
        assert np.isfinite(got).all(), "anchor target is not fully finite"


# -- batched model execution -------------------------------------------------------


def flat_reconstruct(model, items, max_span=None) -> dict:
    """Batched equivalent of ``ForecastOnlyMixin.reconstruct_batch`` over many
    series at once.

    ``items`` is a list of ``(series, spans)``. The math is byte-identical to
    calling ``model.reconstruct_batch(series, spans)`` per item (forward
    forecast from the left context blended with a backcast from the right,
    weights ``linspace(1, 0, span)``); flattening only moves the per-call
    grouping into one grouped pass. A span with <8 points of context on BOTH
    sides yields None (invalid view) instead of the mixin's fill fallback --
    the probe would rather drop a view than score a fill it cannot trust.
    ``max_span`` caps the reconstruction span for models with a compiled
    decode limit (TimesFM); over-long spans yield None as well.

    Leak discipline: the values inside a span are never read -- the requests
    are built from ``series[:lo]`` and ``series[hi:]`` only.
    """
    requests, plan = [], {}
    for i, (series, spans) in enumerate(items):
        s = np.asarray(series, dtype=np.float64)
        for j, (lo, hi) in enumerate(spans):
            lo, hi = int(lo), int(hi)
            span = hi - lo
            if max_span is not None and span > max_span:
                plan[(i, j)] = (span, None, None)
                continue
            left, right = s[:lo], s[hi:]
            i_fwd = i_bwd = None
            if len(left) >= 8:
                i_fwd = len(requests)
                requests.append(("f", left, span))
            if len(right) >= 8:
                i_bwd = len(requests)
                requests.append(("b", right, span))
            plan[(i, j)] = (span, i_fwd, i_bwd)

    results = {}
    by_span = defaultdict(list)
    for idx, (kind, ctx, span) in enumerate(requests):
        by_span[span].append((idx, kind, ctx))
    for span, group in by_span.items():
        contexts = [c[::-1] if k == "b" else c for _, k, c in group]
        preds = model.forecast_batch(contexts, span)
        for (idx, kind, _), p in zip(group, preds):
            results[idx] = (np.asarray(p, dtype=np.float64)[::-1]
                            if kind == "b" else np.asarray(p, np.float64))

    out = {}
    for key, (span, i_fwd, i_bwd) in plan.items():
        fwd, bwd = results.get(i_fwd), results.get(i_bwd)
        if fwd is not None and bwd is not None:
            w = np.linspace(1.0, 0.0, span)
            out[key] = w * fwd + (1.0 - w) * bwd
        elif fwd is not None:
            out[key] = fwd
        elif bwd is not None:
            out[key] = bwd
        else:
            out[key] = None
    return out


def execute_probe(jobs_by_candidate: list, models: list) -> list:
    """Run every candidate's jobs against the frozen pool, batched.

    Returns per-candidate evidence dicts. The judge (models[0]) is the only
    prequential model; all pool models reconstruct for conformity.
    """
    judge = models[0]

    # -- prequential: flatten every (candidate, anchor, side) forecast -------
    reqs = []  # (ctx, horizon, cand_i, anchor_i, side)
    for ci, job in enumerate(jobs_by_candidate):
        for ai, j in enumerate(job["preq_jobs"]):
            reqs.append((j["keep_ctx"], j["horizon"], ci, ai, "keep"))
            reqs.append((j["apply_ctx"], j["horizon"], ci, ai, "apply"))
    errs = {}
    by_horizon = defaultdict(list)
    for r in reqs:
        by_horizon[r[1]].append(r)
    for H, group in sorted(by_horizon.items()):
        preds = judge.forecast_batch([g[0] for g in group], H)
        for (_, _, ci, ai, side), p in zip(group, preds):
            errs[(ci, ai, side)] = np.asarray(p, dtype=np.float64)

    # -- conformity: flatten every (model, candidate, span) reconstruction ---
    conf_items, conf_pos = [], {}
    for ci, job in enumerate(jobs_by_candidate):
        c = job["conformity"]
        if c["applicable"]:
            conf_pos[ci] = len(conf_items)
            conf_items.append((job["x_keep"],
                               [tuple(s) for s in c["spans"]]))
    recs_by_model = [flat_reconstruct(m, conf_items,
                                      max_span=MODEL_SPAN_CAPS.get(
                                          type(m).__name__))
                     for m in models]

    evidences = []
    for ci, job in enumerate(jobs_by_candidate):
        scale2 = max(job["reference_scale"], 1e-8) ** 2
        anchor_rows, gains = [], []
        for ai, j in enumerate(job["preq_jobs"]):
            tgt = np.asarray(j["target"], dtype=np.float64)
            e_keep = float(np.mean((errs[(ci, ai, "keep")] - tgt) ** 2) / scale2)
            e_apply = float(np.mean((errs[(ci, ai, "apply")] - tgt) ** 2) / scale2)
            gains.append(e_keep - e_apply)
            anchor_rows.append({
                "run_lo": j["run_lo"], "run_hi": j["run_hi"],
                "horizon": j["horizon"], "start": j["start"], "end": j["end"],
                "context_len": j["context_len"],
                "err_keep": e_keep, "err_apply": e_apply,
                "gain": e_keep - e_apply,
                "keep_ctx_hash": j["keep_ctx_hash"],
                "apply_ctx_hash": j["apply_ctx_hash"],
                "target_hash": j["target_hash"],
            })
        preq = gain_stats(gains)
        prequential = {
            "supported": int(len(gains) > 0),
            "valid_anchors": len(gains),
            "skipped_short_context": job["n_anchor_skipped_short_context"],
            "anchors": anchor_rows,
            "gain_mean": preq["mean"], "gain_median": preq["median"],
            "gain_min": preq["min"], "gain_std": preq["std"],
            "win_rate": preq["win_rate"], "lcb": preq["lcb"],
        }

        conformity = {"supported": 0, "applicable": 0,
                      "reason": job["conformity"]["reason"],
                      "n_spans": len(job["conformity"]["spans"]),
                      "valid_views": 0, "view_gains": [],
                      "gain_mean": None, "gain_min": None, "gain_std": None,
                      "lcb": None, "model_disagree": None}
        c = job["conformity"]
        if c["applicable"]:
            view_gains, per_point = [], []
            for j, (lo, hi) in enumerate(c["spans"]):
                ii = conf_pos[ci]
                recs = [recs_by_model[mi].get((ii, j))
                        for mi in range(len(models))]
                recs = [r for r in recs if r is not None]
                if not recs:
                    continue
                keep_v = np.asarray(c["keep_vals"][j], dtype=np.float64)
                cand_v = np.asarray(c["cand_vals"][j], dtype=np.float64)
                for r in recs:
                    e_keep = float(np.mean((keep_v - r) ** 2) / scale2)
                    e_cand = float(np.mean((cand_v - r) ** 2) / scale2)
                    view_gains.append(e_keep - e_cand)
                per_point.append(np.std(np.stack(recs), axis=0))
            st = gain_stats(view_gains)
            disagreement = (float(np.mean(np.concatenate(per_point))
                                  / max(job["reference_scale"], 1e-8))
                            if per_point else None)
            conformity = {
                "supported": int(len(view_gains) > 0),
                "applicable": 1, "reason": None,
                "n_spans": len(c["spans"]),
                "valid_views": len(view_gains),
                "view_gains": [float(v) for v in view_gains],
                "gain_mean": st["mean"], "gain_min": st["min"],
                "gain_std": st["std"], "lcb": st["lcb"],
                "model_disagree": disagreement,
            }

        evidences.append({"prequential": prequential,
                          "support_conformity": conformity})
    return evidences


def fixed_scores(evidence: dict) -> dict:
    """The three pre-registered fixed scores (§2.8). None stays None."""
    a = evidence["prequential"]["lcb"]
    b = evidence["support_conformity"]["lcb"]
    c = None
    if a is not None and b is not None:
        c = min(a, b)
    return {"score_a_prequential": a, "score_b_support": b,
            "score_c_joint": c}


def assemble_record(row: dict, job: dict, ev: dict, revisions: dict,
                    cfg_hash: str, code: dict) -> dict:
    """One records-file line. Every record carries the model, checkpoint
    revisions, config hash, input hash and output hash (§5 integrity)."""
    return {
        "sample_uid": row["sample_uid"],
        "window_id": row["window_id"],
        "dataset": row["dataset"],
        "stratum": row["stratum"],
        "family": row["family"],
        "rung": row["rung"],
        "params": row["params"],
        "missing_fraction": row["missing_fraction"],
        "geometry": job["geometry"],
        "corrupted_hash": row["corrupted_hash"],
        "input_hash": row["corrupted_hash"],
        "output_hash": job["output_hash"],
        "output_hash_verified": job["output_hash_verified"],
        "keep_input_hash": job["keep_input_hash"],
        "keep_hash_verified": job["keep_hash_verified"],
        "support_n": job["support_n"],
        "support_runs": job["support_runs"],
        "retain_span": job["retain_span"],
        "anchor_rule": "multi_horizon",
        "anchors": job["anchors"],
        "reference_scale": job["reference_scale"],
        **ev,
        **fixed_scores(ev),
        "model": {"judge": JUDGE_SPEC, "pool": POOL_SPECS,
                  "revisions": revisions},
        "config_hash": cfg_hash,
        "code_hashes": code,
    }


# -- corpus matching (identical discipline to the Phase 0 audit) -------------------


def _row_key(row) -> str:
    return (row["family"], row["rung"], json.dumps(row["params"], sort_keys=True))


def match_windows(rows, n_corpus: int, seed: int, manifest_path: str):
    """Rebuild the frozen corpus and map sample_uid -> corrupted series.

    Only the corrupted series is kept; the pristine twin is dropped on the
    floor here and never touches anything downstream of this function.
    """
    from build_calibration import build as build_calibration
    windows, _ = build_calibration(n=n_corpus, seed=seed, source="mixed",
                                   verbose=False)
    by_hash = defaultdict(list)
    for w in windows:
        by_hash[hash_array(np.asarray(w.series, dtype=np.float64))].append(w)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    manifest_by_uid = {r["sample_uid"]: r for r in manifest["records"]}
    uid_series = {}
    for r in rows:
        uid = r["sample_uid"]
        if uid in uid_series:
            continue
        cands = by_hash.get(r["corrupted_hash"], [])
        m = manifest_by_uid.get(uid)
        if len(cands) != 1 or m is None \
                or m["corrupted_hash"] != r["corrupted_hash"]:
            raise SystemExit(f"window verification failed for {uid}")
        series = np.asarray(cands[0].series, dtype=np.float64)
        if hash_array(series) != r["corrupted_hash"]:
            raise SystemExit(f"corrupted hash mismatch for {uid}")
        uid_series[uid] = series
    return uid_series, len(windows)


def _build_uid(task):
    """Build every candidate's jobs for one window. Top-level for pickling."""
    sample_uid, series, rows = task
    out = []
    for row in rows:
        job = build_candidate_jobs(sample_uid, series, row["family"],
                                   row["params"])
        job["output_hash_verified"] = (
            job["output_hash"] == row.get("output_hash"))
        # The candidate table's KEEP-input field is family-dependent: for
        # IMPUTE it is the probe-materialised series (the same object this
        # probe feeds the model); for other families it is the untouched
        # window (an evaluation-side construct that may still hold NaN and
        # is never model input). The probe's KEEP series is ALWAYS the
        # materialised one -- the frozen TSFM never reads NaN (probe.py) --
        # so the hash cross-check is meaningful for IMPUTE only.
        job["keep_hash_verified"] = (
            (job["keep_input_hash"] == row.get("keep_input_hash"))
            if row["family"] == "IMPUTE" else None)
        verify_job_targets(series, job)
        out.append(job)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data",
                    default=str(ROOT / "results" / "v33_training_data.jsonl"))
    ap.add_argument("--manifest",
                    default=str(ROOT / "results" / "p0_corpus_manifest_a.json"))
    ap.add_argument("--out",
                    default=str(ROOT / "results" / "v35_acv_records.jsonl"))
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
    ap.add_argument("--n-corpus", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--limit", type=int, default=None,
                    help="debug: only the first N candidates (sorted order)")
    args = ap.parse_args()

    t0 = time.time()
    rows_all = [json.loads(l) for l in open(args.data, encoding="utf-8")]
    rows = [{k: r.get(k) for k in ALLOWED_ROW_KEYS} for r in rows_all]
    rows.sort(key=lambda r: (r["sample_uid"], _row_key(r)))
    if args.limit:
        rows = rows[:args.limit]
    print(f"{len(rows)} candidates (of {len(rows_all)})", flush=True)

    uid_series, n_windows = match_windows(rows, args.n_corpus, args.seed,
                                          args.manifest)
    print(f"matched {len(uid_series)} windows of {n_windows} "
          f"({time.time() - t0:.1f}s)", flush=True)

    by_uid = defaultdict(list)
    for r in rows:
        by_uid[r["sample_uid"]].append(r)
    work = [(uid, uid_series[uid], sorted(rs, key=_row_key))
            for uid, rs in sorted(by_uid.items())]

    t1 = time.time()
    if args.n_jobs > 1 and len(work) > 1:
        with ProcessPoolExecutor(max_workers=args.n_jobs) as ex:
            per_uid = list(ex.map(_build_uid, work))
    else:
        per_uid = [_build_uid(w) for w in work]
    print(f"built jobs in {time.time() - t1:.1f}s", flush=True)

    n_bad_out = sum(1 for recs in per_uid for j in recs
                    if not j["output_hash_verified"])
    n_bad_keep = sum(1 for recs in per_uid for j in recs
                     if j["keep_hash_verified"] is False)
    print(f"output hash mismatches: {n_bad_out}; keep hash mismatches "
          f"(IMPUTE only, see _build_uid): {n_bad_keep}", flush=True)
    if n_bad_out or n_bad_keep:
        raise SystemExit("hash verification failed; refusing to probe")

    # -- model loading: exactly once ------------------------------------------
    t2 = time.time()
    models = make_pool(POOL_SPECS, device=args.device, horizon=POOL_HORIZON)
    revisions = {spec: resolve_revision(spec) for spec in POOL_SPECS}
    print(f"loaded {len(models)} models in {time.time() - t2:.1f}s: "
          f"{revisions}", flush=True)

    ordered_rows = [r for _, _, rs in work for r in rs]
    jobs_flat = [j for recs in per_uid for j in recs]

    t3 = time.time()
    evidences = execute_probe(jobs_flat, models)
    print(f"executed probe in {time.time() - t3:.1f}s "
          f"({len(jobs_flat)} candidates)", flush=True)

    ch = config_hash()
    code = code_hashes()
    out_path = Path(args.out)
    n_preq = n_conf = 0
    with out_path.open("w", encoding="utf-8") as f:
        for row, job, ev in zip(ordered_rows, jobs_flat, evidences):
            n_preq += ev["prequential"]["supported"]
            n_conf += ev["support_conformity"]["supported"]
            rec = assemble_record(row, job, ev, revisions, ch, code)
            f.write(json.dumps(rec, sort_keys=True, default=float) + "\n")

    file_hash = hashlib.sha256(out_path.read_bytes()).hexdigest()
    print(json.dumps({
        "n_records": len(ordered_rows),
        "n_prequential_supported": n_preq,
        "n_conformity_supported": n_conf,
        "share_either": float(np.mean([
            ev["prequential"]["supported"] or ev["support_conformity"]["supported"]
            for ev in evidences])) if evidences else 0.0,
        "records_sha256": file_hash,
        "elapsed_seconds": time.time() - t0,
    }, indent=1), flush=True)
    print(f"___V35_ACV_PROBE_DONE___ wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
