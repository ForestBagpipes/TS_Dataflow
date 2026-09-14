"""First H96/H192 development tranche: frozen candidates, then task labels."""
from collections import Counter, defaultdict
from dataclasses import replace
import json
from pathlib import Path
import time
import numpy as np
from .batch_executor import make_executor
from .candidates import prepare_model_input
from .data_io import file_hash, load_context, read_rows
from .p2_data import inventory_p2, select_dev, corrupt_context, legal_history
from .p2_candidates import ridge_candidate, residual_plan, static_residual
from .schemas import Candidate, array_hash, json_hash, require, verify_impute
from .task_labels import read_target, mase_scale, evaluate_pair

ARMS = ("A0_NATIVE", "A0_FFILL", "A2_SINGLE", "A3_COV", "A4_RIDGE_CONTEXT", "A4_RIDGE_FULL", "A5_STATIC")


def run_p2(config, out, code, atomic, status):
    from .cli import readiness
    require(readiness(config)["status"] == "completed", "required models not ready")
    gate = json.loads(Path(config["runtime"]["semantic_gate"]).read_text())
    require(gate["status"] == "completed" and gate["code_hash"] == code["hash"]
            and gate["config_hash"] == json_hash(config), "P2 CPU gate stale or failed")
    root = Path(__file__).resolve().parents[3]
    require(gate["test_hashes"] == {str(p.relative_to(root)): file_hash(p) for p in sorted((root/"tests/v43").rglob("*.py"))}, "test gate stale")
    require(config["data"]["horizons"] == [96, 192] and config["runtime"]["inference_batch_size"] == 1, "unregistered P2 model geometry")
    atomic(out/"semantic_gate.json", gate)
    settings = config["p2"]
    records = inventory_p2(config["data"]["root"], settings["sources"])
    origins = select_dev(records, horizons=config["data"]["horizons"], maximum=settings["maximum_origins_per_source"])
    model_manifest = json.loads(Path(config["models"]["manifest"]).read_text())
    for name, value in (("data_manifest", records), ("origin_manifest", origins), ("model_manifest", model_manifest)):
        atomic(out/f"{name}.json", value)
    lookup = {r["source"]: r for r in records}
    base_contexts = [(o, load_context(lookup[o["source"]], o)) for o in origins]
    contexts, meta = [], {}
    for origin, raw in base_contexts:
        for condition in settings["conditions"]:
            e = corrupt_context(raw, condition, config["data"]["pilot_block"], config["seed"])
            contexts.append(e)
            meta[e.uid] = dict(origin_uid=raw.uid, source=e.source, parent_group=e.parent_group,
                               condition=condition, horizon=e.horizon, split=e.split,
                               raw_start=e.raw_start, context_end=e.context_end,
                               target_hash=array_hash(e.target), covariate_hash=array_hash(e.covariates),
                               observed_mask_hash=array_hash(e.observed_mask), timestamps_hash=array_hash(e.timestamps))
    atomic(out/"episode_manifest.json", meta)
    atomic(out/"arm_manifest.json", dict(executed=list(ARMS), A1=dict(status="blocked_adapter", reason="historical PICS/v39D replay is tied to frozen 771-parent candidate/score records; no validated deployable adapter for these new intervals"), native_multivariate=dict(status="not_run"), incumbent="PICS_joint_relabel"))
    status.update(n_episodes=len(contexts), n_unique_parents=len({e.parent_group for e in contexts}), future_labels_read=0, heldout_labels_read=0)
    atomic(out/"status.json", status)
    call, costs = make_executor(config, out, code, atomic, status, model_manifest)
    method = config["method"]
    params = dict(min_rows=method["residual_min_fit_rows"], max_features=method["residual_max_features"], alpha=method["residual_alpha"])
    candidates, evidence, mask_plans, cpu_costs = {}, {}, {}, []
    # Each horizon is a separate identity domain, even for identical imputation inputs.
    for horizon in config["data"]["horizons"]:
        group = [e for e in contexts if e.horizon == horizon]
        plans, requests, keys = {}, [], []
        predictions = {e.uid: {} for e in group}
        for e in group:
            blocks, views, reason = residual_plan(e, settings["pseudo_block_length"], config["seed"])
            plans[e.uid] = (blocks, reason)
            mask_plans[e.uid] = dict(reason=reason, blocks=None if blocks is None else [np.flatnonzero(b).tolist() for b in blocks], masked_input_hashes=list(views))
            if np.isnan(e.target).any():
                views.setdefault(array_hash(e.target), e.target.copy())
                for key, view in views.items():
                    requests.append((replace(e, target=view), f"BASE_{key}", view))
                    keys.append((e.uid, key))
            else:
                predictions[e.uid][array_hash(e.target)] = e.target.copy()
        if requests:
            values = call("tsicl", "impute", "none", requests, f"h{horizon}-nested")
            for (masked, name, _), (uid, key), prediction in zip(requests, keys, values):
                verify_impute(masked, Candidate(uid, name, prediction))
                predictions[uid][key] = prediction
        cov_requests = [(e, "A3_COV", e.target) for e in group if np.isnan(e.target).any()]
        cov_predictions = dict(zip([e.uid for e, _, _ in cov_requests], call("tsicl", "impute", "past_only", cov_requests, f"h{horizon}-cov"))) if cov_requests else {}
        for e in group:
            started = time.perf_counter()
            single = Candidate(e.uid, "A2_SINGLE", predictions[e.uid][array_hash(e.target)])
            if np.isnan(e.target).any():
                require(e.uid in cov_predictions, "missing real covariate worker output")
                cov_target = cov_predictions[e.uid]
            else:
                cov_target = e.target
            cov = Candidate(e.uid, "A3_COV", cov_target)
            local, local_info = ridge_candidate(e, **params)
            history_x, history_z, span = legal_history(lookup[e.source], e)
            full, full_info = ridge_candidate(e, history=(history_x, history_z), **params)
            full_info.update(read_interval=span, historical_scope="same_split_before_context_plus_dirty_context")
            blocks, reason = plans[e.uid]
            residual, residual_info = static_residual(e, single, blocks, predictions[e.uid], reason, **params)
            arms = [Candidate(e.uid, "A0_NATIVE", e.target), Candidate(e.uid, "A0_FFILL", prepare_model_input(e.target, native_nan=False)), single, cov, local, full, residual]
            require(tuple(c.candidate_id for c in arms) == ARMS, "candidate registry mismatch")
            for c in arms:
                verify_impute(e, c)
            candidates[e.uid] = arms
            evidence[e.uid] = dict(A4_RIDGE_CONTEXT=local_info, A4_RIDGE_FULL=full_info, A5_STATIC=residual_info)
            cpu_costs.append(dict(episode_uid=e.uid, candidate_cpu_and_history_seconds=time.perf_counter()-started))
        atomic(out/"candidate_evidence.json", evidence)
        atomic(out/"mask_plans.json", mask_plans)
        atomic(out/"cpu_cost_ledger.json", cpu_costs)
    # Final candidates and every forecast are committed before future is decoded.
    candidate_index, arrays = [], {}
    for e in contexts:
        for c in candidates[e.uid]:
            key = f"{e.uid}_{c.candidate_id}"
            arrays[key] = c.target
            candidate_index.append(dict(episode_uid=e.uid, arm=c.candidate_id, array_key=key, hash=array_hash(c.target)))
    with (out/"candidates.npz").open("xb") as f:
        np.savez(f, **arrays)
    atomic(out/"candidate_index.json", candidate_index)
    forecasts, aliases = {}, {}
    for horizon in config["data"]["horizons"]:
        requests = []
        for e in (e for e in contexts if e.horizon == horizon):
            seen = {}
            for c in candidates[e.uid]:
                digest = array_hash(c.target)
                key = (e.uid, c.candidate_id)
                if digest not in seen:
                    seen[digest] = c.candidate_id
                    requests.append((e, c.candidate_id, c.target))
                aliases[f"{e.uid}_{c.candidate_id}"] = f"{e.uid}_{seen[digest]}"
        values = call("bolt", "forecast", "none", requests, f"h{horizon}-bolt")
        for (e, arm, _), value in zip(requests, values):
            forecasts[f"{e.uid}_{arm}"] = value
    atomic(out/"forecast_aliases.json", aliases)
    with (out/"forecasts.npz").open("xb") as f:
        np.savez(f, **forecasts)
    status.update(forecast_status="completed", unique_forecasts=len(forecasts), phase="task_labels")
    atomic(out/"status.json", status)
    # Evaluation owns both labels and the raw-train MASE scale. Candidate code has no access.
    scales = {}
    for r in records:
        lo, hi = r["split_bounds"]["train"]
        scales[r["source"]] = mase_scale(read_rows(r, lo, hi, "train")[1][:, 0], config["data"]["seasonal_periods"][r["source"]])
    atomic(out/"mase_scales.json", scales)
    labels, targets = [], {}
    for e in contexts:
        record = lookup[e.source]
        target = read_target(lambda lo, hi: read_rows(record, lo, hi, e.split)[1][:, e.target_channel], e)
        targets[f"{e.uid}_values"], targets[f"{e.uid}_mask"] = target.values, target.mask
        keep = forecasts[aliases[f"{e.uid}_A0_NATIVE"]]
        for c in candidates[e.uid]:
            pred = forecasts[aliases[f"{e.uid}_{c.candidate_id}"]]
            row = evaluate_pair(target, keep, pred, scale=scales[e.source])
            labels.append(dict(row, arm=c.candidate_id, **meta[e.uid]))
        status["future_labels_read"] += 1
    with (out/"targets.npz").open("xb") as f:
        np.savez(f, **targets)
    atomic(out/"task_labels.json", labels)
    atomic(out/"harmful_cases.json", [r for r in labels if r["task_harm"]])
    by_episode = defaultdict(list)
    for row in labels:
        by_episode[row["episode_uid"]].append(row)
    oracle = []
    for uid, rows in by_episode.items():
        require(tuple(r["arm"] for r in rows) == ARMS, "oracle missing candidate label")
        selected = min(rows, key=lambda r: r["mae"]) if rows[0]["status"] == "completed" else rows[0]
        oracle.append(dict(selected, arm="A9_ORACLE_AVAILABLE", chosen_arm=selected["arm"], scope="development_upper_bound_over_executed_arms"))
    atomic(out/"oracle_labels.json", oracle)
    groups = defaultdict(list)
    for row in labels+oracle:
        groups[(row["arm"], row["source"], row["horizon"], row["condition"])].append(row)
    metrics = []
    for (arm, source, horizon, condition), rows in groups.items():
        valid = [r for r in rows if r["status"] == "completed"]
        values = {key: (float(np.mean([r[key] for r in valid])) if valid and all(r[key] is not None for r in valid) else None) for key in ("mae", "mse", "mase", "task_gain", "task_harm")}
        metrics.append(dict(arm=arm, source=source, horizon=horizon, condition=condition, n_origins=len(rows), n_scored=len(valid), **values))
    atomic(out/"metrics_by_source.json", metrics)
    macro = {}
    for arm in (*ARMS, "A9_ORACLE_AVAILABLE"):
        rows = [r for r in metrics if r["arm"] == arm]
        require(len(rows) == len(records)*2*len(settings["conditions"]), "macro denominator mismatch")
        macro[arm] = {key: float(np.mean([r[key] for r in rows])) if all(r[key] is not None for r in rows) else None for key in ("mae", "mse", "mase", "task_gain", "task_harm")}
    atomic(out/"comparison.json", dict(scope="P2_first_development_tranche", source_macro=macro,
        confidence_interval=None, promotion=False, nonoverlapping_base_parents_by_source={r["source"]: len({e.parent_group for e in contexts if e.source == r["source"]}) for r in records},
        limitation="3 fixed conditions, seed101, target0; A1 and native multivariate pending; source support unequal; full-history intervals overlap within dev and require larger dependence blocks for inference",
        information_tracks={"target_only": ["A0_NATIVE", "A0_FFILL", "A2_SINGLE"], "historical_siblings": ["A3_COV", "A4_RIDGE_CONTEXT", "A5_STATIC"], "extra_legal_history": ["A4_RIDGE_FULL"]}))
    status.update(status="completed", phase="p2", scope="P2_first_development_tranche", n_candidate_labels=len(labels), promotion=False, incumbent="PICS_joint_relabel")
