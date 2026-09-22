#!/usr/bin/env python3
"""v54 confirmatory Stage A -- CPU preparation of the replay inputs.

A mirror of ``scripts/v47_prepare.py`` bound to the confirmatory grid
(``introact_ts.v54.confirmatory``) and writing only under
``results/v54/confirmatory/``.  Nothing here changes the main-set paths.

For every episode of a block this builds the deterministic mask, the masked
panel, the future target, the two metrics denominators, and the candidate
inputs of the three CPU actions (KEEP / FFILL / CONTEXT_RIDGE).  The mask is
overlaid on any native NaN cells (US_Term_Structure); nothing is prefilled.
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
from introact_ts.v54 import confirmatory as PL
from introact_ts.v44.hashing import array_hash, json_hash

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v54/confirmatory/replay"
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


def dump_grid(root: Path) -> dict:
    """The frozen confirmatory parent/episode manifest, before any model runs."""
    summary = PL.summary(root)
    registry = PL.source_registry(root)
    summary["registry_path"] = PL.REGISTRY_PATH
    summary["registry_sha256"] = sha(root / PL.REGISTRY_PATH)
    summary["sources"] = {
        name: {
            "path": info.path, "columns": info.columns,
            "seasonal_period": info.seasonal_period,
            "split_bounds": {k: list(v) for k, v in info.split_bounds.items()},
            "file_sha256": info.file_sha256,
        }
        for name, info in registry.items()
    }
    summary["parents"] = {
        block: [p.parent for p in PL.parents_of(root, block)]
        for block in PL.BLOCKS
    }
    write(ROOT / "results/v54/confirmatory/parent_manifest.json", summary)
    return summary


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
                                     spec.horizon, spec.pattern,
                                     protocol_seed=PL.mask_seed_of(block)),
            "missing_count": int(mask[:, 0].sum()),
            "native_missing_count": int(np.isnan(raw_context[:, 0]).sum()),
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
        "stage": "v54-confirmatory-prepare-A",
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
        "registry_sha256": sha(root / PL.REGISTRY_PATH),
        "source_hashes": {
            "src/introact_ts/v44/masking.py": sha(root / "src/introact_ts/v44/masking.py"),
            "src/introact_ts/v44/actions.py": sha(root / "src/introact_ts/v44/actions.py"),
            "src/introact_ts/v44/pipeline.py": sha(root / "src/introact_ts/v44/pipeline.py"),
            "src/introact_ts/v44/splits.py": sha(root / "src/introact_ts/v44/splits.py"),
            "src/introact_ts/v54/confirmatory.py": sha(root / "src/introact_ts/v54/confirmatory.py"),
            "scripts/v54_confirmatory_prepare.py": sha(Path(__file__)),
        },
        "heldout_labels_read": (len(rows) if block.startswith("test") else 0),
        "calibration_test_touched": block.startswith("test"),
    }
    write(out_dir / f"{block}.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--block", default="test", choices=list(PL.BLOCKS))
    parser.add_argument("--dump-grid", action="store_true",
                        help="write the frozen parent manifest and exit")
    args = parser.parse_args()
    root = Path(args.root)
    if args.dump_grid:
        summary = dump_grid(root)
        print(json.dumps(summary["purge_audit"], ensure_ascii=False, indent=1))
        return
    manifest = build_block(root, args.block)
    print(json.dumps({k: v for k, v in manifest.items() if k != "rows"},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
