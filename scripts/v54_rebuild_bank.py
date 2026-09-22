#!/usr/bin/env python3
"""v54 stage 4a step 1: rebuild the replay-bank state snapshots under v54-full22.

The bank's utility labels (per-action realised MASE against the reference) come
from the prediction cache and do not change with the state definition; only the
22-dimensional state vector of every record is recomputed, by re-reading the
immutable v47 replay inputs with the v54 ``introact_ts.v44.state``.

Two artifacts per (block, backbone), under ``results/v54/replay/bank/``:

* ``{block}_{backbone}.npz``  -- the materialised bank: per-action state
  vectors, utilities, metrics and legality flags plus episode metadata
  (including ``parent``, which the parent-clustered scoring needs);
* ``{block}_{backbone}.json`` -- manifest and validation evidence.

Validation, per (block, backbone):

1. every scored KEEP record's intervention block is exactly zero (v54 §5);
2. a deterministic sample of episodes has its full state vector recomputed from
   the raw stored objects (mask, reference, candidate input, reference
   prediction) and compared bitwise with the snapshot;
3. the pre-fix formula (v44-full22: NaN-referenced difference, then
   ``nan_to_num``) is evaluated inline on the same objects, demonstrating that
   the four magnitude features were identically zero before the fix whenever a
   repair existed, and are non-zero now.

Nothing is written outside ``results/v54/``.
"""

from __future__ import annotations

import argparse
import collections
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v44 import masking as M
from introact_ts.v44 import protocol as P
from introact_ts.v44 import state as ST

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v54_common import (BACKBONES, OUT, ROOT, clean, code_hashes,
                        load_catalogs, sha, write)

STATE_DIM = 22
INTERVENTION = slice(12, 17)
SAMPLE_EPISODES = 100


def old_intervention_features(candidate: np.ndarray, reference: np.ndarray,
                              scale: float) -> np.ndarray:
    """The pre-fix v44-full22 formula, kept inline for validation only."""
    candidate = np.asarray(candidate, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    changed = ~np.isclose(candidate, reference, rtol=0.0, atol=0.0, equal_nan=True)
    delta = np.where(changed, candidate - reference, 0.0)
    delta = np.nan_to_num(delta, nan=0.0, posinf=0.0, neginf=0.0)
    mean_abs = float(np.mean(np.abs(delta))) / scale
    max_abs = float(np.max(np.abs(delta))) / scale if delta.size else 0.0
    fraction = float(changed.mean())
    idx = np.flatnonzero(changed)
    slope = (float(np.polyfit(idx.astype(np.float64), delta[idx], 1)[0])
             if len(idx) >= 3 else 0.0)
    window = min(ST.RECENT_WINDOW, len(delta))
    near_origin = float(np.mean(np.abs(delta[-window:]))) / scale
    return np.array([mean_abs, max_abs, fraction, slope / scale, near_origin])


def snapshot_block(root: Path, block: str, backbone: str) -> dict:
    catalogs = load_catalogs(root, block, backbone)
    n = len(catalogs)

    manifest = json.loads(
        (root / C.REPLAY / "inputs" / f"{block}.json").read_text())
    rows_by_episode = {r["episode"]: r for r in manifest["rows"]}

    states = {a: np.full((n, STATE_DIM), np.nan) for a in P.ACTIONS}
    utility = {a: np.full(n, np.nan) for a in P.ACTIONS}
    metrics = {m: {a: np.full(n, np.nan) for a in P.ACTIONS}
               for m in ("mase", "rmsse", "mae", "mse")}
    legal = {a: np.zeros(n, bool) for a in P.ACTIONS}
    applicable = {a: np.zeros(n, bool) for a in P.ACTIONS}
    for i, c in enumerate(catalogs):
        usable = set(c.legal())
        for a in P.ACTIONS:
            e = c.actions.get(a)
            if e is None:
                continue
            applicable[a][i] = e.applicable
            legal[a][i] = a in usable and e.state_vector is not None
            if e.state_vector is not None:
                states[a][i] = e.state_vector
            if e.utility is not None:
                utility[a][i] = e.utility
            for m in metrics:
                value = getattr(e, m, None)
                if value is not None:
                    metrics[m][a][i] = value

    arrays: dict[str, np.ndarray] = {
        "episode": np.asarray([c.episode for c in catalogs]),
        "parent": np.asarray([c.parent for c in catalogs]),
        "source": np.asarray([c.source for c in catalogs]),
        "horizon": np.asarray([c.horizon for c in catalogs], dtype=np.int64),
        "severity": np.asarray([c.severity for c in catalogs]),
        "pattern": np.asarray([c.pattern for c in catalogs]),
    }
    for a in P.ACTIONS:
        arrays[f"state|{a}"] = states[a]
        arrays[f"utility|{a}"] = utility[a]
        arrays[f"legal|{a}"] = legal[a]
        arrays[f"applicable|{a}"] = applicable[a]
        for m in metrics:
            arrays[f"{m}|{a}"] = metrics[m][a]

    out_dir = OUT / "replay" / "bank"
    out_dir.mkdir(parents=True, exist_ok=True)
    npz_path = out_dir / f"{block}_{backbone}.npz"
    with npz_path.open("wb") as handle:
        np.savez(handle, **arrays)

    # ---------------------------------------------------------- validation
    # 1. KEEP's intervention block is exactly zero on every scored record.
    keep_states = states[P.REFERENCE_ACTION]
    scored_keep = np.isfinite(keep_states).all(1)
    keep_intervention = keep_states[scored_keep][:, INTERVENTION]
    n_keep = int(scored_keep.sum())
    if n_keep and not np.array_equal(keep_intervention,
                                     np.zeros_like(keep_intervention)):
        raise AssertionError(f"{block}/{backbone}: KEEP intervention not all zero")

    # 2./3. Recompute from the raw stored objects on a deterministic sample.
    rng = np.random.default_rng(101)
    sample = sorted(rng.choice(n, min(SAMPLE_EPISODES, n), replace=False).tolist())
    repairs = {"records": 0, "old_zero": 0, "new_nonzero": 0,
               "no_repair_zero": 0, "bitwise_equal": 0}
    with np.load(root / C.REPLAY / "inputs" / f"{block}.npz",
                 allow_pickle=False) as store, \
            np.load(root / C.REPLAY / "tsicl" / f"{block}.npz",
                    allow_pickle=False) as tsicl, \
            np.load(root / C.REPLAY / "saits" / f"{block}.npz",
                    allow_pickle=False) as saits:
        stores = (store, tsicl, saits)

        def candidate(key: str, action: str) -> np.ndarray | None:
            name = f"{key}|{action}"
            for source in stores:
                if name in source.files:
                    return source[name]
            return None

        for i in sample:
            c = catalogs[i]
            row = rows_by_episode[c.episode]
            mask = M.build_mask(c.source, c.parent, c.origin, c.horizon,
                                c.pattern, c.severity,
                                length=len(c.reference_target),
                                n_channels=row["n_channels"])
            scale = ST.robust_scale(c.reference_target)
            for a in P.ACTIONS:
                e = c.actions.get(a)
                if e is None or e.state_vector is None:
                    continue
                target = candidate(c.episode, a)
                if target is None:
                    raise AssertionError(f"{c.episode}/{a}: candidate array missing")
                rebuilt = ST.state_vector_from_mask(
                    mask=mask, reference_target=c.reference_target,
                    period=c.period, candidate_target=target,
                    reference_prediction=c.reference_prediction)
                if not np.array_equal(rebuilt, e.state_vector):
                    raise AssertionError(
                        f"{c.episode}/{a}: snapshot state differs from raw rebuild")
                repairs["bitwise_equal"] += 1

                repaired = ~np.isfinite(c.reference_target) & np.isfinite(target)
                if not repaired.any():
                    if np.array_equal(e.state_vector[INTERVENTION], np.zeros(5)):
                        repairs["no_repair_zero"] += 1
                    continue
                repairs["records"] += 1
                old = old_intervention_features(target, c.reference_target, scale)
                if np.array_equal(old[[0, 1, 3, 4]], np.zeros(4)):
                    repairs["old_zero"] += 1
                if e.state_vector[12] > 0.0:
                    repairs["new_nonzero"] += 1

    per_action_support = {a: int(np.isfinite(utility[a]).sum()) for a in P.ACTIONS}
    payload = {
        "stage": "v54-replay-bank-rebuild",
        "state_version": ST.STATE_VERSION,
        "block": block,
        "backbone": backbone,
        "source_replay": C.REPLAY,
        "episodes": n,
        "parents": int(len({c.parent for c in catalogs})),
        "sources": sorted({c.source for c in catalogs}),
        "per_action_support": per_action_support,
        "snapshot_npz": str(npz_path.relative_to(ROOT)),
        "snapshot_sha256": sha(npz_path),
        "input_hashes": {
            "inputs": sha(root / C.REPLAY / "inputs" / f"{block}.npz"),
            "tsicl": sha(root / C.REPLAY / "tsicl" / f"{block}.npz"),
            "saits": sha(root / C.REPLAY / "saits" / f"{block}.npz"),
            "predictions": sha(root / C.REPLAY / "forecast" / block / backbone
                               / "predictions.npz"),
        },
        "validation": {
            "keep_records_checked": n_keep,
            "keep_intervention_all_zero": True,
            "sample_episodes": len(sample),
            "sample_records_bitwise_equal": repairs["bitwise_equal"],
            "records_with_repairs": repairs["records"],
            "old_formula_magnitude_all_zero": repairs["old_zero"],
            "new_formula_mean_abs_positive": repairs["new_nonzero"],
            "no_repair_records_zero": repairs["no_repair_zero"],
        },
        "code_sha256": code_hashes(root) | {
            "scripts/v54_rebuild_bank.py": sha(Path(__file__).resolve())},
        "heldout_labels_read": 0,
    }
    write(out_dir / f"{block}_{backbone}.json", clean(payload))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--blocks", default="bankx,train_eval")
    parser.add_argument("--backbones", default=",".join(BACKBONES))
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    summary = {}
    for block in args.blocks.split(","):
        for backbone in args.backbones.split(","):
            payload = snapshot_block(root, block.strip(), backbone.strip())
            summary[f"{block}/{backbone}"] = {
                "episodes": payload["episodes"],
                "parents": payload["parents"],
                "validation": payload["validation"],
            }
            print(json.dumps({block + "/" + backbone: summary[f"{block}/{backbone}"]},
                             indent=1), flush=True)
    write(OUT / "replay" / "bank" / "rebuild_summary.json", clean({
        "stage": "v54-replay-bank-rebuild",
        "state_version": ST.STATE_VERSION,
        "blocks": summary,
        "runtime_seconds": time.perf_counter() - began,
    }))


if __name__ == "__main__":
    main()
