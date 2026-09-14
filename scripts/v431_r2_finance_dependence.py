#!/usr/bin/env python3
"""Describe financial calendar overlap and TRAIN-only target-level dependence.

Only read_rows(..., split='train') decodes numeric data. DEV context/future
overlap uses the predeclared row/date mapping; no DEV outcome values are read.
Correlations are descriptive, with no IID p-value or causal/return claim.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

from introact_ts.v43.data_io import file_hash, read_rows
from introact_ts.v43.schemas import array_hash, require


SOURCES = ("Oil_Price", "US_Term_Structure")
TARGETS = {"Oil_Price": "COP_Brent-Europe", "US_Term_Structure": "FwdRate_Fitted_1Y"}


def read_json(path):
    return json.loads(Path(path).read_text())


def calendar_summary(dates):
    dates = sorted(set(dates))
    return {"date_count": len(dates), "first": dates[0] if dates else None,
            "last": dates[-1] if dates else None}


def correlation_summary(left, right, dates):
    require(len(left) == len(right) == len(dates), "paired array shape differs")
    x, y = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]
    dates = np.asarray(dates)[keep].tolist()
    supported = len(x) >= 3 and np.ptp(x) > 0 and np.ptp(y) > 0
    return {"status": "computed" if supported else "unsupported_nonfinite_or_constant",
            "finite_paired_dates": calendar_summary(dates),
            "pearson_levels": float(np.corrcoef(x, y)[0, 1]) if supported else None,
            "spearman_levels_average_ties": float(np.corrcoef(rankdata(x), rankdata(y))[0, 1]) if supported else None,
            "paired_target_hashes": [array_hash(x), array_hash(y)],
            "p_value": None, "p_value_reason": "serial dependence; no IID significance claim",
            "units_transformed": False, "returns_or_differences_computed": False}


def train_values(record, reader=read_rows):
    lo, hi = record["split_bounds"]["train"]
    require(record["channels"][0] == TARGETS[record["source"]], "target identity changed")
    _, matrix = reader(record, int(lo), int(hi), "train")
    require(matrix.shape == (hi-lo, record["shape"][1]), "train data shape mismatch")
    return np.asarray(matrix[:, 0], dtype=float), {
        "source": record["source"], "split": "train", "row_bounds_exclusive": [lo, hi],
        "decoded_train_rows": hi-lo, "decoded_train_columns": matrix.shape[1],
        "statistics_target_channel": 0, "dev_numeric_values_decoded": 0,
        "calibration_test_numeric_values_decoded": 0}


def prior_dev_overlap(finance, source_plans, calendars, hashes):
    """Intersect only row/date metadata, never old or new future measurements."""
    root = finance.parent
    paths = {
        "pilot32": Path("results/v43/20260914T125500.992800Z-pilot/origin_manifest.json"),
        "agent26": Path("results/v43/20260914T141030.324186Z-agent/episode_manifest.json"),
    }
    evaluator_path = root / "financial-observation-index-r1/evaluator_metadata.json"
    evaluator = read_json(evaluator_path)
    hashes[str(evaluator_path)] = file_hash(evaluator_path)
    old = {}
    for tag, path in paths.items():
        data = read_json(path)
        rows = list(data.values()) if isinstance(data, dict) else data
        old[tag] = [r for r in rows if r.get("source") in SOURCES and r.get("split") == "dev"]
        hashes[str(path)] = file_hash(path)
    comparisons = []
    for source in SOURCES:
        parent = source_plans[source]["splits"]["dev"]["parents"][0]
        new = {"context": set(parent["raw_context_rows"]),
               "future_H96": set(parent["raw_future_rows_H96"]),
               "future_H192": set(parent["raw_future_rows_H192"])}
        eval_rows = [r for r in evaluator.values() if r["source"] == source]
        require(bool(eval_rows), "financial evaluator metadata missing source")
        for r in eval_rows:
            h = len(r["raw_future_rows"])
            require(set(r["raw_future_rows"]) == new[f"future_H{h}"], "actual evaluator future differs from preregistered mapping")
        for tag, rows in old.items():
            selected = [r for r in rows if r["source"] == source]
            origins = {(int(r["raw_start"]), int(r["context_end"]), int(r["horizon"])) for r in selected}
            old_context, old_future = set(), set()
            for start, cutoff, horizon in origins:
                old_context.update(range(start, cutoff))
                old_future.update(range(cutoff, cutoff+horizon))
            reference = {"old_context": old_context, "old_future_labels": old_future,
                         "old_complete_read": old_context | old_future}
            cross = {}
            for nk, nv in new.items():
                cross[nk] = {}
                for ok, ov in reference.items():
                    common = sorted(nv & ov)
                    cross[nk][ok] = {"row_count": len(common),
                                     "raw_first": common[0] if common else None,
                                     "raw_last": common[-1] if common else None,
                                     "dates": calendar_summary([calendars[source][r] for r in common])}
            comparisons.append({"source": source, "previous_evaluated_collection": tag,
                                "previous_origin_intervals": [{"raw_context": [a, b], "raw_future": [b, b+h], "horizon": h}
                                                              for a, b, h in sorted(origins)],
                                "new_parent": parent["parent_group"], "intersections": cross,
                                "new_future_label_overlap_H192": bool(new["future_H192"] & old_future),
                                "numeric_values_read_for_comparison": 0})
    return {"comparisons": comparisons,
            "interpretation": "Oil 为首次本轮金融附表结果，不是此前从未访问过的独立 DEV 或确认集；旧 pilot 已用相同原始区间及部分映射后未来标签。USTS 亦保留既有 26-parent DEV 重叠。未移动边界寻找更有利窗口。",
            "new_independent_confirmation": False,
            "old_usage_basis": "既有真实已评估集合的 origin/episode manifest；本程序不读取旧 task_labels 或新 future 值"}


def run(finance):
    output = finance / "dependence.json"
    require(not output.exists(), "immutable dependence output already exists")
    plan_path = finance / "observation-index-r1.json"
    plan = read_json(plan_path)
    require(plan["protocol"] == "financial-observation-index-r1", "unregistered mapping")
    source_plans = {s["source"]: s for s in plan["sources"]}
    records, calendars, observed_rows, targets, source_info, ledger, hashes = {}, {}, {}, {}, {}, [], {}
    hashes[str(plan_path)] = file_hash(plan_path)
    for name in SOURCES:
        record_path = finance / f"{name}-record.json"
        record = read_json(record_path)
        require(record["source"] == name, "record source mismatch")
        records[name] = record
        require(file_hash(record["path"]) == record["file_sha256"], "source snapshot changed")
        require(record["file_sha256"] == source_plans[name]["original_file_sha256"], "mapping source changed")
        date_path = finance / f"{name}-time-map.csv"
        with date_path.open(newline="") as stream:
            calendar = {int(r["row_id"]): r["civil_date"] for r in csv.DictReader(stream)
                        if r["split"] in ("train", "dev")}
        require(len(set(calendar.values())) == len(calendar), "duplicated civil dates")
        calendars[name] = calendar
        mapping_path = finance / f"{name}-observation-index-r1.csv"
        require(file_hash(mapping_path) == source_plans[name]["map_sha256"], "event mapping changed")
        with mapping_path.open(newline="") as stream:
            observed_rows[name] = {int(r["original_raw_row"]) for r in csv.DictReader(stream) if r["split"] == "train"}
        target, read = train_values(record)
        ledger.append(read)
        lo, hi = record["split_bounds"]["train"]
        dates = [calendar[i] for i in range(lo, hi)]
        targets[name] = {d: float(x) for d, x in zip(dates, target)}
        source_info[name] = {"target_channel": 0, "target_name": record["channels"][0],
                             "target_kind": "Brent Europe crude spot price" if name == "Oil_Price" else "fitted one-year nominal forward rate",
                             "target_unit": "USD/barrel" if name == "Oil_Price" else "percentage points",
                             "original_snapshot_sha256": record["file_sha256"],
                             "train_dates": calendar_summary(dates),
                             "train_finite_target_dates": calendar_summary([d for d, x in zip(dates, target) if np.isfinite(x)]),
                             "train_target_hash": array_hash(target),
                             "strict_point_in_time": False,
                             "availability_limit": "recorded civil dates; historical publication times and vintages unrecovered"}
        for path in (record_path, date_path, mapping_path):
            hashes[str(path)] = file_hash(path)

    left, right = SOURCES
    common = sorted(set(targets[left]) & set(targets[right]))
    paired = correlation_summary([targets[left][d] for d in common], [targets[right][d] for d in common], common)
    complete_dates = {s: {calendars[s][r] for r in observed_rows[s]} for s in SOURCES}
    complete_common = sorted(complete_dates[left] & complete_dates[right])
    complete_paired = correlation_summary([targets[left][d] for d in complete_common],
                                          [targets[right][d] for d in complete_common], complete_common)

    parents, parent_sets = [], {}
    for name in SOURCES:
        for parent in source_plans[name]["splits"]["dev"]["parents"]:
            group = parent["parent_group"]
            lo, hi = records[name]["split_bounds"]["dev"]
            sets = {}
            for field, key in (("context", "raw_context_rows"), ("future_H96", "raw_future_rows_H96"),
                               ("future_H192", "raw_future_rows_H192")):
                rows = parent[key]
                require(all(lo <= r < hi for r in rows), "DEV metadata crosses split")
                sets[field] = {calendars[name][r] for r in rows}
            require(not (sets["context"] & sets["future_H192"]), "context/future overlap within parent")
            require(sets["future_H96"] <= sets["future_H192"], "horizon parent mismatch")
            parent_sets[group] = sets
            parents.append({"source": name, "parent_group": group,
                            "dates": {k: calendar_summary(v) for k, v in sets.items()},
                            "within_parent_H96_H192_future_common_dates": len(sets["future_H96"]),
                            "future_values_read": False})
    pair_rows = []
    for i, p in enumerate(parents):
        for q in parents[i+1:]:
            ps, qs = parent_sets[p["parent_group"]], parent_sets[q["parent_group"]]
            pair_rows.append({"left_parent": p["parent_group"], "right_parent": q["parent_group"],
                              "all_context_future_common_dates": calendar_summary(set.union(*ps.values()) & set.union(*qs.values())),
                              "region_intersections": {a+"__"+b: calendar_summary(ps[a] & qs[b]) for a in ps for b in qs}})
    require(len(parents) == 2, "financial parent manifest changed; reassess support description")
    old_overlap = prior_dev_overlap(finance, source_plans, calendars, hashes)
    report = {
        "status": "completed", "created_utc": datetime.now(timezone.utc).isoformat(),
        "script_sha256": file_hash(__file__), "source_order": list(SOURCES),
        "sources": source_info, "original_train_calendar_overlap": calendar_summary(common),
        "train_target_finite_date_aligned_levels": paired,
        "train_complete_case_event_subset_levels": complete_paired,
        "dev_parent_metadata": parents, "dev_parent_date_overlap": pair_rows,
        "previous_dev_exposure_metadata": old_overlap,
        "read_ledger": ledger, "input_metadata_sha256": hashes,
        "access_contract": {"numeric_statistics_split": "train_only", "dev_numeric_values_decoded": 0,
                            "dev_future_values_decoded": 0, "calibration_test_numeric_values_decoded": 0,
                            "full_source_file_access": "opaque bytes hashed only; numeric decoding limited to train row payloads",
                            "dev_use": "predeclared row identifiers and civil dates only"},
        "interpretation": {
            "different_targets": True,
            "financial_dependence": "训练期存在相同日期及水平相关。不同经济目标可能共同受宏观因素影响；此描述性分析不能识别共同驱动或因果关系。",
            "development_overlap": "当前两个 dev parent 日期不重叠；不能据此声称其统计独立或代表不同宏观环境的充分覆盖。",
            "independent_parent_support": 2,
            "support_limit": "仅两个开发 parent，每来源一个；两个来源不是大样本，H96/H192 与污染变体不能增加独立样本数。",
            "correlation_limit": "水平序列的自相关、趋势和窗口选择可能影响相关系数；未计算 IID p 值、交易收益或因果效应。",
            "method_use": "仅作金融附录依赖性描述，不修改冻结策略、阈值、评分或选择窗口。"}}
    with output.open("x") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "output": str(output), "train_overlap": report["original_train_calendar_overlap"],
                      "finite_levels": paired, "complete_case_levels": complete_paired,
                      "dev_parent_common_dates": pair_rows[0]["all_context_future_common_dates"],
                      "previous_dev_exposure": old_overlap,
                      "numeric_read_ledger": ledger}, ensure_ascii=False, indent=2))


def self_test():
    calls = []
    record = {"source": "Oil_Price", "channels": [TARGETS["Oil_Price"]],
              "shape": [10, 1], "split_bounds": {"train": [0, 4], "dev": [4, 8]}}
    def guarded_reader(record, lo, hi, split):
        require((lo, hi, split) == (0, 4, "train"), "non-train read attempted")
        calls.append((lo, hi, split))
        return np.arange(lo, hi), np.arange(4, dtype=float)[:, None]
    target, ledger = train_values(record, guarded_reader)
    require(calls == [(0, 4, "train")] and ledger["dev_numeric_values_decoded"] == 0, "train reader contract")
    d = correlation_summary([1, 2, np.nan, 4], [4, 3, 2, 1], ["a", "b", "c", "d"])
    require(d["finite_paired_dates"]["date_count"] == 3 and np.isclose(d["spearman_levels_average_ties"], -1), "finite alignment failed")
    require(correlation_summary([1, 1, 1], [2, 3, 4], ["a", "b", "c"])["pearson_levels"] is None, "unsupported filled with zero")
    print("PASS TRAIN read bounds, pairwise finite mask, tied-rank correlation, unsupported null")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--finance", type=Path, default=Path("results/v431-r2/finance"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    self_test() if args.self_test else run(args.finance)
