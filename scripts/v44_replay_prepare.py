#!/usr/bin/env python3
"""v4.4 Stage A -- CPU preparation of the replay inputs.

For every episode of a block this builds the deterministic mask, the masked
panel, the future target, the two metrics denominators, and the candidate
inputs of the three CPU actions (KEEP / FFILL / CONTEXT_RIDGE).  The two
TS-ICL actions are produced later by the GPU stage, which rebuilds the same
mask from the frozen identity tuple.

Nothing here reads a calibration or test row, and no model is loaded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from introact_ts.v44 import actions as A
from introact_ts.v44 import masking as M
from introact_ts.v44 import metrics as ME
from introact_ts.v44 import pipeline as PL
from introact_ts.v44 import protocol as P
from introact_ts.v44.hashing import array_hash, json_hash

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v44/replay"
CPU_ACTIONS = ("KEEP", "FFILL", "CONTEXT_RIDGE")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def build_block(root: Path, block: str) -> dict:
    specs = PL.episode_specs(root, block)
    if not specs:
        raise SystemExit(f"empty episode grid for block {block}")
    arrays: dict[str, np.ndarray] = {}
    rows: list[dict] = []
    skipped: list[dict] = []
    began = time.perf_counter()

    for spec, raw_context, masked, future in PL.iter_panels(root, specs):
        key = spec.episode_id
        reference = masked[:, 0].copy()
        # The denominator comes from the untouched context, so it is identical
        # for every pattern of the same window.
        mase_scale, rmsse_scale = ME.seasonal_scale(raw_context[:, 0], spec.period)
        if not np.isnan(reference).any():
            skipped.append({"episode": key,
                            "reason": "raw context has no gap after masking"})
            continue

        candidates: dict[str, dict] = {}
        for name in CPU_ACTIONS:
            outcome = A.apply_action(name, masked)
            candidates[name] = {
                "applicable": outcome.applicable,
                "reason": outcome.reason,
                "input_hash": outcome.input_hash if outcome.applicable else None,
            }
            if outcome.applicable:
                arrays[f"{key}|{name}"] = outcome.target.astype(np.float64)
        arrays[f"{key}|reference"] = reference
        arrays[f"{key}|future"] = future.astype(np.float64)

        mask = np.isnan(masked)
        rows.append({
            "episode": key,
            "source": spec.source,
            "parent": spec.parent,
            "origin": spec.origin,
            "read_start": spec.read_start,
            "horizon": spec.horizon,
            "pattern": spec.pattern,
            "severity": spec.severity,
            "severity_source": spec.severity_source,
            "block": block,
            "mask_hash": array_hash(mask),
            "mask_seed": M.mask_seed(spec.source, spec.parent, spec.origin,
                                     spec.horizon, spec.pattern),
            "missing_count": int(mask[:, 0].sum()),
            "n_channels": spec.n_channels,
            "reference_hash": array_hash(reference),
            "future_hash": array_hash(future),
            "mase_scale": mase_scale,
            "rmsse_scale": rmsse_scale,
            "mase_scale_id": json_hash({
                "source": spec.source, "parent": spec.parent,
                "origin": spec.origin, "period": spec.period,
                "definition": "mean_abs_seasonal_naive_on_raw_context",
                "mase_scale": mase_scale, "rmsse_scale": rmsse_scale,
            }),
            "period": spec.period,
            "candidates": candidates,
        })

    out_dir = OUT / "inputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    npz_path = out_dir / f"{block}.npz"
    with npz_path.open("wb") as handle:
        np.savez(handle, **arrays)

    manifest = {
        "stage": "v44-replay-prepare-A",
        "block": block,
        "episodes": len(rows),
        "skipped": skipped,
        "arrays": len(arrays),
        "per_source": dict(sorted(Counter(r["source"] for r in rows).items())),
        "per_pattern": dict(sorted(Counter(r["pattern"] for r in rows).items())),
        "per_severity": {str(k): v for k, v in sorted(
            Counter(r["severity"] for r in rows).items())},
        "per_horizon": dict(sorted(Counter(r["horizon"] for r in rows).items())),
        "cpu_action_support": {
            name: sum(1 for r in rows if r["candidates"][name]["applicable"])
            for name in CPU_ACTIONS},
        "cpu_action_unsupported": {
            name: dict(sorted(Counter(
                r["candidates"][name]["reason"] for r in rows
                if not r["candidates"][name]["applicable"]).items()))
            for name in CPU_ACTIONS},
        "inputs_npz": str(npz_path.relative_to(ROOT)),
        "inputs_sha256": sha(npz_path),
        "rows": rows,
        "runtime_seconds": time.perf_counter() - began,
        "source_hashes": {
            "src/introact_ts/v44/masking.py": sha(root / "src/introact_ts/v44/masking.py"),
            "src/introact_ts/v44/actions.py": sha(root / "src/introact_ts/v44/actions.py"),
            "src/introact_ts/v44/pipeline.py": sha(root / "src/introact_ts/v44/pipeline.py"),
            "src/introact_ts/v44/splits.py": sha(root / "src/introact_ts/v44/splits.py"),
            "scripts/v44_replay_prepare.py": sha(Path(__file__)),
        },
        "heldout_labels_read": 0,
        "calibration_test_touched": False,
    }
    write(out_dir / f"{block}.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--block", default="replay_fit", choices=list(P.SPLIT_NAMES))
    args = parser.parse_args()
    manifest = build_block(Path(args.root), args.block)
    print(json.dumps({k: v for k, v in manifest.items() if k != "rows"},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
