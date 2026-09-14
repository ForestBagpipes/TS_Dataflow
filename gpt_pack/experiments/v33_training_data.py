"""Generate the v3.3 candidate table: features + action-semantic labels.

Derived from ``v3_training_data.py`` (the v3.2 table). Same frozen corpus,
same proposer, same operator outputs; the differences are exactly the ones
pre-registered in ``docs/v3_3_mast_pics_design.md``:

  - labels come from ``v33_labels.compute_action_labels`` (IMPUTE KEEP
    counterfactual = the probe-materialised series);
  - every row carries the deployable pre-action ``profile`` vector (the same
    12-dim vector the support index will query), ``forward_fill_baseline_hash``
    and ``output_hash``;
  - the sanity report re-reads the written file.

Hard integrity gate (checked by ``v33_label_flip_audit.py``, not here):
operator-output identity and unchanged DENOISE/DESPIKE labels against the
v3.2 table on all shared keys. The v3.2 table predates ``output_hash``, so
identity is certified by bit-identical params plus bit-identical before/after
NMSE on non-IMPUTE families -- deterministic functions of the output -- and
``output_hash`` is recorded from this table onward as the direct anchor.

Usage:
    python experiments/v33_training_data.py --device cuda --n-jobs 16
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from build_calibration import build as build_calibration  # noqa: E402
from metrics_common import repair_rmsd  # noqa: E402
from v33_labels import compute_action_labels, hash_array  # noqa: E402
from introact_ts.actions import Action, apply_action  # noqa: E402
from introact_ts.agent import AgentConfig, IntroActAgent, USE_DEPTH  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.calibration import RISK_WEIGHTS, recalibrate_one  # noqa: E402
from introact_ts.policy import PolicyConfig, propose_actions  # noqa: E402
from introact_ts.probe import SIGNAL_NAMES, probe_window, reference_scale  # noqa: E402
from introact_ts.structure import structure_distortion  # noqa: E402
from introact_ts.verify import action_risk, improvement_consistency, improvement_depth, VerifyConfig  # noqa: E402
from introact_ts.contextual_shield import ContextualShield, ShieldConfig  # noqa: E402
from v3_training_data import _jsonify, route_source, sample_uid, _rung_of  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=16)
    ap.add_argument("--manifest", default=str(ROOT / "results" / "p0_corpus_manifest_a.json"))
    ap.add_argument("--out", default=str(ROOT / "results" / "v33_training_data.jsonl"))
    ap.add_argument("--sanity", default=str(ROOT / "results" / "v33_feature_sanity.json"))
    args = ap.parse_args()

    manifest_hash = hashlib.sha256(
        Path(args.manifest).read_bytes()).hexdigest()

    windows, _ = build_calibration(n=args.n, seed=args.seed, source=args.source, verbose=False)
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
        "experiments/v33_training_data.py",
        "experiments/v33_labels.py",
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
        for idx, (w, s) in enumerate(zip(windows, states)):
            cands = propose_actions(s, [], policy_cfg)
            mutating = [c for c in cands if c[0] not in (Action.KEEP, Action.QUARANTINE, Action.ABSTAIN)]
            if not mutating:
                continue

            original = np.asarray(w.series, dtype=np.float64).copy()
            scale = reference_scale(original)
            center = agent._calib.centers[idx]
            spread = agent._calib.spreads[idx]
            rs = route_source(s, policy_cfg)
            before_probe = agent._probes[idx]
            profile = agent._profiles[idx]

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

                c = np.asarray(w.clean_series, dtype=np.float64)
                lo = int(outcome.params.get("lo", 0)) if action is Action.RESEGMENT else 0
                labels = compute_action_labels(
                    action, original, y, c,
                    touched=outcome.touched, params=outcome.params)
                rmsd = repair_rmsd(y, c[lo:lo + len(y)])

                row = {
                    "window_id": int(w.window_id),
                    "sample_uid": sample_uid(w),
                    "dataset": w.dataset,
                    "stratum": w.stratum,
                    "true_kind": w.contamination or "null",
                    "corrupted_hash": hash_array(w.series),
                    "clean_hash": hash_array(w.clean_series) if w.clean_series is not None else None,
                    "manifest_hash": manifest_hash,
                    "code_hashes": code_hashes,
                    "config_hash": config_hash,
                    "family": action.value,
                    "rung": rung,
                    "params": _jsonify(params),
                    "features": _jsonify(dict(zip(shield.feature_names, feats.values.tolist()))),
                    "profile": _jsonify(profile),
                    "true_loss": labels["true_loss"],
                    "harmful": labels["harmful"],
                    "true_repair_gain": labels["true_repair_gain"],
                    "beneficial": labels["beneficial"],
                    "safe": labels["safe"],
                    "beneficial_and_safe": labels["beneficial_and_safe"],
                    "before_nmse": labels["before_nmse"],
                    "after_nmse": labels["after_nmse"],
                    "repair_rmsd": float(rmsd),
                    "delta_utility": float(delta_u),
                    "struct_distortion": float(report.distortion),
                    "risk": float(risk),
                    # v3.3 action-semantic and integrity fields
                    "target_mask_n": labels["target_mask_n"],
                    "target_mask_nrmse_before": labels["target_mask_nrmse_before"],
                    "target_mask_nrmse_after": labels["target_mask_nrmse_after"],
                    "target_mask_gain": labels["target_mask_gain"],
                    "observed_support_nrmse_before": labels["observed_support_nrmse_before"],
                    "observed_support_nrmse_after": labels["observed_support_nrmse_after"],
                    "observed_support_drift": labels["observed_support_drift"],
                    "missing_fraction": labels["missing_fraction"],
                    "missing_recovery_rate": labels["missing_recovery_rate"],
                    "discard_share": labels["discard_share"],
                    "forward_fill_baseline_hash": labels["forward_fill_baseline_hash"],
                    "output_hash": labels["output_hash"],
                    "keep_input_hash": labels["keep_input_hash"],
                }
                out_f.write(json.dumps(row) + "\n")
                n_written += 1
                if n_written % 500 == 0:
                    print(f"  {n_written} candidates written", flush=True)
            out_f.flush()

    # Feature sanity report: re-read the file so the report audits what was
    # written, not what was in memory.
    from introact_ts.contextual_shield import NUMERICAL_FEATURES
    report = {"n_candidates": n_written, "features": {}}
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

    print(f"___V33_TRAINING_DATA_DONE___ wrote {args.out}, {n_written} candidates, "
          f"sanity -> {args.sanity}", flush=True)


if __name__ == "__main__":
    main()
