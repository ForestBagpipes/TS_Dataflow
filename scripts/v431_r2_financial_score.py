#!/usr/bin/env python3
"""CPU-only first financial appendix evaluation after every forecast is frozen."""
from __future__ import annotations
import argparse
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import subprocess
import time
import zipfile
import joblib
import numpy as np

from introact_ts.v43.agent_inputs import POOL, context_scale, mask_views
from introact_ts.v43.cli import atomic_json
from introact_ts.v43.data_io import file_hash, npy_header
from introact_ts.v43.schemas import array_hash, require
from introact_ts.v43.task_labels import TaskTarget, evaluate_pair
from introact_ts.v43.worker_protocol import verify_response
from introact_ts.v431.data import dirty_features
from introact_ts.v431.acquisition import Charge, CostInvoice, AcquiredBranch
from introact_ts.v431_r2.policy import EvidenceState
from introact_ts.v431_r2.acquisition import execute_one_step, BRANCH_TOOLS
from v431_r2_financial_collect import load_episodes, read, arrays
from v431_r2_fit import grouped_summary

ROOT = Path("results/v431-r2")
BACKENDS = ("tato", "timesfm", "timesfm-history", "timesfm-tato")


def prerequisite_gate(root):
    require(read(root / "status.json")["status"] == "completed", "financial Collector incomplete")
    frozen_input = read(root / "input_status.json")
    require(file_hash(ROOT / "terminal_freeze.json") == frozen_input["terminal_freeze_sha256"], "terminal freeze changed after financial input preparation")
    frozen = read(ROOT / "models_frozen.json")
    require(file_hash(ROOT / "models.joblib") == frozen["sha256"], "frozen r2 model changed")
    require(file_hash(ROOT / "terminal_manifest.json") == frozen["terminal_manifest_sha256"], "frozen terminal manifest changed")
    require(file_hash(ROOT / "value_labels.json") == frozen["value_labels_sha256"], "frozen acquisition supervision changed")
    terminal = read(ROOT / "terminal_freeze.json")
    require(file_hash(ROOT / "terminal_models.joblib") == terminal["sha256"], "terminal model artifact changed")
    records = {}
    for backend in BACKENDS:
        path = root / backend
        status, request = read(path / "status.json"), read(path / "request.json")
        require(status["status"] == "completed", f"{backend} not completed; future reader remains sealed")
        require(file_hash(path / "predictions.npz") == status["prediction_file_sha256"], "forecast file changed")
        require(file_hash(request["inputs"]) == request["inputs_sha256"], "backbone inputs changed")
        require(file_hash(path / "request.json") == status["request_sha256"], "backbone request changed")
        records[backend] = {"request_sha256": file_hash(path / "request.json"),
                            "prediction_sha256": file_hash(path / "predictions.npz"), "status": "completed"}
    models = joblib.load(ROOT / "models.joblib")
    for family, policy in models["policies"].items():
        require(policy.frozen_hash == frozen_input["terminal_policy_hashes"][family], "financial policy identity changed")
        require(models["acquirers"][family].terminal_hash == policy.frozen_hash, "acquirer belongs to an old policy")
    return models, read(ROOT / "terminal_manifest.json"), {"models_sha256": frozen["sha256"],
        "terminal_manifest_sha256": frozen["terminal_manifest_sha256"], "backends": records,
        "collector_forecasts_sha256": file_hash(root / "forecasts.npz"),
        "collector_history_forecasts_sha256": file_hash(root / "history/forecasts.npz")}


def replay_collector(root):
    count = 0
    for path in sorted(root.glob("*.request.json")):
        request = read(path); base = path.name.removesuffix(".request.json")
        response = read(root / (base+".response.json"))
        with np.load(root / (base+".predictions.npz"), allow_pickle=False) as archive:
            points = [archive[f"row_{i}"] for i in range(len(request["rows"]))]
        verify_response(request, response, points)
        require(file_hash(response["raw_predictions"]["path"]) == response["raw_predictions"]["sha256"], "raw quantiles changed")
        with np.load(response["raw_predictions"]["path"], allow_pickle=False) as raw:
            for i, (q, r, point) in enumerate(zip(request["rows"], response["rows"], points)):
                quantile = raw[f"row_{i}"]
                require(array_hash(quantile) == r["raw_hash"] and np.isfinite(quantile).all(), "raw quantile integrity failure")
                with np.load(q["array_path"], allow_pickle=False) as payload:
                    for name, key in (("target", "input_hash"), ("raw_mask", "raw_mask_hash"),
                                      ("covariates", "covariate_hash"), ("timestamps", "timestamps_hash"),
                                      ("availability", "availability_hash")):
                        require(array_hash(payload[name]) == q[key], "collector worker input identity failure")
                    if request["model_key"] == "bolt":
                        np.testing.assert_array_equal(point, quantile[0, 4])
                    else:
                        observed = np.isfinite(payload["target"])
                        np.testing.assert_array_equal(point[observed], payload["target"][observed])
                        np.testing.assert_array_equal(point[~observed], quantile[0, 0, ~observed, 1])
                count += 1
    atomic_json(root / "collector_independent_replay.json", {"status": "passed", "raw_outputs": count,
        "future_read": False, "input_mask_time_availability_and_median_verified": True})


def replay_timesfm_without_targets(path):
    # Reprice cross-window experimental cache hits exactly as the old scorer,
    # but intentionally do not open the history source_run/targets.npz.
    sys.path.insert(0, str(Path(__file__).resolve().parent / "v431_baselines"))
    from worker import array_sha
    request, status = read(path / "request.json"), read(path / "status.json")
    rows, calls = read(path / "decisions.json"), read(path / "calls.json")
    require(len(rows) == len(request["rows"]), "TimesFM history denominator changed")
    outputs, prices = {}, {}
    for call in calls:
        if call["cache_hit"]:
            require(call["cache_key"] in outputs, "forward model-cache hit")
            continue
        raw_path = path / call["raw_file"]
        require(file_hash(raw_path) == call["raw_sha256"], "TimesFM raw file changed")
        with np.load(raw_path, allow_pickle=False) as raw:
            require(call["cache_key"] == array_sha(raw["input"])+":"+str(call["horizon"]), "TimesFM cache input mismatch")
            require(np.isfinite(raw["point"]).all() and np.isfinite(raw["quantiles"]).all(), "TimesFM raw nonfinite")
            outputs[call["cache_key"]] = raw["point"][0].copy()
        prices[call["cache_key"]] = call["seconds"]
    priced = {}
    with np.load(request["inputs"], allow_pickle=False) as inputs, np.load(path / "predictions.npz", allow_pickle=False) as predictions:
        for row in rows:
            x, prediction = inputs[row["input_key"]], predictions[row["input_key"]]
            require(array_sha(x) == row["input_sha256"] and array_sha(prediction) == row["prediction_sha256"], "TimesFM row changed")
            np.testing.assert_array_equal(prediction, outputs[array_sha(x[None, :, None])+":"+str(row["horizon"])])
            local, supplement = set(), 0.
            for call in row["model_calls"]:
                if call["cache_key"] in local:
                    continue
                local.add(call["cache_key"])
                if call["cache_hit"]:
                    supplement += prices[call["cache_key"]]
            priced[row["input_key"]] = row["wall_seconds"]+supplement+status.get("process_overhead_seconds", 0.)/len(rows)
    atomic_json(path / "independent_replay.json", {"status": "passed", "all_rows": len(rows), "raw_outputs": len(outputs),
        "source_future_targets_opened": False, "priced_forecast_seconds": priced})
    return priced


def target_events(record, selected_rows, target_channel):
    rows = list(map(int, selected_rows)); lo, hi = record["split_bounds"]["dev"]
    require(rows and rows == sorted(set(rows)) and lo <= rows[0] <= rows[-1] < hi, "future row map crosses original DEV")
    require(target_channel == 0, "financial target changed")
    require(file_hash(record["path"]) == record["file_sha256"], "source file changed before evaluator")
    with zipfile.ZipFile(record["path"]) as archive, archive.open("values.npy") as stream:
        shape, dtype = npy_header(stream); start = stream.tell(); pieces = []
        for row in rows:
            stream.seek(start+(row*shape[1]+target_channel)*dtype.itemsize)
            pieces.append(stream.read(dtype.itemsize))
    # Only target-channel element bytes become floating-point values; future
    # auxiliary values and excluded original rows are never decoded.
    result = np.frombuffer(b"".join(pieces), dtype=dtype).copy()
    require(result.shape == (len(rows),) and np.isfinite(result).all(), "complete-case future invalid")
    return result


def materialize_targets(root, meta, gate):
    if (root / "targets.npz").exists():
        previous = read(root / "target_read_ledger.json")
        require(previous["prediction_gate"] == gate and file_hash(root / "targets.npz") == previous["targets_sha256"], "earlier target freeze changed")
        if (root / "task_labels.json").exists():
            return
        with np.load(root / "targets.npz", allow_pickle=False) as saved:
            outputs = {key: saved[key].copy() for key in saved.files}
    else:
        expected = read(root / "input_status.json")["files"]["evaluator_metadata.json"]
        require(file_hash(root / "evaluator_metadata.json") == expected, "evaluator mapping changed")
        evaluator = read(root / "evaluator_metadata.json")  # First access only after prerequisite gate and raw replay.
        cache, outputs, ledger = {}, {}, []
        # Read the longest future only once for each parent, then reuse H96 prefix.
        for uid in sorted(meta, key=lambda u: -meta[u]["horizon"]):
            m, e = meta[uid], evaluator[uid]; parent = m["parent_group"]
            if parent not in cache:
                values = target_events(e["original_record"], e["raw_future_rows"], e["target_channel"])
                cache[parent] = (e["raw_future_rows"], values)
                ledger.append({"source": m["source"], "parent_group": parent, "split": "dev", "target_channel": 0,
                               "raw_rows": e["raw_future_rows"], "numeric_values_decoded": len(values), "future_auxiliary_values_decoded": 0})
            rows, values = cache[parent]
            require(e["raw_future_rows"] == rows[:m["horizon"]], "H96 not a prefix of H192 target")
            outputs[uid+"_values"] = values[:m["horizon"]].copy()
            outputs[uid+"_mask"] = np.ones(m["horizon"], dtype=bool)
        arrays(root / "targets.npz", outputs)
        atomic_json(root / "target_read_ledger.json", {"created_utc": datetime.now(timezone.utc).isoformat(),
            "prediction_gate": gate, "reads": ledger, "calibration_test_values_decoded": 0,
            "targets_sha256": file_hash(root / "targets.npz"), "mapping_sha256": expected})
    scales = read(root / "mase_scales.json"); labels = []
    with np.load(root / "forecasts.npz", allow_pickle=False) as predictions:
        for uid, m in meta.items():
            target = TaskTarget(uid, "dev", outputs[uid+"_values"], outputs[uid+"_mask"])
            for arm in POOL:
                row = evaluate_pair(target, predictions[uid+"_A0_NATIVE"], predictions[uid+"_"+arm], scale=scales[m["source"]])
                labels.append(dict(row, arm=arm, source=m["source"], parent_group=m["parent_group"], horizon=m["horizon"],
                                   condition=m["condition"], role="dev", protocol=m["protocol"]))
    atomic_json(root / "task_labels.json", labels)


def score(root):
    require(not (root / "first_dev_results.json").exists(), "first financial DEV results are immutable")
    started = time.perf_counter()
    models, manifest, gate = prerequisite_gate(root)
    episodes, meta = load_episodes(root); byuid = {e.uid: e for e in episodes}; uids = list(meta)
    replay_collector(root)
    history_prices = replay_timesfm_without_targets(root / "timesfm-history")
    materialize_targets(root, meta, gate)
    # Reuse each old baseline verifier's already accepted Chronos environment.
    # The core policy environment intentionally lacks the TATO dependency set.
    atomic_json(root / "terminal_manifest.json", manifest)
    baseline_python = read(root / "model_manifest.json")["models"]["bolt"]["environment_python"]
    baseline_scripts = Path(__file__).resolve().parent / "v431_baselines"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    for backend in ("tato", "timesfm", "timesfm-tato"):
        command = [baseline_python, str(baseline_scripts / "timesfm_tato_worker.py"), "--verify", str(root / backend)] if backend == "timesfm-tato" else [
            baseline_python, str(baseline_scripts / "verify_and_score.py"), str(root / backend)]
        with (root / f"{backend}-verify-{stamp}.log").open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    scales, direct = read(root / "mase_scales.json"), read(root / "direct_candidate_costs.json")
    evidence, toolcost = read(root / "evidence.json"), read(root / "tool_costs.json")
    owners = read(root / "history/owners.json"); h_nonforecast = read(root / "history/nonforecast_costs.json")
    X, diagnostics, complete = {}, {}, {}
    for uid in uids:
        tick = time.perf_counter(); X[uid] = dirty_features(byuid[uid], 5); diagnostics[uid] = time.perf_counter()-tick
        complete[uid] = bool(np.isfinite(byuid[uid].target).all())
    E = {"bolt": {}, "timesfm": {}}
    for family in E:
        for uid in uids:
            E[family][uid] = {"mask": np.asarray([np.nan if v is None else v for a in POOL for v in evidence[uid]["strict_mask"][a]])}
    for uid in uids:
        E["bolt"][uid]["history"] = np.asarray([np.nan if v is None else v for a in POOL for v in evidence[uid]["history_probe"][a]])
    tf_history_cost = {}
    with np.load(root / "timesfm-history/predictions.npz", allow_pickle=False) as hp, np.load(root / "history/candidates.npz", allow_pickle=False) as hc:
        for huid, owner in owners.items():
            uid, cutoff = owner["base_uid"], owner["cutoff"]
            target = byuid[uid].target[cutoff:]; valid = np.isfinite(target)
            base = float(np.mean(abs(hp[huid+"_A0_NATIVE"][valid]-target[valid])))
            E["timesfm"][uid]["history"] = np.asarray([v for a in POOL for v in
                ((base-float(np.mean(abs(hp[huid+"_"+a][valid]-target[valid]))))/context_scale(byuid[uid]), 0., float(valid.mean()))])
            unique = {}
            for arm in POOL:
                unique.setdefault(array_hash(hc[huid+"_"+arm]), history_prices[huid+"_"+arm])
            tf_history_cost[uid] = h_nonforecast[uid]+sum(unique.values())
    forecasts, losses, maes, forecast_fees = {}, {}, {}, {"bolt": read(root / "forecast_costs.json"), "timesfm": {}}
    tf_rows = read(root / "timesfm/scored_rows.json")
    for row in tf_rows:
        forecast_fees["timesfm"][row["episode_uid"]+"_"+row["arm"]] = row["total_seconds"]-direct[row["episode_uid"]][row["arm"]]
    with np.load(root / "targets.npz", allow_pickle=False) as targets:
        for family, filename in (("bolt", "forecasts.npz"), ("timesfm", "timesfm/predictions.npz")):
            with np.load(root / filename, allow_pickle=False) as data:
                forecasts[family] = {u: {a: data[u+"_"+a].copy() for a in POOL} for u in uids}
            maes[family] = {u: np.asarray([np.abs(forecasts[family][u][a]-targets[u+"_values"]).mean() for a in POOL]) for u in uids}
            losses[family] = {u: maes[family][u]/scales[meta[u]["source"]] for u in uids}
    with np.load(root / "candidates.npz", allow_pickle=False) as f:
        candidate_hashes = {u: {a: array_hash(f[u+"_"+a]) for a in POOL} for u in uids}
    rows = []
    for family, policy in models["policies"].items():
        fm, acquirer = manifest["families"][family], models["acquirers"][family]
        reference = fm["reference"]["action"]
        for uid in uids:
            def final_invoice(action, diagnostic=False):
                arm = POOL[int(action)]
                result = CostInvoice((Charge("candidate:"+uid+":"+arm, direct[uid][arm]),
                    Charge("forecast:"+family+":"+uid+":"+arm, forecast_fees[family][uid+"_"+arm])))
                if diagnostic:
                    result = result.merge(CostInvoice((Charge("dirty-diagnostic:"+uid, diagnostics[uid]),)))
                return result
            def tool_invoice(kind):
                return CostInvoice(tuple(Charge("tool:"+family+":"+uid+":"+tool,
                    toolcost[uid]["strict_mask"] if tool == "mask" else toolcost[uid]["history_probe"] if family == "bolt" else tf_history_cost[uid])
                    for tool in BRANCH_TOOLS[kind]))
            def state_at(kind):
                state = EvidenceState()
                for tool in BRANCH_TOOLS[kind]:
                    state = state.acquire(tool, E[family][uid][tool])
                return state
            def save(name, action, invoice, **extra):
                arm = POOL[int(action)]; gain = float(losses[family][uid][reference]-losses[family][uid][int(action)])
                rows.append({"family": family, "policy": name, "episode_uid": uid,
                    **{k: meta[uid][k] for k in ("source", "parent_group", "horizon", "condition", "protocol")},
                    "arm": arm, "reference_arm": POOL[reference], "mae": float(maes[family][uid][int(action)]),
                    "mase": float(losses[family][uid][int(action)]), "total_seconds": invoice.total_seconds,
                    "invoice": invoice.as_dict(), "candidate_hash": candidate_hashes[uid][arm],
                    "forecast_hash": array_hash(forecasts[family][uid][arm]), "dirty_features": X[uid].tolist(),
                    "fully_observed": complete[uid], "tool_count": 0, "budget_overrun": False,
                    "switch_gain": max(gain, 0.), "wrong_switch_loss": max(-gain, 0.), "net_gain": gain, **extra})
            for name, action in (("KEEP", 0), ("FIXED_TSICL", 2), ("FIXED_REFERENCE", reference)):
                save(name, action, final_invoice(action))
            cart, median, _ = models["legacy_carts"][family]
            tick = time.perf_counter(); z = np.r_[X[uid], E[family][uid]["mask"], E[family][uid]["history"]]
            action = int(cart.predict(np.r_[np.where(np.isfinite(z), z, median), np.isfinite(z)][None])[0])
            invoice = final_invoice(action, True).merge(tool_invoice("both"), CostInvoice((Charge("legacy-selection:"+family+":"+uid, time.perf_counter()-tick),)))
            save("EXISTING_SAME_EVIDENCE_CART", action, invoice, tool_count=2, history=["mask", "history"])
            tick = time.perf_counter(); initial = policy.choose(X[uid], EvidenceState(), fully_observed=complete[uid])
            usable_mask = len(mask_views(byuid[uid])[0]) == 3
            applicable = {"mask": usable_mask, "history": True, "both": usable_mask}
            estimates = {k: CostInvoice((Charge("estimate-complete-"+k, value),)) for k, value in fm["branch_estimates"].items()}
            planning = CostInvoice((Charge("initial-choice-and-admission:"+family+":"+uid, time.perf_counter()-tick),))
            def fetch(kind):
                state = state_at(kind)
                action = policy.choose(X[uid], state, fully_observed=complete[uid])["action"]
                # Post-evidence CPU selection occurs inside execute_one_step's
                # measured controller wall below; do not bill it twice.
                invoice = final_invoice(action, True).merge(tool_invoice(kind), planning)
                return AcquiredBranch(POOL[action], invoice, array_hash(np.r_[*(state.result(t)[1] for t in BRANCH_TOOLS[kind])]), policy.frozen_hash)
            for budget_name, budget in manifest["budgets"].items():
                fixed = fm["fixed_state"][budget_name]
                for name, mode, order in (("R2_AGENT", "learned", None),
                    ("FIXED_ACQUIRE_CART", "stop" if fixed is None else "fixed", None if fixed is None else (fixed,))):
                    tick = time.perf_counter()
                    result = execute_one_step(terminal_hash=policy.frozen_hash, visible_features=X[uid],
                        stop_arm=POOL[initial["action"]], stop_invoice=final_invoice(initial["action"], True).merge(planning),
                        branch_estimates=estimates, budget=budget, applicable=applicable, model=acquirer, fetch=fetch,
                        fully_observed=complete[uid], mode=mode, tool_order=order)
                    invoice = CostInvoice(tuple(Charge(**v) for v in result["invoice"]["charges"])).merge(
                        CostInvoice((Charge("acquisition-controller:"+family+":"+uid, time.perf_counter()-tick),)))
                    save(name+"_"+budget_name, POOL.index(result["arm"]), invoice)
                    rows[-1].update({k: v for k, v in result.items() if k not in ("arm", "invoice", "total_seconds", "budget_overrun")})
                    rows[-1]["budget_overrun"] = invoice.total_seconds > budget
    table, bysource = grouped_summary(rows)
    bycondition = {}
    for condition in ("raw", "target_block_10", "shared_block_10"):
        bycondition[condition] = grouped_summary([r for r in rows if r["condition"] == condition])[0]
    native = {name: read(root / name / "baseline_table.json") for name in ("tato", "timesfm", "timesfm-tato")}
    native_decisions = []
    for family, folder in (("bolt", "tato"), ("timesfm", "timesfm-tato")):
        reference = manifest["families"][family]["reference"]["action"]
        for value in read(root / folder / "scored_rows.json"):
            uid = value["episode_uid"]
            gain = float(losses[family][uid][reference]-value["mase"])
            native_decisions.append({"family": family, "policy": "TATO_NATIVE_8TRIALS_OBSERVED_LINEAR",
                **{k: value[k] for k in ("episode_uid", "source", "parent_group", "horizon", "condition", "mae", "mase", "total_seconds")},
                "protocol": "financial-observation-index-r1", "arm": "TATO_NATIVE_SPACE", "tool_count": 8,
                "tool_count_unit": "optimization_trials_not_agent_evidence_tools",
                "switch_gain": max(gain, 0.), "wrong_switch_loss": max(-gain, 0.), "net_gain": gain,
                "budget_overrun": value["budget_overrun"].get("high", False), "budget_overruns_by_budget": value["budget_overrun"],
                "native_observed_value_protection": False, "scope": "official native transformations, fixed 8-trial adaptation"})
    common_decisions = rows+native_decisions
    common_table, common_by_source = grouped_summary(common_decisions)
    common_by_condition = {condition: grouped_summary([r for r in common_decisions if r["condition"] == condition])[0]
                           for condition in ("raw", "target_block_10", "shared_block_10")}
    for family, policy in models["policies"].items():
        require(policy.frozen_hash == manifest["families"][family]["terminal_hash"], "policy changed while evaluating")
    require(file_hash(ROOT / "models.joblib") == gate["models_sha256"], "model file changed while evaluating")
    atomic_json(root / "financial_decisions.json", rows)
    atomic_json(root / "financial_table.json", table)
    atomic_json(root / "financial_by_source.json", bysource)
    atomic_json(root / "financial_by_condition.json", bycondition)
    atomic_json(root / "common_financial_table.json", common_table)
    atomic_json(root / "common_financial_decisions.json", common_decisions)
    atomic_json(root / "common_financial_by_source.json", common_by_source)
    atomic_json(root / "common_financial_by_condition.json", common_by_condition)
    payload = {"created_utc": datetime.now(timezone.utc).isoformat(), "status": "completed_development_appendix_not_confirmation",
        "protocol": "financial-observation-index-r1", "first_financial_appendix_results": True,
        "old_USTS_development_overlap": True, "Oil_first_appendix_results_separately_retained": True,
        "parents": 2, "episodes": 12, "table": table, "common_table_including_native_TATO": common_table,
        "by_condition": bycondition, "native_baselines": native,
        "prediction_and_policy_gate": gate, "script_sha256": file_hash(Path(__file__)),
        "evaluation_wall_seconds": time.perf_counter()-started, "calibration_test_values_decoded": 0,
        "confidence_interval": None, "uncertainty_reason": "one parent per source; no independent grouped CI estimable",
        "natural_gap_evidence": "not_established", "strict_point_in_time": False, "method_promotion": False,
        "TATO_observed_value_protection": "native transformations unrestricted; no claim of same observation-protection contract",
        "training": "no financial fit; old frozen model/reference/state/acquisition transferred unchanged"}
    with (root / "first_dev_results.json").open("x") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False); stream.write("\n")
    print(json.dumps(table, indent=2), flush=True)


def self_test():
    import tempfile
    from unittest.mock import patch
    accesses = []
    def blocked_read(path):
        accesses.append(str(path))
        require(Path(path).name == "status.json", "sealed evaluation metadata reached before completion")
        return {"status": "running"}
    with patch(__name__+".read", blocked_read):
        try:
            prerequisite_gate(Path("unready"))
        except ValueError:
            pass
        else:
            raise AssertionError("unready worker gate accepted")
    require(accesses == ["unready/status.json"], "gate attempted an unauthorized second read")
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "synthetic.npz"
        values = np.arange(30, dtype=float).reshape(10, 3)
        np.savez_compressed(path, values=values)
        record = {"path": str(path), "file_sha256": file_hash(path), "split_bounds": {"dev": [5, 9]}}
        np.testing.assert_array_equal(target_events(record, [5, 7], 0), values[[5, 7], 0])
        for rows in ([4, 5], [8, 9], [7, 5]):
            try:
                target_events(record, rows, 0)
            except ValueError:
                pass
            else:
                raise AssertionError("invalid source target range accepted")
    print("PASS unfinished worker blocks before evaluation metadata; target-only selected event decoding; original DEV boundary/order rejects")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=ROOT / "financial-observation-index-r1")
    parser.add_argument("--precheck", action="store_true", help="check completion and frozen identities only; never open evaluator/targets")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.precheck:
        _, _, gate = prerequisite_gate(args.run); print(json.dumps(gate, indent=2))
    else:
        score(args.run)
