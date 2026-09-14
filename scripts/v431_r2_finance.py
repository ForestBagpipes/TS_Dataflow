#!/usr/bin/env python3
"""Audit retained financial snapshots without decoding DEV or held-out values.

Run after source scripts/env_new_server.sh with W2_CORE_PY. Author CSVs are
downloaded separately, pinned and byte-hashed. Timestamp scans read the first
field only; numeric comparisons stop at the original 60% train boundary.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from introact_ts.v43.data_contract import split_intervals
from introact_ts.v43.data_io import file_hash, npy_header, read_rows


AUTHOR_REVISION = "683bb21b470f5a26586e1ab2295f0a2a1529ef0f"
SOURCE_COMMIT = "c11ed82c3eaf39e42e081e5995e7880a76f86cb9"
ASSETS = {
    "Crypto": {
        "sha256": "7587fb7e312656ff2f649087e55c99721fd4f45972354a05b05eeeaa581423f7",
        "author_path": "Crypto/D/cryptocurrencies_d.csv",
        "kind": "cryptocurrency_public_market_price_aggregate",
        "provider": "BitInfoCharts (TIME card update 2026-05-20; retained train values must match)",
        "primary_url": "https://bitinfocharts.com/comparison/bitcoin-price.html",
        "unit": "USD (provider price-chart title; exact daily aggregation not recovered)",
        "release": "Daily bucket timezone, aggregation and vintage availability unrecovered",
    },
    "Oil_Price": {
        "sha256": "75d64cd1cc5a3cfdd88a0ccbbcafb637904f4cf3caeb024e4fcb1bb2b96f55f8",
        "author_path": "Oil_Price/B/item0.csv",
        "kind": "energy_closing_spot_quotes",
        "provider": "EIA; petroleum source Refinitiv/LSEG per EIA definitions",
        "primary_url": "https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm",
        "unit": "Crude USD/barrel; petroleum products USD/gallon; Henry Hub USD/million Btu",
        "release": "Closing quotes become available after interval end; exact market cutoff/release/revisions unrecovered",
    },
    "US_Term_Structure": {
        "sha256": "2b0c3f743779c8a4029eafbe13f87329a012545e9d1ebdf03d1b99298cf30215",
        "author_path": "US_Term_Structure/B/item0.csv",
        "kind": "kim_wright_model_estimated_nominal_term_structure",
        "provider": "Federal Reserve Board Kim-Wright three-factor nominal term structure model",
        "primary_url": "https://www.federalreserve.gov/data/three-factor-nominal-term-structure-model.htm",
        "unit": "percentage points (official CSV header); not tradable security prices",
        "release": "Usually weekly on Tuesday through previous Friday; historical reestimation/revisions; no vintage reconstruction",
    },
}


def timestamp_fields(path: Path):
    """Never parse measurement fields during full-file calendar inspection."""
    with path.open("rb") as stream:
        header = next(csv.reader([stream.readline().decode("utf-8-sig").rstrip("\r\n")]))
        if header[0] != "timestamp":
            raise ValueError("author timestamp header mismatch")
        dates = [line.partition(b",")[0].decode("ascii").strip().strip('"') for line in stream]
    return header[1:], dates


def train_csv_values(path: Path, train_stop: int, columns: int):
    """Do not consume the first DEV line, even if it has malformed numerics."""
    if train_stop <= 0:
        raise ValueError("empty train")
    with path.open(newline="") as stream:
        stream.readline()
        rows = []
        for row in csv.reader(islice(stream, train_stop)):
            if len(row) != columns + 1:
                raise ValueError("author column count mismatch")
            rows.append([float(x) if x.strip() else np.nan for x in row[1:]])
    if len(rows) != train_stop:
        raise ValueError("truncated author train")
    # The official Arrow builder explicitly converts the matrix to float32.
    return np.asarray(rows, dtype=np.float32).astype(np.float64)


def compare_arrays(left, right):
    if left.shape != right.shape:
        raise ValueError("comparison shape mismatch")
    same = (left == right) | (np.isnan(left) & np.isnan(right))
    finite = np.isfinite(left) & np.isfinite(right)
    return {
        "shape": list(left.shape), "exact_equal_including_nan": bool(same.all()),
        "different_cells": int((~same).sum()),
        "nan_pattern_equal": bool(np.array_equal(np.isnan(left), np.isnan(right))),
        "max_abs_difference_finite": float(np.abs(left[finite] - right[finite]).max()) if finite.any() else None,
    }


def capacity(record, dates):
    result = {}
    for split in ("train", "dev"):
        lo, hi = record["split_bounds"][split]
        windows = []
        for start in range(lo, hi - 704 + 1, 704):
            windows.append({
                "parent_group": f"{record['panel']}:{start}:{start + 704}",
                "synchronization_group": f"{record['panel']}:{start}:{start + 704}:all_channels_all_horizons_variants",
                "raw_start": start, "context_end": start + 512, "read_stop_max_horizon": start + 704,
                "context_start_date": dates[start], "context_last_date": dates[start + 511],
                "forecast_first_date": dates[start + 512], "forecast_last_date_H192": dates[start + 703],
                "horizons": [96, 192], "numeric_future_decoded_by_audit": split == "train",
            })
        result[split] = {"independent_704_row_parent_capacity": len(windows), "windows": windows}
    return result


def field_metadata(name, channels):
    fields = []
    for idx, channel in enumerate(channels):
        row = {"index": idx, "name": channel, "target_in_existing_protocol": idx == 0}
        if name == "US_Term_Structure":
            maturity = int(channel.rsplit("_", 1)[1][:-1])
            prefixes = {"FwdRate_Fitted_": "THREEFF", "IF_TermPrem_": "THREEFFTP",
                        "Yield_Fitted_": "THREEFY", "TermPrem_": "THREEFYTP"}
            prefix = next(v for k, v in prefixes.items() if channel.startswith(k))
            row.update(provider_mnemonic=f"{prefix}{maturity:02d}00.B", unit="percentage_points",
                       observation_type="model_estimate", negative_values_valid_in_principle=True)
        elif name == "Oil_Price":
            unit = "USD_per_barrel" if channel.startswith("COP_") else "USD_per_gallon"
            if channel == "HenryHubNaturalGasSpotPrice":
                unit = "USD_per_million_Btu"
            row.update(unit=unit, observation_type="daily_closing_spot_quote",
                       stock_adjustment_or_futures_roll="not_applicable_spot_quote")
        else:
            row.update(unit="USD", observation_type="public_price_aggregate",
                       daily_aggregation_and_timezone="unrecovered")
        fields.append(row)
    return fields


def train_statistics(values, dates, channels):
    finite = np.isfinite(values)
    count = finite.sum(axis=1)
    all_missing = count == 0
    partial = (count > 0) & (count < values.shape[1])
    target = values[:, 0]
    adjacent = np.isfinite(target[:-1]) & np.isfinite(target[1:])
    jump_idx = np.flatnonzero(adjacent)
    if len(jump_idx):
        jump_idx = jump_idx[np.argsort(np.abs(np.diff(target)[jump_idx]))[-5:][::-1]]
    return {
        "decoded_rows": len(values), "finite_cells": int(finite.sum()),
        "all_channels_finite_rows": int((count == values.shape[1]).sum()),
        "target_finite_rows": int(finite[:, 0].sum()), "all_channels_missing_rows": int(all_missing.sum()),
        "partial_missing_rows": int(partial.sum()),
        "missing_per_field": dict(zip(channels, (~finite).sum(axis=0).astype(int).tolist())),
        "all_missing_dates": [dates[i] for i in np.flatnonzero(all_missing)],
        "missing_classification": "unclassified_provider_or_calendar_absence; not certified missing expected quotes",
        "target_zero_observations": int((np.isfinite(target) & (target == 0)).sum()),
        "largest_observed_target_changes_unchanged": [
            {"row_before": int(i), "row_after": int(i+1), "date_before": dates[i], "date_after": dates[i+1],
             "signed_change": float(target[i+1]-target[i]), "classification": "observed_change_not_error_label"}
            for i in jump_idx
        ],
    }


def compare_fed_train(path, record, dates, values):
    """Read only dates in this retained source's TRAIN from current provider CSV."""
    allowed = {date[:10]: i for i, date in enumerate(dates[:len(values)])}
    fields = field_metadata("US_Term_Structure", record["channels"])
    got = np.full_like(values, np.nan)
    found = np.zeros(len(values), dtype=bool)
    with path.open(newline="") as stream:
        for line in stream:
            if line.startswith("Date,"):
                header = next(csv.reader([line]))
                break
        else:
            raise ValueError("Fed provider field header missing")
        positions = [header.index(field["provider_mnemonic"]) for field in fields]
        for line in stream:
            date = line.partition(",")[0].strip('"\r\n')
            if date not in allowed:
                continue
            row = next(csv.reader([line]))
            vals = [float(row[j]) if row[j] not in ("", "NA", "ND", "N/A") else np.nan for j in positions]
            i = allowed[date]
            got[i] = np.asarray(vals, dtype=np.float32).astype(np.float64)
            found[i] = True
    return {"provider_snapshot_sha256": file_hash(path), "matched_train_dates": int(found.sum()),
            "numeric_rows_outside_train_decoded": 0, "comparison_on_matched_dates": compare_arrays(values[found], got[found]),
            "interpretation": "Current provider snapshot can differ by historical revision or upstream cleaning; no replacement performed"}


def audit(root, output):
    output.mkdir(parents=True, exist_ok=True)
    export = json.loads((root / "data/time_export.json").read_text())
    records, train_targets = [], {}
    for metadata in export:
        name = metadata["name"]
        if name not in ASSETS:
            continue
        source = ASSETS[name]
        author = output / f"{name}-author.csv"
        if file_hash(author) != source["sha256"]:
            raise ValueError(f"pinned author hash mismatch: {name}")
        channels, dates = timestamp_fields(author)
        path = root / f"data/time_{name}.npz"
        with zipfile.ZipFile(path) as archive, archive.open("values.npy") as stream:
            shape, dtype = npy_header(stream)
        with np.load(path, allow_pickle=False) as archive:
            if str(archive["freq"]) != metadata["freq"] or str(archive["start"]) != metadata["start"]:
                raise ValueError(f"retained scalar time metadata mismatch: {name}")
        if list(shape) != metadata["shape"] or channels != metadata["channels"]:
            raise ValueError(f"source shape or channel identity mismatch: {name}")
        expected = pd.date_range(metadata["start"], periods=shape[0], freq=metadata["freq"])
        actual = pd.DatetimeIndex(dates)
        if len(dates) != shape[0] or not expected.equals(actual) or actual.tz is not None:
            raise ValueError(f"author raw calendar mapping mismatch: {name}")
        record = {"source": name, "panel": name, "path": str(path.resolve()), "shape": list(shape),
                  "channels": channels, "dtype": dtype.str, "freq": metadata["freq"], "start": metadata["start"],
                  "file_sha256": file_hash(path), "split_bounds": split_intervals(shape[0]),
                  "time_mode": "benchmark_common_row_index", "calendar_status": "verified_author_csv_civil_date_grid_uncompacted",
                  "availability_status": "historical_release_and_vintage_unrecovered", "strict_point_in_time": False}
        stop = record["split_bounds"]["train"][1]
        _, values = read_rows(record, 0, stop, "train")
        train_targets[name] = pd.Series(values[:, 0], index=actual[:stop])
        author_train = train_csv_values(author, stop, shape[1])
        comparison = compare_arrays(values, author_train)
        map_path = output / f"{name}-time-map.csv"
        with map_path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["row_id", "civil_date", "split", "panel_synchronization_id"])
            for i, date in enumerate(dates):
                split = next(s for s, (lo, hi) in record["split_bounds"].items() if lo <= i < hi)
                writer.writerow([i, date, split, f"{name}:{i}:all_channels"])
        entry = {
            "record": record, "identity": dict(source), "fields": field_metadata(name, channels),
            "author_revision": AUTHOR_REVISION, "author_csv_sha256": file_hash(author),
            "time_map_path": str(map_path), "time_map_sha256": file_hash(map_path),
            "original_date_range": [dates[0], dates[-1]], "timezone": "naive civil date; not established UTC or market close time",
            "split_date_ranges": {s: [dates[lo], dates[hi-1]] for s, (lo, hi) in record["split_bounds"].items()},
            "author_train_comparison": comparison, "train_statistics": train_statistics(values, dates, channels),
            "parent_capacity": capacity(record, dates),
            "experiment_eligibility": "snapshot_controlled_deletion_only_pending_root_manifest" if comparison["exact_equal_including_nan"] else "blocked_author_snapshot_mismatch",
            "verified_natural_expected_observation_gap_set": [],
            "natural_gap_status": "not_established_do_not_label_holidays_or_all_native_nans_as_defects",
            "upstream_preprocessing": "TIME supplies processed CSV and documents optional rolling-IQR replacement; source-specific transformation ledger not recovered",
            "adjustment": "No local numeric mutation; upstream historical cleaning/revisions not reconstructed",
            "read_ledger": {"numeric_intervals": [{"split": "train", "start": 0, "stop": stop}],
                            "dev_numeric_rows_decoded": 0, "calibration_test_numeric_rows_decoded": 0,
                            "all_file_bytes_hashed": True, "all_timestamp_first_fields_scanned": True},
        }
        fed = output / "fed-provider.csv"
        if name == "US_Term_Structure" and fed.exists():
            entry["provider_train_verification"] = compare_fed_train(fed, record, dates, values)
        (output / f"{name}-record.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        records.append(entry)
    overlaps = []
    for i, left in enumerate(records):
        for right in records[i+1:]:
            left_name, right_name = left["record"]["source"], right["record"]["source"]
            aligned = pd.concat([train_targets[left_name], train_targets[right_name]], axis=1, join="inner")
            finite = aligned.notna().all(axis=1)
            paired = aligned.loc[finite]
            delta = aligned.diff().dropna()
            overlaps.append({
                "sources": [left_name, right_name],
                "full_snapshot_civil_overlap": [max(left["original_date_range"][0], right["original_date_range"][0]),
                                                min(left["original_date_range"][1], right["original_date_range"][1])],
                "train_intersection_dates": len(aligned), "paired_finite_train_target_dates": len(paired),
                "train_common_date_range": [str(aligned.index[0].date()), str(aligned.index[-1].date())] if len(aligned) else None,
                "train_target_level_pearson": float(paired.corr().iloc[0, 1]) if len(paired) >= 3 else None,
                "paired_adjacent_train_change_dates": len(delta),
                "train_target_change_pearson": float(delta.corr().iloc[0, 1]) if len(delta) >= 3 else None,
                "usage": "descriptive train-only dependence diagnostic; not selector features or source inclusion criteria",
            })
    result = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "protocol": "v431-r2-finance-metadata-train-audit-v1",
        "source_commit": SOURCE_COMMIT, "author_revision": AUTHOR_REVISION,
        "script_sha256": file_hash(Path(__file__)), "heldout_policy": "All DEV values additionally sealed by this audit; no calibration/test numeric decode",
        "cross_source_covariates": "disabled; synchronized as-of history not reconstructed",
        "independence": "All channels/horizons/variants share a panel parent; overlapping civil-time sources are not claimed independent",
        "pairwise_train_dependence": overlaps,
        "records": records,
    }
    (output / "audit.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({r["record"]["source"]: {"train_exact": r["author_train_comparison"]["exact_equal_including_nan"],
                      "train_finite_rows": r["train_statistics"]["all_channels_finite_rows"],
                      "train_missing_rows": r["train_statistics"]["all_channels_missing_rows"],
                      "dev_capacity": r["parent_capacity"]["dev"]["independent_704_row_parent_capacity"],
                      "eligibility": r["experiment_eligibility"]} for r in records}, indent=2))


def self_test():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "sentinel.csv"
        path.write_text("timestamp,x\n2020-01-01,1.25\n2020-01-02,\n2020-01-03,MUST_NOT_PARSE_DEV\n")
        fields, dates = timestamp_fields(path)
        assert fields == ["x"] and len(dates) == 3
        values = train_csv_values(path, 2, 1)
        assert values[0, 0] == 1.25 and np.isnan(values[1, 0])
        assert compare_arrays(values, values)["exact_equal_including_nan"]
        for split in ("calibration", "test"):
            try:
                read_rows({}, 0, 1, split)
            except (ValueError, AssertionError):
                pass
            else:
                raise AssertionError("held-out reader accepted")
        record = {"split_bounds": {"train": [0, 2]}}
        try:
            read_rows(record, 1, 3, "train")
        except (ValueError, AssertionError):
            pass
        else:
            raise AssertionError("cross-boundary reader accepted")
        presence_path = Path(temp) / "presence.csv"
        presence_path.write_text("timestamp,a,b\n2020-01-01,1.25,\n2020-01-02,-inf,8e2\n2020-01-03,MUST_NOT_PARSE_CAL,MUST_NOT_PARSE_CAL\n")
        assert presence_fields(presence_path, 2, 2).tolist() == [[True, False], [False, True]]
        npz = Path(temp) / "finite.npz"
        np.savez_compressed(npz, values=np.asarray([[1.25, np.nan], [-np.inf, 800.], [999., 999.]]))
        mask_record = {"path": str(npz), "split_bounds": {"train": [0, 1], "dev": [1, 2]}}
        assert retained_finite_bits(mask_record, 2).tolist() == [[True, False], [False, True]]
        try:
            retained_finite_bits(mask_record, 3)
        except ValueError:
            pass
        else:
            raise AssertionError("held-out finite mask inspection accepted")
    print("PASS timestamp-only scan; poisoned DEV numerics not parsed; NaN preserved; calibration/test and crossing reads rejected; presence-only CSV/IEEE agreement; held-out presence inspection rejected")


def presence_fields(path, stop, columns):
    """Inspect presence tokens only, never turn DEV decimal strings into values.

    This explicit data-availability audit is separate from the train numeric
    audit. No calibration/test field, including its missingness, is inspected.
    """
    missing_tokens = {"", "nan", "na", "n/a", "null", "none", "inf", "+inf", "-inf",
                      "infinity", "+infinity", "-infinity"}
    numeric_syntax = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
    result = []
    with path.open(newline="") as stream:
        stream.readline()
        for row in csv.reader(islice(stream, stop)):
            if len(row) != columns + 1:
                raise ValueError("presence column mismatch")
            flags = []
            for text in row[1:]:
                text = text.strip()
                if text.lower() in missing_tokens:
                    flags.append(False)
                elif numeric_syntax.fullmatch(text):
                    flags.append(True)
                else:
                    raise ValueError("unrecognized value token; do not silently classify")
            result.append(flags)
    if len(result) != stop:
        raise ValueError("presence audit truncated")
    return np.asarray(result, dtype=bool)


def retained_finite_bits(record, stop):
    """Decode only IEEE exponent bits as a presence mask, not floating values.

    Stop at DEV end; no calibration/test bytes are returned from the stream.
    This path cannot return numeric target values and never casts bits to float.
    """
    if not 0 < stop <= record["split_bounds"]["dev"][1]:
        raise ValueError("finite mask audit crosses into held-out")
    with zipfile.ZipFile(record["path"]) as archive, archive.open("values.npy") as stream:
        shape, dtype = npy_header(stream)
        if dtype.str not in ("<f8", "<f4"):
            raise ValueError("finite-bit audit requires supported little-endian IEEE float")
        payload = stream.read(stop * shape[1] * dtype.itemsize)
    uint = np.dtype("<u8" if dtype.itemsize == 8 else "<u4")
    exponent = np.uint64(0x7ff0000000000000) if dtype.itemsize == 8 else np.uint32(0x7f800000)
    bits = np.frombuffer(payload, dtype=uint).reshape(stop, shape[1])
    return (bits & exponent) != exponent


def prepare_observation_index(output):
    previous = json.loads((output / "audit.json").read_text())
    results = []
    for entry in previous["records"]:
        record = entry["record"]
        if record["source"] not in ("Oil_Price", "US_Term_Structure"):
            continue
        name = record["source"]
        author = output / f"{name}-author.csv"
        if file_hash(author) != entry["author_csv_sha256"] or file_hash(record["path"]) != record["file_sha256"]:
            raise ValueError("presence source changed after audit")
        columns, dates = timestamp_fields(author)
        stop = record["split_bounds"]["dev"][1]
        presence = presence_fields(author, stop, len(columns))
        finite = retained_finite_bits(record, stop)
        if not np.array_equal(presence, finite):
            raise ValueError("author token presence does not match retained IEEE finite mask")
        rows, split_report = [], {}
        for split in ("train", "dev"):
            lo, hi = record["split_bounds"][split]
            included = np.flatnonzero(presence[lo:hi].all(axis=1)) + lo
            excluded = np.flatnonzero(~presence[lo:hi].all(axis=1)) + lo
            parents = []
            for offset in range(0, len(included) - 704 + 1, 704):
                picked = included[offset:offset+704]
                parents.append({
                    "parent_group": f"{name}:observation-r1:{int(picked[0])}:{int(picked[-1])+1}",
                    "observation_offset_within_split": offset,
                    "raw_context_rows": picked[:512].astype(int).tolist(),
                    "raw_future_rows_H96": picked[512:608].astype(int).tolist(),
                    "raw_future_rows_H192": picked[512:704].astype(int).tolist(),
                    "raw_read_interval": [int(picked[0]), int(picked[-1])+1],
                    "context_date_range": [dates[picked[0]], dates[picked[511]]],
                    "future_date_range_H192": [dates[picked[512]], dates[picked[-1]]],
                    "synchronization": "all channels, horizons, corruptions and tools share this source parent",
                })
            for event, raw in enumerate(included):
                rows.append([split, event, int(raw), dates[raw]])
            split_report[split] = {
                "original_raw_bounds": [lo, hi], "original_raw_rows": hi-lo,
                "complete_case_observation_rows": len(included), "excluded_rows_count": len(excluded),
                "excluded_raw_rows": excluded.astype(int).tolist(),
                "excluded_reason": "one_or_more_fields_not_finite_in_author_snapshot; calendar/release cause unclassified",
                "independent_parent_capacity": len(parents), "parents": parents,
            }
        map_path = output / f"{name}-observation-index-r1.csv"
        with map_path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["split", "observation_index_within_split", "original_raw_row", "civil_date"])
            writer.writerows(rows)
        results.append({"source": name, "target_channel": 0, "target_name": columns[0],
                        "original_file_sha256": record["file_sha256"], "author_csv_sha256": entry["author_csv_sha256"],
                        "map_path": str(map_path), "map_sha256": file_hash(map_path), "splits": split_report})
    result = {
        "protocol": "financial-observation-index-r1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "availability_only_preparation_pending_root_protocol_and_candidate_freeze",
        "selection": "all fields finite in the fixed author snapshot; deterministic ascending dates",
        "target_and_units": "unchanged target_channel=0 and original units; no returns/volatility transformation",
        "horizon_semantics": "H96/H192 recorded observation events, different from prior B-grid horizons",
        "publication_semantics": "recorded civil dates, NOT proven actual publication dates or strict point-in-time availability",
        "scope": "conditional complete-case appendix; does not establish absence of natural observation gaps",
        "comparison": "all methods/backbones must rerun on same selected records; keep old row-grid tables separately",
        "missingness_audit": "TRAIN/DEV author presence tokens matched retained IEEE exponent finite bits; no DEV float-value decoding",
        "heldout_access": {"dev_numeric_values_decoded": 0, "dev_presence_mask_inspected": True,
                           "calibration_test_values_or_presence_decoded": 0},
        "script_sha256": file_hash(Path(__file__)), "sources": results,
    }
    (output / "observation-index-r1.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({r["source"]: {s: {k: v for k, v in d.items() if k in
          ("original_raw_rows", "complete_case_observation_rows", "excluded_rows_count", "independent_parent_capacity")}
          for s, d in r["splits"].items()} for r in results}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("results/v431-r2/finance"))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--prepare-observation-index", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.prepare_observation_index:
        prepare_observation_index(args.output)
    else:
        audit(args.root, args.output)
