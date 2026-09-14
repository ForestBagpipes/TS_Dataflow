"""v3.5 Phase 2: TSFM_RECONSTRUCT_IMPUTE operator probe -- records stage.

Pre-registered in ``docs/v3_5_acv_preregistration.md`` §3 and §6. On every
window where the production routing proposed IMPUTE (the candidate table's
family == 'IMPUTE' rows; no outcome field is ever read here), this script
builds four paired arms and freezes their output hashes:

  - ``keep``:      materialize_for_probe(corrupted) -- the KEEP counterfactual
                   the frozen TSFM actually sees (probe.py);
  - ``default``:   the routed default rung, IMPUTE method=linear min_run=16;
  - ``candidate``: the actual candidate row's operator, re-run and
                   hash-verified against the frozen table;
  - ``tsfm``:      TSFM_RECONSTRUCT_IMPUTE -- the experimental operator.

TSFM_RECONSTRUCT_IMPUTE fills exactly the window's real NaN runs with the
frozen proposer model's native masked reconstruction of the probe-
materialised series, the spans masked so the model never reads the fill
sites. It never modifies an observed finite value (asserted per window and
test-enforced), it is a candidate action only (nothing here commits), and
it is generated on every routed-IMPUTE window regardless of any outcome
field (§3.1).

Cross-model discipline (§3.6/§3.7): the proposer is MOMENT (masked
reconstruction is its pretraining task -- the only NATIVE reconstruct head
in the backend registry). The verifiers (chronos-bolt-base, timesfm) hold
CAP_RECONSTRUCT only through the forecast/backcast blend of
ForecastOnlyMixin, so this probe is cross-model but single-native-backend;
the verifier disagreement between the proposer's fill and each verifier's
independent reconstruction of the same masked runs is frozen into every
record. No cross-model certificate is claimed beyond that.

Integrity: only ALLOWED_ROW_KEYS of the candidate table are read; the test
suite scans this file for evaluation-field tokens. Outcome fields are joined
exclusively by v35_tsfm_impute_evaluate.py after this file's records are
frozen, and only after the arm outputs re-verify hash-identical.

Usage:
    python experiments/v35_tsfm_impute_probe.py --device cuda
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

from v33_labels import hash_array  # noqa: E402
import v35_acv_common as acv  # noqa: E402
import v35_acv_probe as acv_probe  # noqa: E402
from introact_ts.actions import Action, apply_action, _mask_runs  # noqa: E402
from introact_ts.probe import materialize_for_probe, reference_scale  # noqa: E402
from introact_ts.backends import make_backend  # noqa: E402

#: Proposer: the registry's only native masked-reconstruction backend.
PROPOSER_SPEC = "moment:AutonLab/MOMENT-1-large"
#: Verifiers: CAP_RECONSTRUCT via the forecast/backcast blend only.
VERIFIER_SPECS = ("chronos:amazon/chronos-bolt-base",
                  "timesfm:google/timesfm-2.5-200m-pytorch")
#: The routed default rung (verified against the table at build time).
DEFAULT_IMPUTE_PARAMS = {"method": "linear", "min_run": 16}

ALLOWED_ROW_KEYS = (
    "sample_uid", "window_id", "dataset", "stratum", "family", "rung",
    "params", "missing_fraction", "corrupted_hash", "output_hash",
)

CODE_FILES = (
    "experiments/v35_tsfm_impute_probe.py",
    "experiments/v35_acv_probe.py",
    "experiments/v35_acv_common.py",
    "src/introact_ts/probe.py",
    "src/introact_ts/actions.py",
    "src/introact_ts/backends/base.py",
    "src/introact_ts/backends/moment.py",
)


def probe_config() -> dict:
    return {
        "proposer": PROPOSER_SPEC,
        "verifiers": list(VERIFIER_SPECS),
        "proposer_native_reconstruct": True,
        "verifier_reconstruct": "forecast/backcast blend (ForecastOnlyMixin)",
        "default_impute_params": DEFAULT_IMPUTE_PARAMS,
        "fill_sites": "all real NaN runs of the corrupted window",
        "observed_finite_values": "never modified (asserted)",
        "scale_rule": "reference_scale(corrupted window)",
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


# -- the experimental operator -----------------------------------------------------


def tsfm_reconstruct_impute(model, series: np.ndarray):
    """Fill the window's real NaN runs from the frozen model's reconstruction.

    Returns ``(filled_series, spans)``. Observed finite values are carried
    verbatim -- the operator may not touch them (§3.3) -- and the input
    array is never mutated. A window without NaN yields the probe-
    materialised series unchanged (identity) and empty spans.
    """
    x = np.asarray(series, dtype=np.float64)
    base = materialize_for_probe(x)
    spans = [(int(lo), int(hi))
             for lo, hi in _mask_runs(~np.isfinite(x))]
    y = base.copy()
    if spans:
        recs = model.reconstruct_batch(base, spans)
        for (lo, hi), r in zip(spans, recs):
            y[lo:hi] = np.asarray(r, dtype=np.float64)
    observed = np.isfinite(x)
    assert np.array_equal(y[observed], x[observed]), \
        "TSFM_RECONSTRUCT_IMPUTE modified an observed finite value"
    return y, spans


def verifier_disagreement(verifier, base, spans, fill, scale) -> dict:
    """How far the verifier's independent reconstruction sits from the fill.

    The verifier reconstructs the same masked runs from the same KEEP base
    without ever seeing the proposer's fill (flat_reconstruct reads only
    out-of-span context). Returns the scale-normalised mean absolute gap
    over filled points, or None when no span was reconstructible.
    """
    if not spans:
        return {"mean_abs_gap": None, "n_spans_valid": 0}
    recs = acv_probe.flat_reconstruct(
        verifier, [(base, spans)],
        max_span=acv_probe.MODEL_SPAN_CAPS.get(type(verifier).__name__))
    gaps, n_valid = [], 0
    for j, (lo, hi) in enumerate(spans):
        r = recs.get((0, j))
        if r is None:
            continue
        n_valid += 1
        gaps.append(np.abs(np.asarray(r, dtype=np.float64)
                           - fill[lo:hi]))
    if not gaps:
        return {"mean_abs_gap": None, "n_spans_valid": 0}
    gap = float(np.mean(np.concatenate(gaps)) / max(scale, 1e-8))
    return {"mean_abs_gap": gap, "n_spans_valid": n_valid}


# -- driver ---------------------------------------------------------------------


def _row_key(row) -> str:
    return (row["family"], row["rung"], json.dumps(row["params"], sort_keys=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data",
                    default=str(ROOT / "results" / "v33_training_data.jsonl"))
    ap.add_argument("--manifest",
                    default=str(ROOT / "results" / "p0_corpus_manifest_a.json"))
    ap.add_argument("--out",
                    default=str(ROOT / "results" / "v35_tsfm_impute_records.jsonl"))
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n-corpus", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    t0 = time.time()
    rows_all = [json.loads(l) for l in open(args.data, encoding="utf-8")]
    rows = [{k: r.get(k) for k in ALLOWED_ROW_KEYS} for r in rows_all
            if r["family"] == "IMPUTE"]
    rows.sort(key=lambda r: (r["sample_uid"], _row_key(r)))
    if args.limit:
        rows = rows[:args.limit]
    print(f"{len(rows)} routed-IMPUTE candidate rows", flush=True)

    uid_series, n_windows = acv_probe.match_windows(rows, args.n_corpus,
                                                    args.seed, args.manifest)
    print(f"matched {len(uid_series)} windows of {n_windows} "
          f"({time.time() - t0:.1f}s)", flush=True)

    by_uid = defaultdict(list)
    for r in rows:
        by_uid[r["sample_uid"]].append(r)
    uids = sorted(by_uid)

    # -- CPU arms (deterministic), hash-verified against the table -----------
    default_checked = 0
    arms = {}
    for uid in uids:
        x = uid_series[uid]
        y_default = np.asarray(
            apply_action(x, Action.IMPUTE, **DEFAULT_IMPUTE_PARAMS).series,
            dtype=np.float64)
        arms[uid] = {
            "x_keep": materialize_for_probe(x),
            "default": y_default,
            "scale": reference_scale(x),
        }
        for r in by_uid[uid]:
            out = apply_action(x, Action.IMPUTE, **r["params"])
            if hash_array(out.series) != r["output_hash"]:
                raise SystemExit(f"operator output mismatch for {uid}")
            if r["rung"] == "default":
                if r["params"] != DEFAULT_IMPUTE_PARAMS:
                    raise SystemExit("default rung params drifted: "
                                     f"{r['params']}")
                default_checked += 1
    print(f"CPU arms built; {default_checked} default-rung rows verified "
          f"against DEFAULT_IMPUTE_PARAMS", flush=True)

    # -- models: proposer + verifiers, loaded once ----------------------------
    t2 = time.time()
    proposer = make_backend(PROPOSER_SPEC, device=args.device)
    verifiers = [make_backend(s, device=args.device,
                              horizon=acv_probe.POOL_HORIZON)
                 for s in VERIFIER_SPECS]
    revisions = {s: acv_probe.resolve_revision(s)
                 for s in (PROPOSER_SPEC,) + VERIFIER_SPECS}
    print(f"loaded models in {time.time() - t2:.1f}s: {revisions}",
          flush=True)

    # -- TSFM arm + verifier disagreement --------------------------------------
    tsfm_arm, verifier_gaps = {}, {}
    for uid in uids:
        x = uid_series[uid]
        y_tsfm, spans = tsfm_reconstruct_impute(proposer, x)
        tsfm_arm[uid] = (y_tsfm, spans)
        verifier_gaps[uid] = {
            s: verifier_disagreement(v, arms[uid]["x_keep"], spans, y_tsfm,
                                     arms[uid]["scale"])
            for s, v in zip(VERIFIER_SPECS, verifiers)}
    print(f"TSFM arm built for {len(uids)} windows "
          f"({time.time() - t2:.1f}s total)", flush=True)

    ch, code = config_hash(), code_hashes()
    out_path = Path(args.out)
    with out_path.open("w", encoding="utf-8") as f:
        for uid in uids:
            y_tsfm, spans = tsfm_arm[uid]
            a = arms[uid]
            for r in sorted(by_uid[uid], key=_row_key):
                rec = {
                    "sample_uid": uid,
                    "window_id": r["window_id"],
                    "dataset": r["dataset"],
                    "stratum": r["stratum"],
                    "family": "IMPUTE",
                    "rung": r["rung"],
                    "params": r["params"],
                    "missing_fraction": r["missing_fraction"],
                    "geometry": acv.geometry_of(uid_series[uid]),
                    "corrupted_hash": r["corrupted_hash"],
                    "input_hash": r["corrupted_hash"],
                    "arm_hashes": {
                        "keep": hash_array(a["x_keep"]),
                        "default": hash_array(a["default"]),
                        "candidate": r["output_hash"],
                        "tsfm": hash_array(y_tsfm),
                    },
                    "candidate_output_hash_verified": True,
                    "tsfm_spans": [[int(lo), int(hi)] for lo, hi in spans],
                    "tsfm_n_filled": int(sum(hi - lo for lo, hi in spans)),
                    "reference_scale": float(a["scale"]),
                    "verifier_disagreement": verifier_gaps[uid],
                    "model": {"proposer": PROPOSER_SPEC,
                              "verifiers": list(VERIFIER_SPECS),
                              "revisions": revisions,
                              "status": "cross-model verification, single "
                                        "native-reconstruction backend"},
                    "config_hash": ch,
                    "code_hashes": code,
                }
                f.write(json.dumps(rec, sort_keys=True, default=float) + "\n")

    file_hash = hashlib.sha256(out_path.read_bytes()).hexdigest()
    print(json.dumps({
        "n_records": len(rows), "n_windows": len(uids),
        "records_sha256": file_hash,
        "elapsed_seconds": time.time() - t0}, indent=1), flush=True)
    print(f"___V35_TSFM_IMPUTE_PROBE_DONE___ wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
