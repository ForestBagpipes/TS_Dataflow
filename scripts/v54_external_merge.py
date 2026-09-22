#!/usr/bin/env python3
"""Merge and validate the v54 external-imputer shards of one method.

Shards are ``results/v54/replay/external/<method>/<block>__<tag>.npz`` written
by scripts/v54_external_imputers_par.py, one shard per (source, mode).  The
merge joins them into ``<block>.npz`` under keys ``<episode>|<METHOD>`` with
the same contract as scripts/v47_saits_merge.py -- a union that refuses
duplicate keys -- and then validates the merged archive end to end:

* episode coverage equals the frozen block sizes
  (bankx 5352, train_eval 424, the five evaluation blocks 760 each);
* at every observed position the repair matches the observed target in
  ``results/v47/replay/inputs/<block>.npz`` (``<episode>|reference``) up to
  float32 rounding (rtol=1e-5, atol=1e-4) -- the frozen SAITS archive, built
  through the same float32 panels, deviates from the raw inputs by at most
  2.9e-5 absolute / 5.9e-8 relative, so a bitwise check would flag the
  incumbent baseline itself;
* every hidden position is finite;
* the plausibility guard of the protocol is evaluated per episode and the
  unsupported count is reported (the repair stays in the archive, as for
  SAITS -- downstream scoring marks it unsupported).

Per-shard report/status files are aggregated into ``status.json``.
"""

from __future__ import annotations

import argparse
import collections
import json
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "results/v47/replay/inputs"

#: Frozen block sizes of the protocol (scripts/v47_prepare.py reports).
EXPECTED = {"bankx": 5352, "train_eval": 424, "test": 760, "test30": 760,
            "test50": 760, "test_m2": 760, "test_m3": 760}

BLOCKS = {"crossfit": ["bankx"],
          "full": ["train_eval", "test", "test30", "test50",
                   "test_m2", "test_m3"]}


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", required=True, choices=["BRITS", "CSDI"])
    args = parser.parse_args()

    from introact_ts.v44 import actions as A

    method = args.method
    out = ROOT / f"results/v54/replay/external/{method.lower()}"
    began = time.perf_counter()

    blocks = sorted({p.name.split("__")[0] for p in out.glob("*__*.npz")
                     if "__smoke" not in p.name})
    report: dict[str, dict] = {}
    totals = collections.Counter()
    for block in blocks:
        shards = sorted(p for p in out.glob(f"{block}__*.npz")
                        if "__smoke" not in p.name)
        merged: dict[str, np.ndarray] = {}
        owner: dict[str, str] = {}
        for path in shards:
            with np.load(path, allow_pickle=False) as store:
                for key in store.files:
                    if key in merged:
                        raise SystemExit(
                            f"{key} written by both {owner[key]} and {path.name}")
                    merged[key] = store[key]
                    owner[key] = path.name

        entry: dict = {"shards": [p.name for p in shards],
                       "episodes": len(merged),
                       "expected_episodes": EXPECTED.get(block)}
        if not merged:
            entry["status"] = "no shards"
            report[block] = entry
            print(json.dumps({block: entry}), flush=True)
            continue

        # Validation against the frozen inputs: observed positions bitwise
        # identical, hidden positions finite, plausibility guard counted.
        inputs = np.load(INPUTS / f"{block}.npz", allow_pickle=False)
        mismatch, nonfinite, unsupported = [], [], []
        missing_input = []
        max_abs = max_rel = 0.0
        for key, repaired in merged.items():
            episode = key.rsplit("|", 1)[0]
            ikey = f"{episode}|reference"
            if ikey not in inputs.files:
                missing_input.append(episode)
                continue
            keep = inputs[ikey]
            observed = np.isfinite(keep)
            if repaired.shape != keep.shape:
                mismatch.append(episode)
                continue
            diff = np.abs(repaired[observed] - keep[observed])
            if diff.size:
                max_abs = max(max_abs, float(diff.max()))
                max_rel = max(max_rel, float(
                    (diff / (np.abs(keep[observed]) + 1e-12)).max()))
            if not np.allclose(repaired[observed], keep[observed],
                               rtol=1e-5, atol=1e-4):
                mismatch.append(episode)
            if not np.isfinite(repaired[~observed]).all():
                nonfinite.append(episode)
            if A.implausible_reason(repaired, keep) is not None:
                unsupported.append(episode)
        entry.update({
            "status": "ok" if not (mismatch or nonfinite or missing_input)
                      else "VALIDATION FAILED",
            "coverage_match": len(merged) == EXPECTED.get(block, -1),
            "observed_mismatch": len(mismatch),
            "observed_max_abs_diff": max_abs,
            "observed_max_rel_diff": max_rel,
            "hidden_non_finite": len(nonfinite),
            "input_missing": len(missing_input),
            "unsupported": len(unsupported),
            "unsupported_examples": unsupported[:5],
            "mismatch_examples": (mismatch + missing_input)[:5],
        })
        totals["episodes"] += len(merged)
        totals["unsupported"] += len(unsupported)
        totals["observed_mismatch"] += len(mismatch)
        totals["hidden_non_finite"] += len(nonfinite)
        if entry["status"] == "ok" and entry["coverage_match"]:
            target = out / f"{block}.npz"
            with target.open("wb") as handle:
                np.savez(handle, **merged)
            entry["archive"] = str(target.name)
        else:
            entry["archive"] = None  # never publish a failed merge
        report[block] = entry
        print(json.dumps({block: entry}, default=str), flush=True)

    # Aggregate the per-shard report/status files.
    shard_reports = {}
    failures = collections.Counter()
    runtimes = {}
    for path in sorted(out.glob("report_*.json")):
        if path.stem == "merge_report":
            continue
        payload = json.loads(path.read_text())
        shard_reports[path.name] = {
            "config_sha256": payload.get("config_sha256"),
            "failures": payload.get("failures"),
            "runtime_seconds": payload.get("runtime_seconds"),
            "per_source_status": {s: d.get("status") for s, d in
                                  payload.get("per_source", {}).items()},
        }
        for reason, count in (payload.get("failures") or {}).items():
            failures[reason] += count
        runtimes[path.name] = payload.get("runtime_seconds")

    write(out / "merge_report.json", {
        "stage": "v54-external-merge",
        "method": method,
        "blocks": report,
        "totals": dict(totals),
        "shard_failures": dict(sorted(failures.items())),
        "runtime_seconds": time.perf_counter() - began,
    })
    status_path = out / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    status.update({
        "stage": "v54-external-imputers",
        "method": method,
        "merged_blocks": {b: e.get("archive") for b, e in report.items()},
        "totals": dict(totals),
        "shard_failures": dict(sorted(failures.items())),
        "shard_reports": shard_reports,
    })
    write(status_path, status)
    print(json.dumps({"totals": dict(totals),
                      "shard_failures": dict(failures)}, indent=1))


if __name__ == "__main__":
    main()
