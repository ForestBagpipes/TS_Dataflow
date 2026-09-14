"""Build the frozen formal OOD stress set for v3.3 (Phase 4).

Pre-registered in ``docs/v3_3_mast_pics_design.md`` §2.1: a fresh frozen seed
(313), 64 synthetic clean-OOD windows (16 each of random_walk, staircase,
pulse_train, sawtooth) and 32 real cross-domain windows (exchange/solar),
disjoint by content identity from the calibration corpus and deployment seeds
0/1/2. The 56 OOD windows inside the seed-101 corpus remain the historical
development stress set and are not reused for the formal gate.

Outputs:
  results/v33_ood_manifest.json    window-level manifest + hashes
  results/v33_ood_candidates.jsonl candidate rows in the v3.3 schema, with
                                   ``var_ratio`` (post/pre action variance)
                                   added for the OOD attribution report
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from build_calibration import build as build_calibration, ident  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402
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

OOD_SEED = 313


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-clean-ood", dest="n_clean_ood", type=int, default=64)
    ap.add_argument("--n-real-ood", dest="n_real_ood", type=int, default=32)
    ap.add_argument("--seed", type=int, default=OOD_SEED)
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=16)
    ap.add_argument("--manifest", default=str(ROOT / "results" / "p0_corpus_manifest_a.json"))
    ap.add_argument("--out-manifest", default=str(ROOT / "results" / "v33_ood_manifest.json"))
    ap.add_argument("--out", default=str(ROOT / "results" / "v33_ood_candidates.jsonl"))
    args = ap.parse_args()

    spec = CorpusSpec(
        n_contaminated=0, n_clean=0, n_hard=0, n_rare_valid=0,
        n_changepoint=0, n_clean_ood=args.n_clean_ood,
        n_real_ood=args.n_real_ood, window_len=512, seed=args.seed)
    windows = build_corpus(spec, source="mixed")
    print(f"built {len(windows)} OOD windows", flush=True)

    # Content-identity disjointness against calibration + deployment seeds.
    banned = set()
    for s in (0, 1, 2):
        dspec = SCALES["xl"]
        dspec.seed = s
        for w in build_corpus(dspec, source="mixed"):
            banned.add(ident(w))
    cal_windows, _ = build_calibration(n=1600, seed=101, source="mixed")
    for w in cal_windows:
        banned.add(ident(w))
    overlap = sum(1 for w in windows if ident(w) in banned)
    print(f"identity overlap with calibration/deployment: {overlap}", flush=True)

    manifest_hash = hashlib.sha256(
        Path(args.manifest).read_bytes()).hexdigest()
    manifest = {
        "seed": args.seed, "n_clean_ood": args.n_clean_ood,
        "n_real_ood": args.n_real_ood, "window_len": 512,
        "overlap_with_calibration_or_deployment": overlap,
        "forms": dict(Counter(w.dataset for w in windows)),
        "records": [{
            "window_id": int(w.window_id), "sample_uid": sample_uid(w),
            "dataset": w.dataset, "stratum": w.stratum,
            "corrupted_hash": hash_array(w.series),
            "clean_hash": hash_array(w.clean_series),
        } for w in windows],
    }
    m_path = Path(args.out_manifest)
    m_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    ood_manifest_hash = hashlib.sha256(m_path.read_bytes()).hexdigest()
    print(f"manifest -> {m_path} ({ood_manifest_hash[:16]}...)", flush=True)

    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)
    agent = IntroActAgent(
        models,
        AgentConfig(
            verification=VerifyConfig(tau=0.02),
            policy=PolicyConfig(enable_param_ladder=True),
            n_jobs=args.n_jobs,
        ),
    )
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
        "experiments/v33_ood_stress.py",
        "experiments/v33_labels.py",
        "experiments/metrics_common.py",
    ]
    code_hashes = {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
                   for rel in code_files if (ROOT / rel).exists()}
    config_hash = hashlib.sha256(
        json.dumps(vars(args), sort_keys=True).encode()).hexdigest()

    n_written = 0
    with Path(args.out).open("w", encoding="utf-8") as out_f:
        for idx, (w, s) in enumerate(zip(windows, states)):
            cands = propose_actions(s, [], policy_cfg)
            mutating = [c for c in cands if c[0] not in (Action.KEEP, Action.QUARANTINE, Action.ABSTAIN)]
            original = np.asarray(w.series, dtype=np.float64).copy()
            scale = reference_scale(original)
            center = agent._calib.centers[idx]
            spread = agent._calib.spreads[idx]
            rs = route_source(s, policy_cfg)
            before_probe = agent._probes[idx]
            profile = agent._profiles[idx]
            var_before = float(np.nanvar(original))

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
                row = {
                    "window_id": int(w.window_id),
                    "sample_uid": sample_uid(w),
                    "dataset": w.dataset,
                    "stratum": w.stratum,
                    "true_kind": w.contamination or "null",
                    "corrupted_hash": hash_array(w.series),
                    "clean_hash": hash_array(w.clean_series),
                    "manifest_hash": manifest_hash,
                    "ood_manifest_hash": ood_manifest_hash,
                    "code_hashes": code_hashes,
                    "config_hash": config_hash,
                    "family": action.value,
                    "rung": rung,
                    "params": _jsonify(params),
                    "features": _jsonify(dict(zip(shield.feature_names, feats.values.tolist()))),
                    "profile": _jsonify(profile),
                    "var_ratio": float(np.nanvar(y) / max(var_before, 1e-12)),
                    "delta_utility": float(delta_u),
                    "struct_distortion": float(report.distortion),
                    "risk": float(risk),
                    "episode_proposal": True,
                    **{k: labels[k] for k in (
                        "true_loss", "harmful", "true_repair_gain",
                        "beneficial", "safe", "beneficial_and_safe",
                        "before_nmse", "after_nmse", "discard_share",
                        "missing_fraction", "forward_fill_baseline_hash",
                        "output_hash", "keep_input_hash")},
                }
                out_f.write(json.dumps(row) + "\n")
                n_written += 1
            out_f.flush()

    print(f"___V33_OOD_DONE___ wrote {args.out}, {n_written} candidates "
          f"on {len(windows)} windows, overlap={overlap}", flush=True)


if __name__ == "__main__":
    main()
