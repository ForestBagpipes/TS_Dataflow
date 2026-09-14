#!/usr/bin/env python3
"""Prepare frozen financial complete-case contexts; never decode DEV future."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import time
from datetime import datetime, timezone
import numpy as np

from introact_ts.v43.data_io import file_hash, read_rows
from introact_ts.v43.p2_data import corrupt_context
from introact_ts.v43.schemas import Episode, array_hash, json_hash, require
from introact_ts.v43.task_labels import mase_scale

PROTOCOL = "financial-observation-index-r1"
DAY_NS = 86_400_000_000_000
CONDITIONS = ("raw", "target_block_10", "shared_block_10")


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def mapped_context(record, raw_rows, date_lookup, reader=read_rows):
    rows = np.asarray(raw_rows, dtype=np.int64)
    require(rows.shape == (512,) and np.all(np.diff(rows) > 0), "invalid context event mapping")
    lo, hi = record["split_bounds"]["dev"]
    require(lo <= int(rows[0]) < int(rows[-1])+1 <= hi, "context crosses original DEV")
    # Only the raw context envelope is decoded. No future selected event or
    # intervening future calendar row is included in this reader call.
    _, envelope = reader(record, int(rows[0]), int(rows[-1])+1, "dev")
    values = envelope[rows-rows[0]].copy()
    require(np.isfinite(values).all(), "selected original context is not complete")
    dates = [date_lookup[int(r)] for r in rows]
    # Civil dates carry no recovered market timezone. EOD integer encoding is
    # a benchmark convention; timestamps and availability must agree so the
    # last observation is visible at this event's decision cutoff.
    timestamps = np.asarray(dates, dtype="datetime64[ns]").astype(np.int64) + DAY_NS - 1
    availability = np.broadcast_to(timestamps[:, None], values.shape).copy()
    return values, timestamps, availability, dates


def prepare(finance, output, terminal_freeze):
    require(terminal_freeze.is_file(), "terminal policy freeze is required before DEV context materialization")
    freeze = read_json(terminal_freeze)
    require(bool(freeze.get("terminal_hashes")), "terminal freeze has no policy identities")
    require(not (output / "contexts.npz").exists(), "immutable context artifact already exists")
    started = time.perf_counter()
    output.mkdir(parents=True, exist_ok=True)
    plan = read_json(finance / "observation-index-r1.json")
    require(plan["protocol"] == PROTOCOL, "unexpected financial input protocol")
    source_audit = {r["record"]["source"]: r for r in read_json(finance / "audit.json")["records"]}
    episodes, meta, evaluator, manifests, scales, scale_meta, ledger = [], {}, {}, [], {}, {}, []
    for source in plan["sources"]:
        name = source["source"]
        record = source_audit[name]["record"]
        require(name in ("Oil_Price", "US_Term_Structure"), "unregistered financial source")
        require(file_hash(record["path"]) == source["original_file_sha256"], "financial source file changed")
        parent = source["splits"]["dev"]["parents"][0]
        date_lookup = {}
        with Path(source_audit[name]["time_map_path"]).open(newline="") as stream:
            for r in csv.DictReader(stream):
                date_lookup[int(r["row_id"])] = r["civil_date"]
        values, times, availability, dates = mapped_context(record, parent["raw_context_rows"], date_lookup)
        ctxrows = parent["raw_context_rows"]
        ledger.append({"source": name, "split": "dev", "start": ctxrows[0], "stop": ctxrows[-1]+1,
                       "purpose": "context_only", "future_values_decoded": 0})
        train_lo, train_hi = record["split_bounds"]["train"]
        _, train = read_rows(record, train_lo, train_hi, "train")
        mask = np.isfinite(train).all(axis=1)
        event_train = train[mask, 0]
        scale = mase_scale(event_train, 5)
        require(scale is not None, "degenerate train-only financial MASE scale")
        scales[name] = scale
        scale_meta[name] = {"scale": scale, "period": 5, "period_unit": "complete_case_observation_event",
                            "train_raw_bounds": [train_lo, train_hi], "finite_event_count": int(mask.sum()),
                            "selected_train_target_hash": array_hash(event_train),
                            "raw_train_finite_rows_hash": array_hash(np.flatnonzero(mask)+train_lo),
                            "protocol_changed_from_business_grid": True}
        ledger.append({"source": name, "split": "train", "start": train_lo, "stop": train_hi,
                       "purpose": "event_lag5_MASE_scale", "future_values_decoded": 0})
        panel = f"{name}:{PROTOCOL}:dev"
        parent_group = panel + ":parent0"
        context_identity = {"protocol": PROTOCOL, "source": name, "split": "dev", "panel": panel,
                            "raw_source_sha256": record["file_sha256"], "context_raw_rows": ctxrows,
                            "values_hash": array_hash(values), "timestamps_hash": array_hash(times),
                            "availability_hash": array_hash(availability)}
        for horizon in (96, 192):
            origin_uid = json_hash(dict(context_identity, horizon=horizon, target_channel=0))
            raw = Episode(origin_uid, name, panel, parent_group, "dev", 0, 0, 512, horizon,
                          times, values[:, 0], values[:, 1:], availability)
            for condition in CONDITIONS:
                episode = corrupt_context(raw, condition, [230, 281], 101)
                # The exact same retained finite values survive every deletion.
                visible = np.isfinite(episode.target)
                require(np.array_equal(episode.target[visible], raw.target[visible]), "observed target overwritten")
                cov_visible = np.isfinite(episode.covariates)
                require(np.array_equal(episode.covariates[cov_visible], raw.covariates[cov_visible]), "observed covariate overwritten")
                episodes.append(episode)
                meta[episode.uid] = {
                    "source": name, "panel": panel, "parent_group": parent_group, "split": "dev", "role": "dev",
                    "protocol": PROTOCOL, "horizon": horizon, "horizon_unit": "recorded_observation_event",
                    "condition": condition, "target_channel": 0, "target_name": record["channels"][0],
                    "raw_start": 0, "context_end": 512, "origin_uid": origin_uid,
                    "original_context_raw_rows": ctxrows, "original_context_civil_dates": dates,
                    "original_context_read_interval": [ctxrows[0], ctxrows[-1]+1],
                    "original_source_split_bounds": record["split_bounds"],
                    "original_source_sha256": record["file_sha256"], "original_context_identity_hash": json_hash(context_identity),
                    "target_hash": array_hash(episode.target), "covariate_hash": array_hash(episode.covariates),
                    "observed_mask_hash": array_hash(episode.observed_mask), "timestamps_hash": array_hash(episode.timestamps),
                    "availability_hash": array_hash(episode.availability), "block": [230, 281], "seed": 101,
                    "timestamp_encoding": "naive_civil_date_end_of_day_ns", "strict_point_in_time": False,
                    "availability_assumption": "benchmark_end_of_day; actual publication/revision unrecovered",
                }
                future_rows = parent[f"raw_future_rows_H{horizon}"]
                require(len(future_rows) == horizon and min(future_rows) > max(ctxrows), "future/context mapping overlap")
                evaluator[episode.uid] = {
                    "source": name, "target_channel": 0, "original_record": record,
                    "original_parent_group": parent["parent_group"], "raw_future_rows": future_rows,
                    "future_civil_dates": [date_lookup[r] for r in future_rows],
                    "future_values_read": False, "mask_selection": "predeclared complete-case presence audit",
                    "online_read_prohibited": True,
                }
        manifests.append({"source": name, "panel": panel, "protocol": PROTOCOL,
                          "original_file_sha256": record["file_sha256"], "target_channel": 0,
                          "channels": record["channels"], "frequency": "recorded_observation_event",
                          "context_date_range": [dates[0], dates[-1]], "strict_point_in_time": False})
    require(len(episodes) == 12 and len({e.parent_group for e in episodes}) == 2, "financial matrix incomplete")
    with (output / "contexts.npz").open("xb") as stream:
        np.savez_compressed(stream, **{e.uid+"_"+field: getattr(e, field) for e in episodes
                                     for field in ("target", "covariates", "timestamps", "availability")})
    for name, value in (("episode_manifest", meta), ("evaluator_metadata", evaluator), ("data_manifest", manifests),
                        ("mase_scales", scales), ("mase_scale_protocol", scale_meta), ("read_ledger", ledger)):
        write_json(output / f"{name}.json", value)
    status = {"status": "contexts_prepared", "protocol": PROTOCOL, "created_utc": datetime.now(timezone.utc).isoformat(),
              "episodes": 12, "independent_source_parents": 2, "future_values_decoded": 0,
              "calibration_test_values_decoded": 0, "terminal_freeze_sha256": file_hash(terminal_freeze),
              "terminal_policy_hashes": freeze["terminal_hashes"], "selection_manifest_sha256": file_hash(finance / "observation-index-r1.json"),
              "script_sha256": file_hash(Path(__file__)), "preparation_wall_seconds": time.perf_counter()-started,
              "files": {p.name: file_hash(p) for p in sorted(output.iterdir()) if p.is_file()},
              "next": "root GPU queue generates all methods on these contexts before evaluator opens future targets"}
    write_json(output / "input_status.json", status)
    print(json.dumps({"status": status["status"], "episodes": len(episodes), "scales": scales,
                      "wall_seconds": status["preparation_wall_seconds"], "future_values_decoded": 0}, indent=2))


def self_test():
    calls = []
    rows = list(range(10, 1034, 2))
    def reader(record, start, stop, split):
        calls.append((start, stop, split))
        assert stop == 1033  # Must stop before the first future event.
        return np.arange(start, stop), np.ones((stop-start, 3))
    dates = {r: str(np.datetime64("2000-01-01")+np.timedelta64(i, "D")) for i, r in enumerate(rows)}
    values, timestamps, available, _ = mapped_context({"split_bounds": {"dev": [10, 2000]}}, rows, dates, reader)
    assert calls == [(10, 1033, "dev")] and values.shape == (512, 3)
    e = Episode("test", "financial", "events", "parent", "dev", 0, 0, 512, 96,
                timestamps, values[:, 0], values[:, 1:], available)
    corrupted = corrupt_context(e, "shared_block_10", [230, 281], 101)
    assert np.isnan(corrupted.target).sum() == 51 and np.isnan(corrupted.covariates).sum() == 102
    assert np.array_equal(corrupted.target[np.isfinite(corrupted.target)], e.target[np.isfinite(corrupted.target)])
    assert np.all(available <= timestamps[-1])
    print("PASS context-only raw envelope; event/EOD availability; exact 51-event deletion; original visible values preserved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--finance", type=Path, default=Path("results/v431-r2/finance"))
    parser.add_argument("--output", type=Path, default=Path("results/v431-r2/financial-observation-index-r1"))
    parser.add_argument("--terminal-freeze", type=Path, default=Path("results/v431-r2/terminal_freeze.json"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        prepare(args.finance, args.output, args.terminal_freeze)
