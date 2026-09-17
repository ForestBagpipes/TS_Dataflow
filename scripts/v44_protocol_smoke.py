#!/usr/bin/env python3
"""v4.4 Step 2-4 protocol freeze.

Builds the TRAIN-only parent registry from the frozen r5 protocol, assigns the
Replay-Fit / Gate / TRAIN-Eval blocks, audits the purge, enumerates the episode
grid, and hashes every mask that the replay bank will use.

Reads no future label: the reader is exercised on the context only, and the
future returned by ``read_windows`` is discarded and counted as unread.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from introact_ts.v44 import masking as M
from introact_ts.v44 import protocol as P
from introact_ts.v44 import registry as R
from introact_ts.v44 import splits as S

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v44/protocol"


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--no-data", action="store_true",
                        help="skip the row-reader probe")
    args = parser.parse_args()

    root = Path(args.root)
    out = Path(args.out)
    if out.exists() and (out / "protocol_freeze.json").exists():
        raise SystemExit("protocol freeze already exists; preserve the first one")

    registry = R.source_registry(root)
    unsupported = sorted(R.unsupported_parents(root))
    parents = R.train_parents(root)
    assignment = S.assign_splits(parents)
    audit = S.audit_purge(parents, assignment)
    summary = S.block_summary(parents, assignment)

    grids = {}
    for block in P.SPLIT_NAMES:
        grid = S.episode_grid(parents, assignment, block=block)
        grids[block] = {
            "episodes": len(grid),
            "parents": len({e["parent"] for e in grid}),
            "sources": len({e["source"] for e in grid}),
            "per_source": dict(sorted(Counter(e["source"] for e in grid).items())),
            "per_pattern": dict(sorted(Counter(e["pattern"] for e in grid).items())),
            "per_severity": {str(k): v for k, v in sorted(
                Counter(e["severity"] for e in grid).items())},
            "per_horizon": dict(sorted(Counter(e["horizon"] for e in grid).items())),
        }

    # Every mask the replay bank will build, hashed before any model runs.
    mask_rows = []
    for block in P.SPLIT_NAMES:
        for episode in S.episode_grid(parents, assignment, block=block):
            severity = episode["severity"]
            identity = M.mask_identity(episode["source"], episode["parent"],
                                       episode["origin"], episode["horizon"],
                                       episode["pattern"], severity)
            mask_rows.append({**identity, "block": block,
                              "assigned_severity": severity,
                              "severity_source": episode["severity_source"]})
    mask_digest = hashlib.sha256(json.dumps(
        [(row["block"], row["parent"], row["horizon"], row["pattern"],
          row["assigned_severity"], row["mask_hash"]) for row in mask_rows],
        sort_keys=True).encode()).hexdigest()

    reader_probe = {"status": "skipped"}
    if not args.no_data:
        probe = {}
        unread_future = 0
        for source, info in registry.items():
            source_parents = [p for p in parents if p.source == source]
            if not source_parents:
                continue
            target = sorted(source_parents, key=lambda p: p.read_start)[0]
            for window, context, future in R.read_windows(
                    root, info, [target], horizon=P.HORIZONS[-1]):
                unread_future += int(future.size)
                probe[source] = {
                    "parent": window.parent,
                    "context_shape": list(context.shape),
                    "target_missing": int(np.isnan(context[:, 0]).sum()),
                    "future_length": int(future.size),
                    "future_labels_scored": 0,
                }
        reader_probe = {
            "status": "completed",
            "sources": probe,
            "future_values_read_but_not_scored": unread_future,
            "heldout_labels_read": 0,
        }

    payload = {
        "version": "v44-protocol-freeze-1",
        "status": "frozen_before_any_model_run",
        "context": P.CONTEXT,
        "horizons": list(P.HORIZONS),
        "patterns": list(P.PATTERNS),
        "severities": list(P.SEVERITIES),
        "main_severity": P.MAIN_SEVERITY,
        "actions": list(P.ACTIONS),
        "reference_action": P.REFERENCE_ACTION,
        "k_grid": list(P.K_GRID),
        "beta_grid": list(P.BETA_GRID),
        "protocol_seed": P.PROTOCOL_SEED,
        "split_ratios": list(P.SPLIT_RATIOS),
        "purge": P.PURGE,
        "seasonal_periods": P.SEASONAL_PERIODS,
        "train_parents_total": len(parents),
        "train_parents_per_source": R.expected_window_count(root),
        "unsupported_parents": unsupported,
        "blocks": summary,
        "grids": grids,
        "purge_audit": audit,
        "mask_records": len(mask_rows),
        "mask_digest_sha256": mask_digest,
        "mask_identity_rows": mask_rows,
        "reader_probe": reader_probe,
        "source_hashes": {
            str(root / R.PROTOCOL_PATH): sha(root / R.PROTOCOL_PATH),
            str(root / R.TIMESTAMP_AUDIT_PATH): sha(root / R.TIMESTAMP_AUDIT_PATH),
            "src/introact_ts/v44/protocol.py": sha(root / "src/introact_ts/v44/protocol.py"),
            "src/introact_ts/v44/masking.py": sha(root / "src/introact_ts/v44/masking.py"),
            "src/introact_ts/v44/splits.py": sha(root / "src/introact_ts/v44/splits.py"),
            "src/introact_ts/v44/registry.py": sha(root / "src/introact_ts/v44/registry.py"),
            "scripts/v44_protocol_smoke.py": sha(Path(__file__)),
        },
        "heldout_labels_read": 0,
        "calibration_test_touched": False,
    }
    write(out / "protocol_freeze.json", payload)
    print(json.dumps({
        "train_parents": len(parents),
        "unsupported": len(unsupported),
        "blocks": {k: v["parents"] for k, v in summary.items()},
        "grids": {k: v["episodes"] for k, v in grids.items()},
        "mask_records": len(mask_rows),
        "mask_digest": mask_digest,
        "reader_probe": reader_probe["status"],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
