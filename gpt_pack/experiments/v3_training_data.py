"""Generate v3-pre training data: features and labels for every routed candidate.

For each calibration window, run the existing proposer, execute every candidate
in the sandbox, and record:
  - feature vector (whitelist)
  - true labels (blacklist, evaluation namespace only)
  - provenance fields (sample_uid, hashes, manifest hash, code hash, config hash)

The output is used to train and calibrate the ContextualShield.
"""

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from build_calibration import build as build_calibration  # noqa: E402
from metrics_common import canonical_nmse, damage, repair_rmsd, ref_var  # noqa: E402
from introact_ts.actions import Action, apply_action  # noqa: E402
from introact_ts.agent import AgentConfig, IntroActAgent, USE_DEPTH  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.calibration import RISK_WEIGHTS, recalibrate_one  # noqa: E402
from introact_ts.policy import PolicyConfig, propose_actions  # noqa: E402
from introact_ts.probe import SIGNAL_NAMES, probe_window, reference_scale  # noqa: E402
from introact_ts.structure import structure_distortion  # noqa: E402
from introact_ts.types import Verdict  # noqa: E402
from introact_ts.verify import action_risk, improvement_consistency, improvement_depth, verify, VerifyConfig  # noqa: E402
from introact_ts.contextual_shield import ContextualShield, ShieldConfig  # noqa: E402


def _hash_array(a: np.ndarray) -> str:
    x = np.asarray(a, dtype=np.float64).copy()
    x[~np.isfinite(x)] = np.nan
    return hashlib.sha256(np.round(x, 6).tobytes()).hexdigest()


def sample_uid(window) -> str:
    clean = window.clean_series
    corrupted = window.series
    clean_hash = _hash_array(clean) if clean is not None else "no_clean"
    corrupted_hash = _hash_array(corrupted)
    true_kind = window.contamination or "null"
    return f"{window.dataset}:{window.stratum}:{true_kind}:{clean_hash}:{corrupted_hash}"


def _jsonify(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    return obj


def route_source(state, policy_cfg):
    defect = state.dominant_defect
    units = dict(state.defect_units)
    if defect == "shift":
        return "primary"
    units.pop(defect, None)
    if units:
        best = max(units, key=units.get)
        if units[best] >= policy_cfg.secondary_threshold and best == "shift":
            return "secondary"
    return "other"


def _rung_of(action, params):
    from introact_ts.policy import LADDER, _key
    table = LADDER.get(action, {})
    for name, p in table.items():
        if _key(p) == _key(params):
            return name
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
    ap.add_argument("--manifest", default=str(ROOT / "results" / "p0_corpus_manifest_a.json"))
    ap.add_argument("--out", default=str(ROOT / "results" / "v32_training_data.jsonl"))
    ap.add_argument("--sanity", default=str(ROOT / "results" / "v32_feature_sanity.json"))
    args = ap.parse_args()

    manifest_hash = hashlib.sha256(
        Path(args.manifest).read_bytes()).hexdigest()

    windows, _ = build_calibration(n=args.n, seed=args.seed, source=args.source, verbose=False)
    byid = {w.window_id: w for w in windows}
    print(f"built {len(windows)} windows", flush=True)

    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)
    agent = IntroActAgent(
        models,
        AgentConfig(
            verification=VerifyConfig(tau=0.02),
            policy=PolicyConfig(enable_param_ladder=True),
            n_jobs=args.n_jobs,
        ),
    )
    print("perceiving corpus", flush=True)
    states = agent.perceive(windows)
    print("perception done", flush=True)

    shield = ContextualShield(ShieldConfig())
    policy_cfg = PolicyConfig(enable_param_ladder=True)

    code_files = [
        "src/introact_ts/contextual_shield.py",
        "src/introact_ts/actions.py",
        "src/introact_ts/policy.py",
        "src/introact_ts/probe.py",
        "src/introact_ts/structure.py",
        "src/introact_ts/verify.py",
        "experiments/v3_training_data.py",
        "experiments/metrics_common.py",
    ]
    code_hashes = {}
    for rel in code_files:
        p = ROOT / rel
        if p.exists():
            code_hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    config = vars(args)
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True).encode()).hexdigest()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    with out_path.open("w", encoding="utf-8") as out_f:
        for w, s in zip(windows, states):
            cands = propose_actions(s, [], policy_cfg)
            # Only mutating candidates get evaluated.
            mutating = [c for c in cands if c[0] not in (Action.KEEP, Action.QUARANTINE, Action.ABSTAIN)]
            if not mutating:
                continue

            original = np.asarray(w.series, dtype=np.float64).copy()
            scale = reference_scale(original)
            peer_idx = windows.index(w)
            center = agent._calib.centers[peer_idx]
            spread = agent._calib.spreads[peer_idx]
            rs = route_source(s, policy_cfg)
            before_probe = agent._probes[peer_idx]

            for action, params in mutating:
                outcome = apply_action(original, action, **params)
                if not outcome.applicable:
                    continue
                y = np.asarray(outcome.series, dtype=np.float64)
                after = probe_window(y, models, scale, agent.cfg.probe)
                delta_u = after.utility - s.utility
                z_after, _ = recalibrate_one(
                    after.vector, center, spread, SIGNAL_NAMES, RISK_WEIGHTS)
                report = structure_distortion(
                    original, y, action, outcome.params, touched=outcome.touched)
                consistency = improvement_consistency(s.z, z_after)
                depth = improvement_depth(s.z, z_after)
                risk = action_risk(depth if USE_DEPTH else s.confidence,
                                   outcome.cost, consistency)

                rung = _rung_of(action, params)
                feats = shield.extract(
                    window=w, state=s, action=action, params=params,
                    outcome=outcome, before=before_probe, after=after,
                    struct_report=report, cost=outcome.cost, rung=rung,
                    route_source=rs,
                    improvement_consistency=consistency,
                    improvement_depth=depth, action_risk=risk)

                # Labels.
                c = np.asarray(w.clean_series, dtype=np.float64)
                lo = int(outcome.params.get("lo", 0)) if action is Action.RESEGMENT else 0
                hi = lo + len(y)
                rv = ref_var(c)
                before_nmse = canonical_nmse(original, c, rv)
                after_nmse = canonical_nmse(y, c[lo:hi], rv)
                worse = 1.0 if after_nmse > before_nmse + 1e-9 else 0.0
                discard = 1.0 - (hi - lo) / len(original)
                loss = damage(worse, discard)
                repair_gain = before_nmse - after_nmse
                beneficial = 1.0 if repair_gain > 1e-9 else 0.0
                safe = 1.0 if loss <= 0.03 else 0.0
                beneficial_and_safe = 1.0 if beneficial and safe else 0.0
                rmsd = repair_rmsd(y, c[lo:hi])

                row = {
                    "window_id": int(w.window_id),
                    "sample_uid": sample_uid(w),
                    "dataset": w.dataset,
                    "stratum": w.stratum,
                    "true_kind": w.contamination or "null",
                    "corrupted_hash": _hash_array(w.series),
                    "clean_hash": _hash_array(w.clean_series) if w.clean_series is not None else None,
                    "manifest_hash": manifest_hash,
                    "code_hashes": code_hashes,
                    "config_hash": config_hash,
                    "family": action.value,
                    "rung": rung,
                    "params": _jsonify(params),
                    "features": _jsonify(dict(zip(shield.feature_names, feats.values.tolist()))),
                    "true_loss": float(loss),
                    "harmful": float(1.0 - safe),
                    "true_repair_gain": float(repair_gain),
                    "beneficial": float(beneficial),
                    "safe": float(safe),
                    "beneficial_and_safe": float(beneficial_and_safe),
                    "before_nmse": float(before_nmse),
                    "after_nmse": float(after_nmse),
                    "repair_rmsd": float(rmsd),
                    "delta_utility": float(delta_u),
                    "struct_distortion": float(report.distortion),
                    "risk": float(risk),
                }
                out_f.write(json.dumps(row) + "\n")
                n_written += 1
                if n_written % 500 == 0:
                    print(f"  {n_written} candidates written", flush=True)
            out_f.flush()

    # Feature sanity report: catch constant, non-finite, or scale-broken
    # features before any model is trained on this table.
    from introact_ts.contextual_shield import NUMERICAL_FEATURES
    report = {"n_candidates": n_written, "features": {}}
    # Re-read what was written so the report audits the file, not memory.
    numeric = {name: [] for name in NUMERICAL_FEATURES}
    with out_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            for name in NUMERICAL_FEATURES:
                numeric[name].append(float(row["features"].get(name, 0.0)))
    for name, vals in numeric.items():
        v = np.asarray(vals, dtype=np.float64)
        finite = np.isfinite(v)
        uniq = np.unique(v[finite])
        report["features"][name] = {
            "finite_rate": float(finite.mean()),
            "n_distinct": int(len(uniq)),
            "min": float(v[finite].min()) if finite.any() else None,
            "max": float(v[finite].max()) if finite.any() else None,
            "constant": bool(len(uniq) <= 1),
        }
    report["constant_features"] = sorted(
        n for n, r in report["features"].items() if r["constant"])
    report["all_features_finite"] = bool(all(
        r["finite_rate"] == 1.0 for r in report["features"].values()))
    Path(args.sanity).write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"___V3_TRAINING_DATA_DONE___ wrote {args.out}, {n_written} candidates, "
          f"sanity -> {args.sanity}", flush=True)


if __name__ == "__main__":
    main()
