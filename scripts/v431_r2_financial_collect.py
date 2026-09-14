#!/usr/bin/env python3
"""Queue-only collection for frozen financial contexts, with no future reader.

This CLI invokes real TS-ICL/Bolt subprocesses when root schedules it. It never
calls run_collect and never opens evaluator_metadata or future targets.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import traceback
import numpy as np
import yaml

from introact_ts.v43.agent_collect import Collector
from introact_ts.v43.agent_inputs import POOL, mask_views, context_scale
from introact_ts.v43.cli import atomic_json, code_manifest
from introact_ts.v43.data_contract import as_of
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.schemas import Episode, array_hash, require


def read(path):
    return json.loads(Path(path).read_text())


def arrays(path, values):
    with Path(path).open("xb") as stream:
        np.savez_compressed(stream, **values)


def load_episodes(root):
    meta = read(root / "episode_manifest.json")
    with np.load(root / "contexts.npz", allow_pickle=False) as archive:
        result = []
        for uid, m in meta.items():
            vals = {k: archive[uid+"_"+k] for k in ("target", "covariates", "timestamps", "availability")}
            for field, key in (("target", "target_hash"), ("covariates", "covariate_hash"),
                               ("timestamps", "timestamps_hash"), ("availability", "availability_hash")):
                require(array_hash(vals[field]) == m[key], "frozen financial context hash mismatch")
            result.append(Episode(uid, m["source"], m["panel"], m["parent_group"], "dev", 0, 0, 512,
                                  m["horizon"], **vals))
    return result, meta


def save_pools(path, pools):
    arrays(path, {uid+"_"+arm: value for uid, pool in pools.items() for arm, value in pool.items()})


def save_predictions(path, predictions):
    arrays(path, {uid+"_"+arm: value for (uid, arm), value in predictions.items()})


def prepare_followup(root):
    sys.path.insert(0, str(Path(__file__).resolve().parent / "v431_baselines"))
    import worker
    import timesfm_tato_worker
    worker.prepare(root, root / "tato", "tato")
    worker.prepare(root, root / "timesfm", "timesfm")
    worker.prepare(root / "history", root / "timesfm-history", "timesfm")
    timesfm_tato_worker.prepare(root, root / "timesfm-tato")
    atomic_json(root / "followup_requests.json", {
        "execution": "root unified GPU queue only; this preparation does not run backends",
        "requests": [str(root / name / "request.json") for name in ("tato", "timesfm", "timesfm-history", "timesfm-tato")],
        "entrypoints": {"tato": "scripts/v431_baselines/worker.py", "timesfm": "scripts/v431_baselines/worker.py",
                        "timesfm-history": "scripts/v431_baselines/worker.py",
                        "timesfm-tato": "scripts/v431_baselines/timesfm_tato_worker.py"},
        "official_space": "unchanged native eight transformations; preexisting 8-trial bridge protocol",
    })


def run(root, config_path):
    begun = time.perf_counter()
    frozen = read(root / "input_status.json")
    require(frozen["status"] == "contexts_prepared", "financial contexts not frozen")
    for filename in ("contexts.npz", "episode_manifest.json", "mase_scales.json"):
        require(file_hash(root / filename) == frozen["files"][filename], "frozen input changed")
    require(not (root / "inputs").exists(), "collection is immutable; use a separately registered retry directory")
    config = yaml.safe_load(config_path.read_text())
    code = code_manifest()
    model = read(config["models"]["manifest"])
    atomic_json(root / "code_manifest.json", code)
    atomic_json(root / "model_manifest.json", model)
    atomic_json(root / "collection_config.json", {"base_config": config, "protocol": frozen["protocol"],
        "history": "one exclusive origin r=512-H; regenerate all candidates from dirty prefix; target span H",
        "mask": "three frozen views, block length51 seed101", "entrypoint_sha256": file_hash(Path(__file__)),
        "terminal_policy_hashes": frozen["terminal_policy_hashes"], "no_evaluator_metadata_access": True})
    status = {"status": "running", "phase": "load_contexts", "pid": os.getpid(),
              "started_utc": datetime.now(timezone.utc).isoformat(), "future_labels_read": 0, "heldout_labels_read": 0}
    atomic_json(root / "status.json", status)
    try:
        tick = time.perf_counter()
        episodes, meta = load_episodes(root)
        io_seconds = time.perf_counter()-tick
        collector = Collector(config, root, code, status, model)
        byuid = {e.uid: e for e in episodes}
        status["phase"] = "base_candidates"; atomic_json(root / "status.json", status)
        pools, base_costs, base_cpu = collector.pools(episodes, "base")
        direct = {e.uid: {arm: collector.component_costs[e.uid][arm]+io_seconds/len(episodes) for arm in POOL} for e in episodes}
        for uid in base_costs:
            base_costs[uid] += io_seconds/len(episodes)
        save_pools(root / "candidates.npz", pools)
        atomic_json(root / "direct_candidate_costs.json", direct)
        atomic_json(root / "base_costs.json", base_costs)
        evidence = {e.uid: {} for e in episodes}
        tools = {e.uid: {} for e in episodes}
        views, owners, plan = [], {}, {}
        for episode in episodes:
            tick = time.perf_counter()
            planned, reason = mask_views(episode, 51, 101)
            plan[episode.uid] = {"reason": reason, "blocks": [np.flatnonzero(mask).tolist() for _, mask in planned]}
            tools[episode.uid]["strict_mask"] = time.perf_counter()-tick
            for view, mask in planned:
                views.append(view); owners[view.uid] = (episode.uid, mask)
        atomic_json(root / "mask_plan.json", plan)
        status["phase"] = "strict_mask"; atomic_json(root / "status.json", status)
        mask_pool, mask_cost, _ = collector.pools(views, "mask")
        save_pools(root / "mask_candidates.npz", mask_pool)
        arrays(root / "mask_contexts.npz", {e.uid+"_"+k: getattr(e, k) for e in views
                                           for k in ("target", "covariates", "timestamps", "availability")})
        errors = defaultdict(lambda: defaultdict(list))
        for view in views:
            owner, mask = owners[view.uid]; episode = byuid[owner]; tick = time.perf_counter()
            require(np.isfinite(episode.target[mask]).all(), "strict mask validation overlaps native missing")
            for arm in POOL:
                prediction = mask_pool[view.uid][arm][mask]
                if np.isfinite(prediction).all():
                    errors[owner][arm].append(float(np.mean(abs(prediction-episode.target[mask])))/context_scale(episode))
            tools[owner]["strict_mask"] += mask_cost[view.uid]+time.perf_counter()-tick
        for episode in episodes:
            evidence[episode.uid]["strict_mask"] = {
                arm: [float(np.mean(v)), float(np.std(v)), len(v)/3] if (v := errors[episode.uid][arm]) else [None, None, 0.]
                for arm in POOL}
        atomic_json(root / "evidence.json", evidence)
        atomic_json(root / "tool_costs.json", tools)
        history, hmeta, owners = [], {}, {}
        for episode in episodes:
            cutoff = 512-episode.horizon
            view = as_of(episode, cutoff, episode.horizon)
            history.append(view); owners[view.uid] = {"base_uid": episode.uid, "cutoff": cutoff}
            hmeta[view.uid] = {**{k: meta[episode.uid][k] for k in ("source", "panel", "parent_group", "condition", "split", "role", "protocol")},
                              "base_uid": episode.uid, "horizon": episode.horizon, "raw_start": 0, "context_end": cutoff,
                              "target_hash": array_hash(view.target), "covariate_hash": array_hash(view.covariates),
                              "timestamps_hash": array_hash(view.timestamps), "availability_hash": array_hash(view.availability),
                              "original_context_raw_rows": meta[episode.uid]["original_context_raw_rows"][:cutoff],
                              "original_context_civil_dates": meta[episode.uid]["original_context_civil_dates"][:cutoff]}
        histdir = root / "history"; histdir.mkdir(exist_ok=False)
        atomic_json(histdir / "episode_manifest.json", hmeta)
        atomic_json(histdir / "owners.json", owners)
        arrays(histdir / "contexts.npz", {e.uid+"_"+k: getattr(e, k) for e in history
                                         for k in ("target", "covariates", "timestamps", "availability")})
        status["phase"] = "aligned_history"; atomic_json(root / "status.json", status)
        hpool, hcost, hcpu = collector.pools(history, "history")
        save_pools(histdir / "candidates.npz", hpool)
        atomic_json(histdir / "base_costs.json", hcost)
        hp, hfc = collector.forecasts(history, hpool, "history")
        save_predictions(histdir / "forecasts.npz", hp)
        atomic_json(histdir / "forecast_costs.json", {uid+"_"+arm: value for (uid, arm), value in hfc.items()})
        hist_evidence, hist_nonforecast = {}, {}
        for view in history:
            owner = owners[view.uid]; uid, cutoff = owner["base_uid"], owner["cutoff"]
            episode = byuid[uid]; tick = time.perf_counter()
            target = episode.target[cutoff:cutoff+episode.horizon]; mask = np.isfinite(target)
            if mask.any():
                base = float(np.mean(abs(hp[view.uid, "A0_NATIVE"][mask]-target[mask])))
                hist_evidence[uid] = {arm: [(base-float(np.mean(abs(hp[view.uid, arm][mask]-target[mask]))))/context_scale(episode), 0., float(mask.mean())]
                                      for arm in POOL}
            else:
                hist_evidence[uid] = {arm: [None, None, 0.] for arm in POOL}
            distinct = {collector.forecast_aliases["history", view.uid, arm]: hfc[view.uid, arm] for arm in POOL}
            nonforecast = hcost[view.uid]+time.perf_counter()-tick
            hist_nonforecast[uid] = nonforecast
            tools[uid]["history_probe"] = nonforecast+sum(distinct.values())
            evidence[uid]["history_probe"] = hist_evidence[uid]
        atomic_json(histdir / "evidence.json", hist_evidence)
        atomic_json(histdir / "nonforecast_costs.json", hist_nonforecast)
        atomic_json(root / "evidence.json", evidence)
        atomic_json(root / "tool_costs.json", tools)
        status["phase"] = "final_forecasts"; atomic_json(root / "status.json", status)
        forecasts, fc = collector.forecasts(episodes, pools, "final")
        save_predictions(root / "forecasts.npz", forecasts)
        atomic_json(root / "forecast_costs.json", {uid+"_"+arm: value for (uid, arm), value in fc.items()})
        aliases = [{"phase": phase, "episode_uid": uid, "arm": arm, "alias_episode_uid": alias[0], "alias_arm": alias[1]}
                   for (phase, uid, arm), alias in collector.forecast_aliases.items()]
        atomic_json(root / "forecast_aliases.json", aliases)
        noop = []
        for episode in episodes:
            if meta[episode.uid]["condition"] != "raw":
                continue
            for arm in POOL:
                same_input = array_hash(pools[episode.uid][arm]) == array_hash(episode.target)
                same_forecast = array_hash(forecasts[episode.uid, arm]) == array_hash(forecasts[episode.uid, "A0_NATIVE"])
                require(same_input and same_forecast, "complete finite raw governance changed input or prediction")
                noop.append({"episode_uid": episode.uid, "arm": arm, "input_unchanged": same_input,
                             "forecast_equals_keep": same_forecast, "direct_seconds": direct[episode.uid][arm],
                             "forecast_seconds": fc[episode.uid, arm]})
        atomic_json(root / "complete_raw_noop.json", noop)
        atomic_json(root / "cost_scope.json", {"offline_counterfactuals": "all worker inputs, responses, invoices, aliases preserved",
                    "deployment": "acquired tool and selected candidate+forecast costs; shared forecasts deduplicated within episode",
                    "data_io_seconds": io_seconds, "mask_shared_across_backbones": True,
                    "history_nonforecast_reusable_across_backbones": str(histdir / "nonforecast_costs.json"),
                    "input_preparation_and_train_scale_seconds": frozen["preparation_wall_seconds"],
                    "history_horizon": "actual task horizon; one dirty-prefix origin; no source context before episode"})
        prepare_followup(root)
        status.update(status="completed", phase="predictions_collected_followup_requests_ready", episodes=len(episodes),
                      history_views=len(history), strict_mask_views=len(views), future_labels_read=0, heldout_labels_read=0,
                      elapsed_seconds=time.perf_counter()-begun, promotion=False)
        atomic_json(root / "status.json", status)
        print(json.dumps(status), flush=True)
    except BaseException as exc:
        status.update(status="failed", error=f"{type(exc).__name__}: {exc}", elapsed_seconds=time.perf_counter()-begun)
        atomic_json(root / "status.json", status)
        traceback.print_exc(); raise


def self_test(root):
    # CPU test on already-frozen context arrays only; no evaluator/target input.
    episodes, meta = load_episodes(root)
    require(len(episodes) == 12, "financial input geometry changed")
    for episode in episodes:
        view = as_of(episode, 512-episode.horizon, episode.horizon)
        require(len(view.target) in (320, 416), "history cutoff wrong")
        require(np.array_equal(np.isnan(view.target), np.isnan(episode.target[:len(view.target)])), "dirty history mask changed")
        require(view.availability.max() <= view.timestamps[-1], "history includes unavailable covariates")
        plans, reason = mask_views(episode, 51, 101)
        require(reason is None and len(plans) == 3, "mask views unsupported")
        for _, mask in plans:
            require(np.isfinite(episode.target[mask]).all(), "pseudo mask uses hidden original missing")
    print("PASS 12 frozen contexts; aligned H96/H192 exclusive history; dirty mask/as-of preserved; 3 legal mask views each")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=Path("results/v431-r2/financial-observation-index-r1"))
    parser.add_argument("--config", type=Path, default=Path("configs/v43/agent_minimal.yaml"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(args.run)
    else:
        run(args.run, args.config)
