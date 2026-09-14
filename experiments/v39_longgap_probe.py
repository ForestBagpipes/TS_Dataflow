"""v3.9 Phase 1: MIRAGE-TS long-gap foundation-imputer frozen probe.

Pre-registered in ``docs/v3_9_mirage_preregistration.md`` §3. GPU for the
foundation models, CPU otherwise, API 0.

Evaluation population: the 89 missing_block windows whose single raw-NaN run
(length 25-63, two finite anchors, inside [T/8, T-T/8]) abstained as
``overlong_gap`` in every v3.8 gap-certificate tier. They are recovered
exactly from ``results/v38_explicit_impute_records.jsonl`` (wide tier,
n_filled == 0 and n_raw_nan > 0).

Fixed candidates (§3):
  keep                  KEEP / materialised forward-fill
  linear_bridge         unrestricted explicit linear bridge (the v3.8 operator
                        with the length cap removed)
  seasonal_existing     existing seasonal IMPUTE row (aggressive rung)
  impute_default        existing linear min_run=16 IMPUTE row (default rung)
  impute_conservative   existing linear min_run=32 IMPUTE row
  moment                MOMENT-1-large masked reconstruction (v3.5 operator)
  openfim               OpenFIM fim-imp-pointwise-base (ICLR 2025)
  tsicl                 TS-ICL median, plus q10/q90 (uncertainty width only)
  fm_mean               mean of the OpenFIM and TS-ICL-median fills (only
                        because both are available)

Label-freeze discipline (§3): candidate stages NEVER read clean series or any
label field. Every candidate record carries input/output/touched/filled
hashes, per-window drift and the model identity. ``freeze`` merges and
digests all candidate files; only then may ``evaluate`` join the v3.3
action-semantic labels (``experiments/v33_labels.py::compute_action_labels``,
family "IMPUTE": KEEP counterfactual = materialize_for_probe(original)).

Candidate contract: only raw NaN positions may be written; observed-support
drift is exactly 0 (asserted per candidate and re-verified at evaluate time
by rebuilding the output from the stored fill values); output length and
time index equal the input window's; unsupported windows are recorded as
unsupported and never back-filled with a surrogate.

Stages:
    python experiments/v39_longgap_probe.py candidates --proposer keep ...
    python experiments/v39_longgap_probe.py freeze
    python experiments/v39_longgap_probe.py evaluate
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
import v38_explicit_impute_probe as v38p  # noqa: E402
from introact_ts.actions import robust_scale, _mask_runs  # noqa: E402
from introact_ts.probe import materialize_for_probe  # noqa: E402
from introact_ts.contextual_shield import EPISODE_FAMILY_ORDER  # noqa: E402
import v33_compare_arms as v33  # noqa: E402

ROWS_PATH = ROOT / "results" / "v33_training_data.jsonl"
MANIFEST_PATH = ROOT / "results" / "p0_corpus_manifest_a.json"
REPLAY_PATH = ROOT / "results" / "v38_oracle_replay.json"
PHASE0_V39 = ROOT / "results" / "v39_phase0_replay.json"
EXPLICIT_RECORDS = ROOT / "results" / "v38_explicit_impute_records.jsonl"
MASK_RECORDS = ROOT / "results" / "v38_impute_mask_records.jsonl"

OUT_CANDIDATES = ROOT / "results" / "v39_longgap_candidates.jsonl"
OUT_FREEZE = ROOT / "results" / "v39_longgap_candidates_freeze.json"
OUT_PROBE = ROOT / "results" / "v39_longgap_probe.json"
OUT_ORACLE = ROOT / "results" / "v39_longgap_oracle.json"
OUT_MODEL_MANIFEST = ROOT / "results" / "v39_model_manifest.json"

OPENFIM_REPO = ROOT / "third_party" / "openfim"
OPENFIM_CKPT = ROOT / "third_party" / "checkpoints" / "openfim_pointwise_base"
TSICL_CKPT = ROOT / "third_party" / "checkpoints" / "tsicl" / "tsicl-v1.ckpt"
TSICL_CKPT_SHA256 = (
    "a67ae9f694c2a83cfc8e7ec41745ff4f41a4a76ee2b17172ec3430d8d29da431")
OPENFIM_CKPT_SHA256 = (
    "390ba4c13f24e8f0c2d8cfca6565cbcd2c34928f0be8fe61647144bfc2df2834")

HARM_LOSS = 0.03
GAIN_EPS = 1e-9
TOL = 1e-9

#: Population facts frozen from the v3.8 probe (verified, not assumed).
EXPECTED_POPULATION = {
    "n_windows": 89, "gap_len_min": 25, "gap_len_max": 63,
    "n_gaps_per_window": 1,
}
FACT_SHORT_MAX_GAP = 3
FACT_FAMILY = "FACT_SHORT"
BRIDGE_FAMILY = "BRIDGE_LONG"
#: Expected FACT_SHORT counts on this corpus (v3.8/v3.9-Phase-0 frozen facts).
EXPECTED_FILL = {"n_windows": 88, "n_bs": 76, "n_harmful": 12}

#: New proposers (relative to the inherited IMPUTE family).
NEW_PROPOSERS = ("linear_bridge", "moment", "openfim", "tsicl", "fm_mean")
#: Proposers whose fills enter the joint unrestricted oracle as BRIDGE_LONG.
ORACLE_PROPOSERS = ("linear_bridge", "moment", "openfim", "tsicl", "fm_mean")
ORACLE_ALLOWED = ("DENOISE", "DESPIKE", FACT_FAMILY, BRIDGE_FAMILY)

#: Headroom gates (§3), fixed before any result is seen.
GATE1_MIN_BS_SINGLE = 15
GATE1_MIN_BS_UNION_GAIN = 10
GATE2 = {"bcov": 0.32, "gain": 0.105, "chr": 0.0}
GATE4_MIN_SOURCES = 4

PROPOSER_STAGE_FILE = {
    p: ROOT / "results" / f"v39_longgap_cand_{p}.jsonl"
    for p in ("keep", "linear_bridge", "seasonal_existing", "impute_default",
              "impute_conservative", "moment", "openfim", "tsicl", "fm_mean")
}

#: Existing IMPUTE reference rows: proposer name -> (rung, params).
EXISTING_IMPUTE_REFS = {
    "seasonal_existing": ("aggressive", {"method": "seasonal", "min_run": 8}),
    "impute_default": ("default", {"method": "linear", "min_run": 16}),
    "impute_conservative": ("conservative", {"method": "linear",
                                             "min_run": 32}),
}

MODEL_INFO = {
    "moment": {
        "name": "MOMENT-1-large (masked reconstruction head)",
        "paper": "MOMENT: A Foundation Model for Time Series (ICML 2024)",
        "repository_url": "https://github.com/moment-timeseries-foundation-model/moment",
        "huggingface_id": "AutonLab/MOMENT-1-large",
        "license": "MIT",
        "checkpoint_sha256": None,  # filled from the HF cache snapshot
        "role": "control arm (native masked reconstruction, used in v3.5)",
    },
    "openfim": {
        "name": "OpenFIM fim-imp-pointwise-base",
        "paper": ("Zero-shot Imputation with Foundation Inference Models "
                  "for Dynamical Systems (ICLR 2025)"),
        "repository_url": "https://github.com/FIM4Science/OpenFIM",
        "code_commit": "cee2bb53be1e8e92b73f98dfdbe3605efc9119cc",
        "huggingface_id": "FIM4Science/fim-imp-pointwise-base",
        "huggingface_revision": "e00537a9fc695c69e6f22bf8dce3903c3bff3af3",
        "checkpoint_sha256": OPENFIM_CKPT_SHA256,
        "checkpoint_bytes": 80904896,
        "license": "MIT (repository LICENSE.md; HF model card unspecified)",
        "role": "primary new proposer",
    },
    "tsicl": {
        "name": "TS-ICL tsicl-v1 (imputer component)",
        "paper": ("TS-ICL: A Flexible Time-Indexed Foundation Model for "
                  "Time Series via In-Context Learning (arXiv:2606.05878)"),
        "repository_url": "https://github.com/EDF-Lab/ts-icl",
        "pypi": "tsicl==0.2.1 (installed --no-deps; only hf_hub_download and "
                "LocalEntryNotFoundError are used, both present in "
                "huggingface_hub<1)",
        "huggingface_id": "taharnbl/TS-ICL",
        "huggingface_revision": "19c94031439fb31f36ce395088ee50a6762d3774",
        "checkpoint_sha256": TSICL_CKPT_SHA256,
        "checkpoint_bytes": 219150987,
        "license": "TS-ICL Non-Commercial License v1.0 (EDF SA; academic "
                   "research use permitted)",
        "role": "new proposer; q10/q90 used only for uncertainty width",
    },
}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pkey(params):
    return json.dumps(params, sort_keys=True)


# -- pure candidate helpers (unit-tested) ----------------------------------------


def longgap_population_uids(explicit_records):
    """The 89 long-gap missing_block windows from the v3.8 explicit probe.

    Selection: wide tier, n_raw_nan > 0, n_filled == 0 (every gap abstained
    as overlong_gap). Returns {uid: meta} sorted by uid. Pure function of the
    records; assertions encode the frozen population facts.
    """
    pop = {}
    for r in explicit_records:
        if r["variant"] != "wide":
            continue
        if r["n_raw_nan"] > 0 and r["n_filled"] == 0:
            pop[r["sample_uid"]] = {
                "sample_uid": r["sample_uid"], "dataset": r["dataset"],
                "stratum": r["stratum"], "true_kind": r["true_kind"],
                "layer": r["layer"], "corrupted_hash": r["corrupted_hash"],
                "n_raw_nan": r["n_raw_nan"],
                "gap_decisions": r["gap_decisions"],
            }
    assert len(pop) == EXPECTED_POPULATION["n_windows"], \
        f"population drifted: {len(pop)} != {EXPECTED_POPULATION['n_windows']}"
    for uid, m in pop.items():
        gaps = m["gap_decisions"]
        assert len(gaps) == EXPECTED_POPULATION["n_gaps_per_window"]
        g = gaps[0]
        assert g["abstain_reason"] == "overlong_gap" and not g["certified"]
        assert EXPECTED_POPULATION["gap_len_min"] <= g["length"] \
            <= EXPECTED_POPULATION["gap_len_max"]
        assert g["left_anchor"] and g["right_anchor"]
    return dict(sorted(pop.items()))


def insert_fill_at_raw_nan(x, fill_values):
    """KEEP base + candidate fills written ONLY at raw NaN positions.

    ``fill_values`` is ordered over the raw NaN positions (np.flatnonzero
    order). Returns (y, filled_mask). Observed-support drift is exactly 0 by
    construction and asserted.
    """
    x = np.asarray(x, dtype=np.float64)
    nm = ~np.isfinite(x)
    y = materialize_for_probe(x)
    pos = np.flatnonzero(nm)
    fill_values = np.asarray(fill_values, dtype=np.float64)
    assert len(fill_values) == len(pos), "fill/NaN-position count mismatch"
    assert bool(np.isfinite(fill_values).all()), "fill contains non-finite"
    y[pos] = fill_values
    filled = np.zeros(len(x), dtype=bool)
    filled[pos] = True
    obs = np.isfinite(x)
    assert np.array_equal(y[obs], x[obs]), "observed-support drift"
    assert bool(np.isfinite(y).all())
    return y, filled


def seam_jump_stats(x, y, scale=None):
    """Boundary seam jumps of a filled window against the raw anchors.

    |fill - anchor| at each gap edge, normalised by ``robust_scale`` of the
    raw window (v3.8 diagnostics convention; raw-only, label-free).
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    scale = float(scale if scale is not None else robust_scale(x))
    scale = max(scale, 1e-12)
    seams = []
    T = len(x)
    for lo, hi in _mask_runs(~np.isfinite(x)):
        if lo > 0 and np.isfinite(x[lo - 1]) and np.isfinite(y[lo]):
            seams.append(abs(float(y[lo]) - float(x[lo - 1])) / scale)
        if hi < T and np.isfinite(x[hi]) and np.isfinite(y[hi - 1]):
            seams.append(abs(float(y[hi - 1]) - float(x[hi])) / scale)
    return {"seam_jump_max": float(max(seams)) if seams else 0.0,
            "seam_jump_mean": float(np.mean(seams)) if seams else 0.0}


def observed_mad(x):
    """Median absolute deviation of the observed finite values (label-free)."""
    v = np.asarray(x, dtype=np.float64)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return 0.0
    return float(np.median(np.abs(v - np.median(v))))


def uncertainty_width(q10, q90, x):
    """TS-ICL posterior width over the gap, raw and observed-MAD-normalised."""
    q10 = np.asarray(q10, dtype=np.float64)
    q90 = np.asarray(q90, dtype=np.float64)
    w = q90 - q10
    mad = max(observed_mad(x), 1e-12)
    return {"q10_q90_width_mean": float(np.mean(w)),
            "q10_q90_width_max": float(np.max(w)),
            "width_over_observed_mad_mean": float(np.mean(w) / mad),
            "observed_mad": float(mad)}


def config_hash(cfg: dict) -> str:
    return hashlib.sha256(
        json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()


# -- candidate record builder -----------------------------------------------------


def base_record(meta, proposer, family, rung, params, is_new):
    return {
        "sample_uid": meta["sample_uid"], "dataset": meta["dataset"],
        "stratum": meta["stratum"], "true_kind": meta["true_kind"],
        "layer": meta["layer"], "corrupted_hash": meta["corrupted_hash"],
        "proposer": proposer, "family": family, "rung": rung,
        "params": params, "is_new_proposer": bool(is_new),
        "supported": True, "unsupported_reason": None,
        "applicable": False, "n_raw_nan": int(meta["n_raw_nan"]),
        "n_filled": 0, "gap_decisions": meta["gap_decisions"],
        "input_hash": meta["corrupted_hash"], "output_hash": None,
        "touched_mask_hash": None, "filled_mask_hash": None,
        "fill_values": None,
        "observed_support_drift": 0.0,
        "seam_jump_max": 0.0, "seam_jump_mean": 0.0,
        "uncertainty": None, "model": None,
    }


def finalize_record(rec, x, y, filled, model=None):
    """Fill hash/drift/seam fields of a candidate record; asserts the contract."""
    x = np.asarray(x, dtype=np.float64)
    nm = raw_nan_mask(x)
    y = np.asarray(y, dtype=np.float64)
    assert len(y) == len(x), "output length must equal the input window"
    obs = np.isfinite(x)
    drift = float(np.max(np.abs(y[obs] - x[obs]))) if obs.any() else 0.0
    assert drift == 0.0, f"observed-support drift {drift}"
    rec.update({
        "applicable": bool(filled.any()),
        "n_filled": int(filled.sum()),
        "output_hash": hash_array(y),
        "touched_mask_hash": mask_hash(nm),
        "filled_mask_hash": mask_hash(filled),
        "fill_values": [float(v) for v in y[nm]],
        "observed_support_drift": drift,
        **seam_jump_stats(x, y),
        "model": model,
    })
    return rec


def unsupported_record(rec, reason):
    rec["supported"] = False
    rec["unsupported_reason"] = str(reason)[:300]
    return rec


# -- candidate generators ---------------------------------------------------------


def gen_keep(x, meta):
    rec = base_record(meta, "keep", "KEEP_MATERIALIZED", "keep_ff",
                      {"method": "forward_fill"}, False)
    y = materialize_for_probe(x)
    return finalize_record(rec, x, y, np.zeros(len(x), dtype=bool))


def gen_linear_bridge(x, meta):
    """Unrestricted explicit linear bridge: the v3.8 operator, no length cap."""
    rec = base_record(meta, "linear_bridge", BRIDGE_FAMILY, "linear_bridge",
                      {"method": "explicit_linear", "max_gap": None}, True)
    res = v38p.impute_explicit_linear(x, max_gap=2**31 - 1)
    return finalize_record(rec, x, res["series"], res["filled"])


def gen_existing_impute(x, meta, proposer, table_index):
    """Re-run an existing IMPUTE row's operator; hash-verified vs the table.

    Only non-label fields of the frozen candidate table are read here
    (sample_uid, family, rung, params, output_hash); labels are joined at
    evaluate time.
    """
    from introact_ts.actions import Action, apply_action
    rung, params = EXISTING_IMPUTE_REFS[proposer]
    row = table_index.get((meta["sample_uid"], rung, _pkey(params)))
    rec = base_record(meta, proposer, "IMPUTE", rung, params, False)
    if row is None:
        return unsupported_record(rec, "no matching row in v33 candidate table")
    out = apply_action(np.asarray(x, dtype=np.float64), Action.IMPUTE,
                       **params)
    if not out.applicable:
        return unsupported_record(rec, "operator not applicable")
    got = hash_array(out.series)
    if got != row["output_hash"]:
        return unsupported_record(
            rec, f"output hash mismatch vs frozen table: {got}")
    touched = np.asarray(out.touched, dtype=bool)
    rec["params"] = {**params, "operator_n_filled":
                     int(out.params.get("n_filled", 0))}
    # Existing IMPUTE masks may include finite flatline points; the candidate
    # is the historical operator output, recorded as-is (drift asserted).
    return finalize_record(rec, x, out.series, touched)


def gen_moment(x, meta, model):
    """MOMENT masked reconstruction of the raw NaN spans (v3.5 operator)."""
    rec = base_record(meta, "moment", BRIDGE_FAMILY, "moment_reconstruct",
                      {"task": "reconstruction"}, True)
    x = np.asarray(x, dtype=np.float64)
    base = materialize_for_probe(x)
    spans = [(int(lo), int(hi)) for lo, hi in _mask_runs(~np.isfinite(x))]
    recs = model.reconstruct_batch(base, spans)
    y = base.copy()
    for (lo, hi), r in zip(spans, recs):
        y[lo:hi] = np.asarray(r, dtype=np.float64)
    filled = np.zeros(len(x), dtype=bool)
    for lo, hi in spans:
        filled[lo:hi] = True
    return finalize_record(rec, x, y, filled, model=MODEL_INFO["moment"])


def gen_openfim(x, meta, fim_model):
    """OpenFIM pointwise imputation at the raw NaN positions.

    obs_mask follows the OpenFIM convention (1 = masked out); the model
    forward-fills masked positions internally and its MinMax normalisation is
    mask-aware (observed values only). The fill is written only at raw NaN
    positions of the KEEP base.
    """
    import torch
    rec = base_record(meta, "openfim", BRIDGE_FAMILY, "openfim_pointwise",
                      {"windowing": "none", "dtype": "float32"}, True)
    x = np.asarray(x, dtype=np.float64)
    T = len(x)
    nm = ~np.isfinite(x)
    pos = np.flatnonzero(nm)
    obs_times = torch.arange(T, dtype=torch.float32).view(1, T, 1)
    obs_values = torch.tensor(np.where(nm, 0.0, x),
                              dtype=torch.float32).view(1, T, 1)
    obs_mask = torch.tensor(nm, dtype=torch.bool).view(1, T, 1)
    eval_times = torch.tensor(pos, dtype=torch.float32).view(1, len(pos), 1)
    with torch.no_grad():
        out = fim_model.forward(obs_times, obs_values, eval_times, obs_mask)
    fill = out.reconstructed_values.detach().cpu().numpy().reshape(-1)
    fill = np.asarray(fill, dtype=np.float64)
    if not np.isfinite(fill).all():
        return unsupported_record(rec, "OpenFIM produced non-finite values")
    y, filled = insert_fill_at_raw_nan(x, fill)
    return finalize_record(rec, x, y, filled, model=MODEL_INFO["openfim"])


def gen_tsicl(x, meta, model):
    """TS-ICL imputation: median fill + q10/q90 uncertainty width."""
    rec = base_record(meta, "tsicl", BRIDGE_FAMILY, "tsicl_median",
                      {"quantile_levels": [0.1, 0.5, 0.9],
                       "point_estimator": "median", "replace_by_gt": True},
                      True)
    x = np.asarray(x, dtype=np.float64)
    nm = ~np.isfinite(x)
    pos = np.flatnonzero(nm)
    point, quantiles = model.impute(
        inputs=x, quantile_levels=[0.1, 0.5, 0.9], denormalize=True,
        point_estimator="median", replace_by_gt=True, squeeze_output=True)
    point = np.asarray(point.detach().cpu().numpy(), dtype=np.float64)
    quants = np.asarray(quantiles.detach().cpu().numpy(), dtype=np.float64)
    point = point.reshape(-1)[: len(x)]
    quants = quants.reshape(len(x), -1)  # [T, 3] in requested order
    fill = point[pos]
    if not np.isfinite(fill).all():
        return unsupported_record(rec, "TS-ICL produced non-finite values")
    y, filled = insert_fill_at_raw_nan(x, fill)
    rec["uncertainty"] = uncertainty_width(quants[pos, 0], quants[pos, 2], x)
    return finalize_record(rec, x, y, filled, model=MODEL_INFO["tsicl"])


def gen_fm_mean(x, meta, openfim_fill, tsicl_fill):
    """Mean of the OpenFIM and TS-ICL-median fills (both must exist)."""
    rec = base_record(meta, "fm_mean", BRIDGE_FAMILY, "fm_mean",
                      {"mean_of": ["openfim", "tsicl"]}, True)
    if openfim_fill is None or tsicl_fill is None:
        return unsupported_record(rec, "requires both OpenFIM and TS-ICL fills")
    fill = (np.asarray(openfim_fill, dtype=np.float64)
            + np.asarray(tsicl_fill, dtype=np.float64)) / 2.0
    y, filled = insert_fill_at_raw_nan(x, fill)
    return finalize_record(rec, x, y, filled,
                           model={"mean_of": [MODEL_INFO["openfim"],
                                              MODEL_INFO["tsicl"]]})


# -- stage plumbing -----------------------------------------------------------------


def load_population():
    """Population uids + rebuilt corpus windows, with all integrity gates."""
    rep = json.load(REPLAY_PATH.open(encoding="utf-8"))
    if not bool(rep.get("all_replays_pass")):
        raise SystemExit("[FATAL] v3.8 replay gate failed; Phase 1 void")
    if PHASE0_V39.exists():
        p0 = json.load(PHASE0_V39.open(encoding="utf-8"))
        if not bool(p0.get("all_gates_pass")):
            raise SystemExit("[FATAL] v3.9 Phase-0 gates failed; Phase 1 void")
    explicit = [json.loads(l) for l in EXPLICIT_RECORDS.open(encoding="utf-8")]
    pop = longgap_population_uids(explicit)
    recs, _dropped = rebuild_corpus()
    manifest = json.load(MANIFEST_PATH.open(encoding="utf-8"))
    gate = verify_against_manifest(recs, manifest)
    if not gate["pass"]:
        raise SystemExit(f"[FATAL] corpus manifest gate: {gate}")
    rebuilt = {r["sample_uid"]: r for r in recs}
    for uid, m in pop.items():
        w = rebuilt.get(uid)
        assert w is not None, f"population uid {uid} not rebuilt"
        assert w["corrupted_hash"] == m["corrupted_hash"]
    return pop, rebuilt


def candidate_table_index():
    """(uid, rung, params_key) -> non-label fields of the frozen table row."""
    out = {}
    for l in ROWS_PATH.open(encoding="utf-8"):
        r = json.loads(l)
        if r["family"] != "IMPUTE":
            continue
        out[(r["sample_uid"], r["rung"], _pkey(r["params"]))] = {
            "output_hash": r["output_hash"],
            "corrupted_hash": r["corrupted_hash"]}
    return out


def stage_file(proposer):
    return PROPOSER_STAGE_FILE[proposer]


def moment_cache_info():
    """MOMENT revision + checkpoint sha256 from the local HF cache."""
    snap = (Path("/root/autodl-tmp/.cache/huggingface/hub")
            / "models--AutonLab--MOMENT-1-large" / "snapshots")
    if not snap.exists():
        return {"huggingface_revision": None, "checkpoint_sha256": None}
    snaps = sorted(p for p in snap.iterdir() if p.is_dir())
    return {"huggingface_revision": [p.name for p in snaps],
            "checkpoint_sha256": _sha256(snaps[0] / "model.safetensors")
            if (snaps[0] / "model.safetensors").exists() else None,
            "checkpoint_bytes": ((snaps[0] / "model.safetensors").stat()
                                 .st_size
                                 if (snaps[0] / "model.safetensors").exists()
                                 else None)}


def run_candidate_stage(proposer, device="cuda", limit=None):
    t0 = time.time()
    pop, rebuilt = load_population()
    uids = sorted(pop)[:limit] if limit else sorted(pop)
    gpu_peak_mb = None
    model = None
    table_index = None

    if proposer == "moment":
        import torch
        torch.cuda.set_per_process_memory_fraction(0.55)
        from introact_ts.backends import make_backend
        model = make_backend("moment:AutonLab/MOMENT-1-large", device=device)
        MODEL_INFO["moment"].update(moment_cache_info())
    elif proposer == "openfim":
        import torch
        torch.cuda.set_per_process_memory_fraction(0.55)
        sys.path.insert(0, str(OPENFIM_REPO / "src"))
        assert _sha256(OPENFIM_CKPT / "model.safetensors") == \
            OPENFIM_CKPT_SHA256, "OpenFIM checkpoint sha256 mismatch"
        from fim.models.imputation_pointwise import (
            FIMImpPoint, FIMImpPointBase)
        base = FIMImpPointBase.from_pretrained(str(OPENFIM_CKPT))
        base.to(device).eval()
        model = FIMImpPoint(fim_imp_pointwise_base=base)  # no windowing
    elif proposer == "tsicl":
        import torch
        torch.cuda.set_per_process_memory_fraction(0.55)
        assert _sha256(TSICL_CKPT) == TSICL_CKPT_SHA256, \
            "TS-ICL checkpoint sha256 mismatch"
        from tsicl import TSICL
        model = TSICL(model_path=str(TSICL_CKPT))
    elif proposer in EXISTING_IMPUTE_REFS:
        table_index = candidate_table_index()
    elif proposer == "fm_mean":
        pass  # fills read from the openfim/tsicl stage files below
    elif proposer != "keep" and proposer != "linear_bridge":
        raise SystemExit(f"unknown proposer {proposer}")

    fills_of = {}
    if proposer == "fm_mean":
        for src in ("openfim", "tsicl"):
            for l in stage_file(src).open(encoding="utf-8"):
                r = json.loads(l)
                if r["supported"] and r["applicable"]:
                    fills_of.setdefault(r["sample_uid"], {})[src] = \
                        r["fill_values"]

    recs = []
    n_unsupported = 0
    for i, uid in enumerate(uids):
        meta = pop[uid]
        x = np.asarray(rebuilt[uid]["series"], dtype=np.float64)
        try:
            if proposer == "keep":
                rec = gen_keep(x, meta)
            elif proposer == "linear_bridge":
                rec = gen_linear_bridge(x, meta)
            elif proposer in EXISTING_IMPUTE_REFS:
                rec = gen_existing_impute(x, meta, proposer, table_index)
            elif proposer == "moment":
                rec = gen_moment(x, meta, model)
            elif proposer == "openfim":
                rec = gen_openfim(x, meta, model)
            elif proposer == "tsicl":
                rec = gen_tsicl(x, meta, model)
            elif proposer == "fm_mean":
                got = fills_of.get(uid, {})
                rec = gen_fm_mean(x, meta, got.get("openfim"),
                                  got.get("tsicl"))
            else:  # pragma: no cover
                raise AssertionError(proposer)
        except Exception as exc:  # unsupported, never a silent fallback
            fam = (BRIDGE_FAMILY if proposer in NEW_PROPOSERS
                   else "IMPUTE" if proposer in EXISTING_IMPUTE_REFS
                   else "KEEP_MATERIALIZED" if proposer == "keep"
                   else BRIDGE_FAMILY)
            rec = unsupported_record(
                base_record(meta, proposer, fam, proposer, {},
                            proposer in NEW_PROPOSERS),
                f"{type(exc).__name__}: {exc}")
        n_unsupported += int(not rec["supported"])
        rec["config_hash"] = config_hash(
            {"proposer": proposer, "params": rec["params"],
             "model": (rec["model"] or {}).get("huggingface_id")
             if isinstance(rec["model"], dict) else None})
        recs.append(rec)
        if (i + 1) % 20 == 0:
            print(f"[{proposer}] {i + 1}/{len(uids)} "
                  f"({time.time() - t0:.0f}s)", flush=True)

    if proposer in ("moment", "openfim", "tsicl"):
        import torch
        if torch.cuda.is_available():
            gpu_peak_mb = float(torch.cuda.max_memory_allocated() / 2**20)

    out = stage_file(proposer)
    with out.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    sidecar = {
        "proposer": proposer, "n_windows": len(recs),
        "n_unsupported": n_unsupported,
        "device": device if proposer in ("moment", "openfim", "tsicl")
        else "cpu",
        "gpu_peak_mem_mb": gpu_peak_mb,
        "runtime_sec": time.time() - t0,
        "output_sha256": _sha256(out),
        "python": sys.version.split()[0],
        "packages": _pip_freeze(),
    }
    sidecar_path = ROOT / "results" / f"v39_longgap_stage_{proposer}.json"
    with sidecar_path.open("w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=1)
    print(f"[{proposer}] {len(recs)} candidates ({n_unsupported} "
          f"unsupported) in {time.time() - t0:.1f}s -> {out.name}",
          flush=True)
    print(f"___V39_LONGGAP_STAGE_{proposer.upper()}_DONE___", flush=True)
    return 0


def _pip_freeze():
    import subprocess
    try:
        out = subprocess.run([sys.executable, "-m", "pip", "freeze",
                              "--all"],
                             capture_output=True, text=True, timeout=120)
        pkgs = sorted(l for l in out.stdout.splitlines() if "==" in l)
        return pkgs
    except Exception as exc:  # pragma: no cover
        return [f"pip freeze failed: {exc}"]


# -- freeze ------------------------------------------------------------------------


def run_freeze():
    t0 = time.time()
    files = {}
    missing = []
    for p, path in PROPOSER_STAGE_FILE.items():
        if not path.exists():
            missing.append(p)
            continue
        files[p] = [json.loads(l) for l in path.open(encoding="utf-8")]
    # fm_mean is conditional on both FMs; every other proposer is mandatory.
    hard_required = [p for p in PROPOSER_STAGE_FILE if p != "fm_mean"]
    hard_missing = [p for p in hard_required if p in missing]
    if hard_missing:
        raise SystemExit(f"[FATAL] candidate stages missing: {hard_missing}")

    pop_check = None
    all_recs = []
    per_file = {}
    for p, recs in sorted(files.items()):
        per_file[f"results/v39_longgap_cand_{p}.jsonl"] = {
            "sha256": _sha256(stage_file(p)), "n_records": len(recs),
            "n_supported": sum(1 for r in recs if r["supported"])}
        uids = sorted(r["sample_uid"] for r in recs)
        if pop_check is None:
            pop_check = uids
        assert uids == pop_check, f"{p}: window set drifted"
        all_recs.extend(recs)
    all_recs.sort(key=lambda r: (r["sample_uid"], r["proposer"]))

    with OUT_CANDIDATES.open("w", encoding="utf-8") as f:
        for r in all_recs:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    merged_sha = _sha256(OUT_CANDIDATES)
    slim = sorted(({"sample_uid": r["sample_uid"], "proposer": r["proposer"],
                    "supported": r["supported"],
                    "output_hash": r["output_hash"]} for r in all_recs),
                  key=lambda r: (r["sample_uid"], r["proposer"]))
    digest = hashlib.sha256(
        json.dumps(slim, sort_keys=True).encode()).hexdigest()
    freeze = {
        "phase": "v3.9 Phase 1 candidate freeze (labels not yet joined)",
        "frozen_at_epoch": time.time(),
        "n_records": len(all_recs),
        "n_windows": len(pop_check),
        "proposers": sorted(files),
        "per_file": per_file,
        "merged_file": "results/v39_longgap_candidates.jsonl",
        "merged_sha256": merged_sha,
        "record_digest_sha256": digest,
        "label_freeze_discipline": ("all candidate outputs and hashes frozen "
                                    "before any clean/evaluation label is "
                                    "read; evaluate refuses to run without "
                                    "this file and re-verifies every output "
                                    "hash from the stored fill values"),
        "runtime_sec": time.time() - t0,
    }
    with OUT_FREEZE.open("w", encoding="utf-8") as f:
        json.dump(freeze, f, indent=1)
    print(f"[freeze] {len(all_recs)} records, digest={digest[:16]}... -> "
          f"{OUT_FREEZE.name}", flush=True)
    print("___V39_LONGGAP_FREEZE_DONE___", flush=True)
    return 0


# -- evaluation ----------------------------------------------------------------------


def labeled_row(rec, labels):
    """Candidate record + joined labels as a v3.3-pool-shaped row."""
    return {
        "sample_uid": rec["sample_uid"], "dataset": rec["dataset"],
        "stratum": rec["stratum"], "true_kind": rec["true_kind"],
        "corrupted_hash": rec["corrupted_hash"],
        "family": rec["family"], "rung": rec["rung"],
        "params": rec["params"] if isinstance(rec["params"], dict) else {},
        "proposer": rec["proposer"],
        "true_loss": float(labels["true_loss"]),
        "true_repair_gain": float(labels["true_repair_gain"]),
        "beneficial": float(labels["beneficial"]),
        "beneficial_and_safe": float(labels["beneficial_and_safe"]),
    }


def proposer_stats(rows, n_pop):
    """The v3.9 five-quantity report + label metrics for one proposer."""
    app = [r for r in rows if r["supported"] and r["applicable"]]
    bs = [r for r in app if r["labels"]["beneficial_and_safe"]]
    harm = [r for r in app if r["labels"]["true_loss"] > HARM_LOSS]
    neutral = [r for r in app
               if not r["labels"]["beneficial_and_safe"]
               and r["labels"]["true_loss"] <= HARM_LOSS]
    gains_all = [r["labels"]["true_repair_gain"]
                 if r["supported"] and r["applicable"] else 0.0
                 for r in rows]
    gains_app = [r["labels"]["true_repair_gain"] for r in app]
    tm_after = [r["labels"]["target_mask_nrmse_after"] for r in app
                if np.isfinite(r["labels"]["target_mask_nrmse_after"] or
                               float("nan"))]
    tm_gain = [r["labels"]["target_mask_gain"] for r in app
               if r["labels"]["target_mask_gain"] is not None
               and np.isfinite(r["labels"]["target_mask_gain"])]
    n_app = len(app)
    return {
        "n_windows": len(rows),
        "n_supported": sum(1 for r in rows if r["supported"]),
        "n_applicable": n_app,
        "applicability_coverage": n_app / n_pop,
        "action_conditional_bs_precision":
            (len(bs) / n_app) if n_app else None,
        "action_conditional_chr": (len(harm) / n_app) if n_app else None,
        "bcov_population": len(bs) / n_pop,
        "abstention_rate": 1.0 - n_app / n_pop,
        "n_bs": len(bs), "n_harmful": len(harm), "n_neutral": len(neutral),
        "bs_uids": sorted(r["sample_uid"] for r in bs),
        "harmful_uids": sorted(r["sample_uid"] for r in harm),
        "mean_gain_all_windows": float(np.mean(gains_all))
        if gains_all else None,
        "mean_gain_applicable": float(np.mean(gains_app))
        if gains_app else None,
        "median_gain_applicable": float(np.median(gains_app))
        if gains_app else None,
        "target_mask_nrmse_after_mean": float(np.mean(tm_after))
        if tm_after else None,
        "target_mask_gain_mean": float(np.mean(tm_gain)) if tm_gain else None,
        "seam_jump_max": float(max((r["seam_jump_max"] for r in app),
                                   default=0.0)),
        "seam_jump_mean": float(np.mean([r["seam_jump_mean"] for r in app]))
        if app else None,
        "observed_support_drift_max": float(max(
            (r["observed_support_drift"] for r in rows), default=0.0)),
    }


def per_source_stats(rows, n_pop_by_source):
    out = {}
    by_src = defaultdict(list)
    for r in rows:
        by_src[r["dataset"]].append(r)
    for ds in sorted(by_src):
        s = proposer_stats(by_src[ds], n_pop_by_source[ds])
        out[ds] = {k: s[k] for k in (
            "n_windows", "n_supported", "n_applicable",
            "applicability_coverage", "action_conditional_bs_precision",
            "action_conditional_chr", "n_bs", "n_harmful",
            "mean_gain_applicable", "target_mask_nrmse_after_mean")}
    return out


def fact_short_rows(rebuilt, explicit_by_uid):
    """FACT_SHORT candidate rows, identical construction to v3.9 Phase 0."""
    wide_by_uid = {r["sample_uid"]: r for r in explicit_by_uid
                   if r["variant"] == "wide"}
    fact_rows, n_bs, n_harm = [], 0, 0
    for uid in sorted(wide_by_uid):
        w = wide_by_uid[uid]
        if w["layer"] not in v38p.ACTUAL_NAN_LAYERS:
            continue
        x = np.asarray(rebuilt[uid]["series"], dtype=np.float64)
        res3 = v38p.impute_explicit_linear(x, max_gap=FACT_SHORT_MAX_GAP)
        if not res3["applicable"]:
            continue
        assert hash_array(res3["series"]) == w["output_hash"], \
            f"FACT_SHORT != v3.8 wide on {uid}"
        lab = w["labels"]
        n_bs += int(bool(lab["beneficial_and_safe"]))
        n_harm += int(float(lab["true_loss"]) > HARM_LOSS)
        fact_rows.append({
            "sample_uid": uid, "dataset": w["dataset"],
            "stratum": w["stratum"], "true_kind": w["true_kind"],
            "corrupted_hash": w["corrupted_hash"],
            "family": FACT_FAMILY, "rung": "fact_short",
            "params": {"method": "explicit_linear",
                       "max_gap": FACT_SHORT_MAX_GAP},
            "true_loss": float(lab["true_loss"]),
            "true_repair_gain": float(lab["true_repair_gain"]),
            "beneficial": float(lab["beneficial"]),
            "beneficial_and_safe": float(lab["beneficial_and_safe"]),
        })
    assert (len(fact_rows), n_bs, n_harm) == (
        EXPECTED_FILL["n_windows"], EXPECTED_FILL["n_bs"],
        EXPECTED_FILL["n_harmful"]), "FACT_SHORT 88/76/12 reproduction failed"
    return fact_rows


def unrestricted_oracle_rows(rows, allowed):
    """v3.3 oracle: per window max-gain beneficial_and_safe among allowed."""
    by_uid = defaultdict(list)
    for r in rows:
        by_uid[r["sample_uid"]].append(r)
    committed = {}
    for uid, rs in by_uid.items():
        bs = [r for r in rs
              if r["beneficial_and_safe"] and r["family"] in allowed]
        if bs:
            best = max(bs, key=lambda r: r["true_repair_gain"])
            committed[uid] = (best, rs.index(best), "oracle", None)
        else:
            committed[uid] = None
    return committed


def keep_placeholders(all_uids, covered, uid_meta):
    return [{"sample_uid": u, "dataset": uid_meta[u]["dataset"],
             "stratum": uid_meta[u]["stratum"],
             "true_kind": uid_meta[u]["true_kind"],
             "corrupted_hash": uid_meta[u]["corrupted_hash"],
             "family": "KEEP", "rung": "keep", "params": {},
             "true_loss": 0.0, "true_repair_gain": 0.0,
             "beneficial": 0.0, "beneficial_and_safe": 0.0}
            for u in sorted(set(all_uids) - set(covered))]


def run_evaluate():
    t0 = time.time()
    if not OUT_FREEZE.exists():
        raise SystemExit("[FATAL] candidates not frozen; run candidate "
                         "stages then `freeze` before `evaluate`")
    freeze = json.load(OUT_FREEZE.open(encoding="utf-8"))
    if _sha256(OUT_CANDIDATES) != freeze["merged_sha256"]:
        raise SystemExit("[FATAL] merged candidates file changed after freeze")
    print(f"[freeze verified] digest={freeze['record_digest_sha256'][:16]}...",
          flush=True)

    pop, rebuilt = load_population()
    cand = [json.loads(l) for l in OUT_CANDIDATES.open(encoding="utf-8")]
    assert len(cand) == freeze["n_records"]

    # -- join labels (evaluation namespace from here on) -----------------------
    n_hash_fail = 0
    max_drift = 0.0
    for r in cand:
        uid = r["sample_uid"]
        x = np.asarray(rebuilt[uid]["series"], dtype=np.float64)
        clean = np.asarray(rebuilt[uid]["window"].clean_series,
                           dtype=np.float64)
        if not r["supported"]:
            r["labels"] = None
            continue
        y, filled = insert_fill_at_raw_nan(x, r["fill_values"])
        if hash_array(y) != r["output_hash"]:
            n_hash_fail += 1
        obs = np.isfinite(x)
        drift = float(np.max(np.abs(y[obs] - x[obs]))) if obs.any() else 0.0
        max_drift = max(max_drift, drift, r["observed_support_drift"])
        assert drift == 0.0 and r["observed_support_drift"] == 0.0
        touched = (None if r["proposer"] == "keep"
                   else raw_nan_mask(x))
        lab = compute_action_labels("IMPUTE", x, y, clean, touched=touched,
                                    params={})
        if r["proposer"] == "keep":
            assert abs(lab["true_repair_gain"]) <= 1e-12, "KEEP gain must be 0"
        r["labels"] = {k: (float(v) if isinstance(v, (int, float, np.floating))
                           and v is not None else v)
                       for k, v in lab.items()}
        # label-free diagnostics against clean (v3.8 conventions)
        nm = raw_nan_mask(x)
        xk = materialize_for_probe(x)
        rv = ref_var(clean)
        scale = max(robust_scale(clean), 1e-12)
        r["missing_support_nmse_before"] = float(
            np.mean((xk[nm] - clean[nm]) ** 2)) / max(rv, 1e-12)
        r["missing_support_nmse_after"] = float(
            np.mean((y[nm] - clean[nm]) ** 2)) / max(rv, 1e-12)
        r["missing_support_nrmse_after"] = float(
            np.sqrt(np.mean((y[nm] - clean[nm]) ** 2)) / scale)
    if n_hash_fail:
        raise SystemExit(f"[FATAL] {n_hash_fail} frozen output hashes do "
                         f"not reproduce from stored fill values")
    print(f"[labels joined] max observed drift={max_drift}", flush=True)

    # Cross-check: recomputed labels of the existing IMPUTE refs must equal
    # the frozen table's labels (loss/gain/beneficial/safe are touched-free).
    table = {}
    for l in ROWS_PATH.open(encoding="utf-8"):
        row = json.loads(l)
        if row["family"] == "IMPUTE":
            table[(row["sample_uid"], row["rung"], _pkey(row["params"]))] = row
    n_label_xcheck = 0
    for r in cand:
        if r["proposer"] not in EXISTING_IMPUTE_REFS or not r["supported"]:
            continue
        key = (r["sample_uid"], r["rung"], _pkey(EXISTING_IMPUTE_REFS[
            r["proposer"]][1]))
        ref = table[key]
        for k in ("true_loss", "true_repair_gain"):
            assert abs(r["labels"][k] - float(ref[k])) < TOL, \
                f"label path drifted on {key}: {r['labels'][k]} vs {ref[k]}"
        n_label_xcheck += 1
    print(f"[label xcheck] {n_label_xcheck} existing-IMPUTE labels reproduce "
          f"the frozen table within 1e-9", flush=True)

    # -- per-proposer tables ----------------------------------------------------
    n_pop = len(pop)
    src_pop = Counter(m["dataset"] for m in pop.values())
    by_prop = defaultdict(list)
    for r in cand:
        by_prop[r["proposer"]].append(r)
    tables = {}
    for p in sorted(by_prop):
        rows = by_prop[p]
        tables[p] = {**proposer_stats(rows, n_pop),
                     "per_source": per_source_stats(rows, src_pop)}

    # Derived comparator: current best IMPUTE = per-window max-gain b&s pick
    # over the three existing IMPUTE rows (the "current IMPUTE oracle" of §3).
    impute_by_uid = defaultdict(list)
    for p in EXISTING_IMPUTE_REFS:
        for r in by_prop.get(p, []):
            if r["supported"] and r["applicable"]:
                impute_by_uid[r["sample_uid"]].append(r)
    imp_best_rows = []
    for uid in sorted(pop):
        rs = impute_by_uid.get(uid, [])
        bs = [r for r in rs if r["labels"]["beneficial_and_safe"]]
        pick = max(bs, key=lambda r: r["labels"]["true_repair_gain"]) \
            if bs else (max(rs, key=lambda r: r["labels"]["true_repair_gain"])
                        if rs else None)
        if pick is not None:
            imp_best_rows.append(pick)
    current_impute_bs = {r["sample_uid"] for r in imp_best_rows
                         if r["labels"]["beneficial_and_safe"]}
    tables["impute_current_best"] = {
        "definition": ("per-window max-gain beneficial_and_safe pick over "
                       "the three existing IMPUTE rows; falls back to the "
                       "max-gain row when none is b&s (the §3 'current best "
                       "IMPUTE candidates' comparator)"),
        **proposer_stats(imp_best_rows, n_pop),
        "per_source": per_source_stats(imp_best_rows, src_pop),
    }

    # -- gate 1: new-proposer headroom on long blocks ----------------------------
    new_bs = {p: set(tables[p]["bs_uids"]) for p in NEW_PROPOSERS
              if p in tables}
    union_new_bs = set().union(*new_bs.values()) if new_bs else set()
    per_prop_ge15 = {p: len(s) for p, s in new_bs.items()}
    g1a = any(len(s) >= GATE1_MIN_BS_SINGLE for s in new_bs.values())
    added_vs_impute = union_new_bs - current_impute_bs
    g1b = len(added_vs_impute) >= GATE1_MIN_BS_UNION_GAIN
    gate1 = {
        "rule": (f">= {GATE1_MIN_BS_SINGLE} B&S unique windows for at least "
                 f"one new proposer, OR new-proposer union adds >= "
                 f"{GATE1_MIN_BS_UNION_GAIN} B&S windows over the current "
                 f"IMPUTE oracle (89-window long-block population)"),
        "bs_unique_by_proposer": per_prop_ge15,
        "new_proposer_union_bs": len(union_new_bs),
        "current_impute_oracle_bs": len(current_impute_bs),
        "union_bs_not_in_impute_oracle": len(added_vs_impute),
        "single_proposer_leg_pass": bool(g1a),
        "union_leg_pass": bool(g1b),
        "pass": bool(g1a or g1b),
    }

    # -- gate 2: joint unrestricted oracle over the 771 frame --------------------
    rows_all = v33._load_rows(str(ROWS_PATH))
    real = [r for r in rows_all if not r["dataset"].startswith("ood:")]
    real_uids = sorted({r["sample_uid"] for r in real})
    assert len(real_uids) == 771
    uid_meta = {}
    for r in real:
        uid_meta.setdefault(r["sample_uid"], {
            "dataset": r["dataset"], "stratum": r["stratum"],
            "true_kind": r["true_kind"],
            "corrupted_hash": r["corrupted_hash"]})
    explicit = [json.loads(l) for l in EXPLICIT_RECORDS.open(encoding="utf-8")]
    fact_rows = fact_short_rows(rebuilt, explicit)
    base_rows = [r for r in real if r["family"] != "IMPUTE"]
    bridge_rows = []
    for r in cand:
        if r["proposer"] not in ORACLE_PROPOSERS:
            continue
        if not (r["supported"] and r["applicable"]):
            continue
        bridge_rows.append(labeled_row(r, r["labels"]))
    pool = base_rows + fact_rows + bridge_rows
    pool += keep_placeholders(real_uids, {r["sample_uid"] for r in pool},
                              uid_meta)
    committed = unrestricted_oracle_rows(pool, ORACLE_ALLOWED)
    met = v33._episode_metrics(pool, committed)
    oracle_picks = {}
    for uid, got in committed.items():
        if got is None:
            continue
        row = got[0]
        oracle_picks[uid] = {
            "family": row["family"], "rung": row["rung"],
            "proposer": row.get("proposer"),
            "true_repair_gain": float(row["true_repair_gain"]),
            "true_loss": float(row["true_loss"]),
        }
    oracle_report = {
        "pool": {
            "n_rows": len(pool),
            "n_base_non_impute": len(base_rows),
            "n_fact_short": len(fact_rows),
            "n_bridge_long": len(bridge_rows),
            "n_keep_placeholders":
                len(pool) - len(base_rows) - len(fact_rows) - len(bridge_rows),
            "allowed_families": list(ORACLE_ALLOWED),
            "bridge_rungs": dict(Counter(r["rung"] for r in bridge_rows)),
            "frame": "frozen 771 real windows; candidate-less windows stay "
                     "as no-commit KEEP placeholders",
        },
        "rule": ("unrestricted per-window max-gain beneficial_and_safe "
                 "oracle over PICS_non_IMPUTE pool + FACT_SHORT + BRIDGE_LONG "
                 "(new long-gap proposers); RESEGMENT and inherited IMPUTE "
                 "closed; headroom measurement only, never a deployment rule"),
        "n_windows": int(met["n_windows"]),
        "committed": int(met["committed"]),
        "bcov": float(met["beneficial_coverage"]),
        "gain": float(met["mean_repair_gain_contaminated"]),
        "chr": float(met["conditional_harm_rate"]),
        "pme": float(met["protected_mis_edit_rate"]),
        "damage": float(met["damage"]),
        "applicability_coverage": int(met["committed"]) / len(real_uids),
        "action_conditional_bs_precision":
            (float(met["beneficial_commits"]) / int(met["committed"]))
            if int(met["committed"]) else None,
        "abstention_rate": 1.0 - float(met["commit_rate"]),
        "commit_by_family": dict(Counter(p["family"]
                                         for p in oracle_picks.values())),
        "commit_by_bridge_rung": dict(Counter(
            p["rung"] for p in oracle_picks.values()
            if p["family"] == BRIDGE_FAMILY)),
        "picks": oracle_picks,
    }
    gate2 = {
        "rule": (f"joint unrestricted oracle: bcov >= {GATE2['bcov']}, gain "
                 f">= {GATE2['gain']}, CHR == {GATE2['chr']} (771-window "
                 f"frame, KEEP placeholders)"),
        "bcov": {"value": oracle_report["bcov"], "threshold": GATE2["bcov"],
                 "pass": bool(oracle_report["bcov"] >= GATE2["bcov"])},
        "gain": {"value": oracle_report["gain"], "threshold": GATE2["gain"],
                 "pass": bool(oracle_report["gain"] >= GATE2["gain"])},
        "chr": {"value": oracle_report["chr"], "threshold": GATE2["chr"],
                "pass": bool(oracle_report["chr"] == GATE2["chr"])},
    }
    gate2["pass"] = bool(all(c["pass"] for c in gate2.values()
                             if isinstance(c, dict)))

    # -- gate 3: observed-support drift ------------------------------------------
    gate3 = {
        "rule": "observed-support drift exactly 0 for every candidate",
        "max_drift": max_drift, "n_candidates": len(cand),
        "pass": bool(max_drift == 0.0),
    }

    # -- gate 4: >= 4/6 sources with valid output ----------------------------------
    all_sources = sorted({m["dataset"] for m in pop.values()})
    src_valid = {}
    for p in NEW_PROPOSERS:
        if p not in tables:
            continue
        src_valid[p] = sorted(
            ds for ds, s in tables[p]["per_source"].items()
            if s["n_applicable"] > 0)
    union_src = sorted(set().union(*(set(v) for v in src_valid.values()))
                       if src_valid else set())
    gate4 = {
        "rule": (f">= {GATE4_MIN_SOURCES}/6 sources with valid new-proposer "
                 f"output (population sources: {all_sources})"),
        "sources_with_valid_output_by_proposer": src_valid,
        "union_sources": union_src,
        "n_union_sources": len(union_src),
        "pass": bool(len(union_src) >= GATE4_MIN_SOURCES),
    }

    gates = {"g1_new_proposer_headroom": gate1,
             "g2_joint_unrestricted_oracle": gate2,
             "g3_observed_support_drift_zero": gate3,
             "g4_source_coverage": gate4}
    all_pass = all(g["pass"] for g in gates.values())
    verdict = ("candidate_headroom_reached" if all_pass
               else "candidate_headroom_not_reached")
    print(f"[gates] { {k: v['pass'] for k, v in gates.items()} } "
          f"verdict={verdict}", flush=True)

    # -- outputs ---------------------------------------------------------------------
    stage_sidecars = {}
    for p in PROPOSER_STAGE_FILE:
        sp = ROOT / "results" / f"v39_longgap_stage_{p}.json"
        if sp.exists():
            stage_sidecars[p] = json.load(sp.open(encoding="utf-8"))

    probe_out = {
        "phase": "v3.9 Phase 1: MIRAGE-TS long-gap foundation-imputer "
                 "frozen probe (docs/v3_9_mirage_preregistration.md §3)",
        "definitions": {
            "population": ("89 missing_block windows: single raw-NaN run of "
                           "length 25-63, two finite anchors, inside "
                           "[T/8, T-T/8]; abstained as overlong_gap in every "
                           "v3.8 gap-certificate tier"),
            "label_path": ("experiments/v33_labels.py::compute_action_labels "
                           "with family 'IMPUTE'; joined ONLY after the "
                           "candidate freeze (see v39_longgap_candidates_"
                           "freeze.json)"),
            "harmful": f"true_loss > {HARM_LOSS}",
            "neutral": "applicable and neither beneficial_and_safe nor harmful",
            "five_quantities": ("applicability coverage, action-conditional "
                                "B&S precision, action-conditional CHR, bcov, "
                                "abstention rate"),
            "candidate_contract": ("only raw NaN positions written; drift "
                                   "exactly 0; output length/index aligned; "
                                   "unsupported recorded, never silently "
                                   "back-filled"),
        },
        "freeze": {k: freeze[k] for k in ("n_records", "n_windows",
                                          "record_digest_sha256",
                                          "merged_sha256", "proposers")},
        "proposer_tables": tables,
        "gates": gates,
        "all_gates_pass": bool(all_pass),
        "verdict": verdict,
        "stage_runtimes": {p: {"runtime_sec": s["runtime_sec"],
                               "gpu_peak_mem_mb": s["gpu_peak_mem_mb"],
                               "device": s["device"]}
                           for p, s in stage_sidecars.items()},
        "label_xcheck_existing_impute": {
            "n_checked": n_label_xcheck,
            "note": ("recomputed labels of the existing IMPUTE reference "
                     "rows equal the frozen v3.3 table within 1e-9")},
        "input_hashes": {
            "v33_training_data": _sha256(ROWS_PATH),
            "v38_explicit_impute_records": _sha256(EXPLICIT_RECORDS),
            "v38_impute_mask_records": _sha256(MASK_RECORDS),
            "v38_oracle_replay": _sha256(REPLAY_PATH),
            "p0_corpus_manifest_a": _sha256(MANIFEST_PATH),
        },
        "code_hashes": {
            "experiments/v39_longgap_probe.py": _sha256(
                Path(__file__).resolve()),
            "experiments/v38_explicit_impute_probe.py": _sha256(
                ROOT / "experiments" / "v38_explicit_impute_probe.py"),
            "experiments/v33_labels.py": _sha256(
                ROOT / "experiments" / "v33_labels.py"),
        },
        "runtime_sec": time.time() - t0,
    }
    with OUT_PROBE.open("w", encoding="utf-8") as f:
        json.dump(probe_out, f, indent=1, ensure_ascii=False, default=str)
    print(f"[probe] -> {OUT_PROBE.name}", flush=True)

    oracle_out = {
        "phase": "v3.9 Phase 1 joint unrestricted oracle (gate 2 detail)",
        **oracle_report,
        "gate": gate2,
    }
    with OUT_ORACLE.open("w", encoding="utf-8") as f:
        json.dump(oracle_out, f, indent=1, ensure_ascii=False, default=str)
    print(f"[oracle] -> {OUT_ORACLE.name}", flush=True)

    # -- model manifest ---------------------------------------------------------------
    manifest = build_model_manifest(stage_sidecars)
    with OUT_MODEL_MANIFEST.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False, default=str)
    print(f"[model manifest] -> {OUT_MODEL_MANIFEST.name}", flush=True)

    print(f"[done] verdict={verdict} runtime={time.time() - t0:.1f}s",
          flush=True)
    print("___V39_LONGGAP_EVALUATE_DONE___", flush=True)
    return 0 if all_pass else 1


def build_model_manifest(stage_sidecars):
    """Per-external-model acquisition record (§3 reporting duty)."""
    models = {}
    for key, info in MODEL_INFO.items():
        entry = dict(info)
        if key == "moment":
            entry.update(moment_cache_info())
        sidecar = stage_sidecars.get(key)
        entry["available"] = bool(
            sidecar and sidecar["n_windows"] - sidecar["n_unsupported"] > 0)
        if sidecar:
            entry["n_windows_supported"] = \
                sidecar["n_windows"] - sidecar["n_unsupported"]
            entry["runtime_sec"] = sidecar["runtime_sec"]
            entry["gpu_peak_mem_mb"] = sidecar["gpu_peak_mem_mb"]
        models[key] = entry
    return {
        "phase": "v3.9 Phase 1 external model manifest",
        "models": models,
        "openfim_code": {
            "repository_url": "https://github.com/FIM4Science/OpenFIM",
            "local_copy": "third_party/openfim",
            "used_files": ["src/fim/models/imputation_pointwise.py"],
            "usage": ("FIMImpPointBase.from_pretrained(local checkpoint dir) "
                      "wrapped in FIMImpPoint without windowing; obs_mask=raw "
                      "NaN, evaluation at the NaN positions"),
        },
        "tsicl_code": {
            "repository_url": "https://github.com/EDF-Lab/ts-icl",
            "pypi": "tsicl==0.2.1",
            "usage": ("TSICL(model_path=local ckpt).impute(inputs=window "
                      "with NaN, quantile_levels=[0.1,0.5,0.9], "
                      "point_estimator='median', replace_by_gt=True, "
                      "denormalize=True); only NaN positions taken; q10/q90 "
                      "used only for the uncertainty width"),
        },
        "stage_environments": {p: {"python": s["python"],
                                   "packages": s["packages"]}
                               for p, s in stage_sidecars.items()},
        "api_spend": 0,
        "download_sources": {
            "hf_mirror": ("https://hf-mirror.com (HF mirror; the node cannot "
                          "reach huggingface.co directly)"),
            "checkpoints": {
                "openfim": "https://huggingface.co/FIM4Science/"
                           "fim-imp-pointwise-base (revision "
                           "e00537a9fc695c69e6f22bf8dce3903c3bff3af3)",
                "tsicl": "https://huggingface.co/taharnbl/TS-ICL (revision "
                         "19c94031439fb31f36ce395088ee50a6762d3774)",
            },
        },
    }


# -- main ----------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["candidates", "freeze", "evaluate"])
    ap.add_argument("--proposer", default=None)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if args.stage == "candidates":
        if not args.proposer:
            raise SystemExit("--proposer required for the candidates stage")
        return run_candidate_stage(args.proposer, device=args.device,
                                   limit=args.limit)
    if args.stage == "freeze":
        return run_freeze()
    if args.stage == "evaluate":
        return run_evaluate()
    raise SystemExit(f"unknown stage {args.stage}")


if __name__ == "__main__":
    sys.exit(main())
