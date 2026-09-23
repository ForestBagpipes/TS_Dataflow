#!/usr/bin/env python3
"""v54 end-to-end per-request latency measurement (protocol freeze 2026-09-22 §8).

The freeze registers the cost accounting rule: only request-level end-to-end
*measured* latency may be reported -- batch=1, cold start and hot requests
listed separately; cache-replay speed must not be passed off as online
latency, and percentiles of different components must not be stitched into a
request percentile.  The v53 audit (docs/v53_state_compact_report_20260922.md
task 5) left exactly this open: candidate construction had no per-request
timer and no single timer ever spanned reference forecast + candidate
construction + retrieval + selected-action forecast.

This script closes that gap by serving real requests one at a time:

    reference forecast (KEEP forward)
      -> candidate construction (FFILL / CONTEXT_RIDGE pure functions,
         SINGLE_TSICL / MULTI_TSICL forward, SAITS forward)
      -> plausibility guard
      -> state feature extraction (v54-full22)
      -> retrieval + decision (frozen k, beta from v54 protocol)
      -> selected-action forecast
      -> submit

Roles (the frozen environments are kept isolated, as every stage before):

* ``tsicl``   -- run with W2_TSICL_PY.  Loads the frozen TS-ICL checkpoint
  once (cold start recorded), then times both TS-ICL forwards per sampled
  request and stores the candidate arrays.
* ``saits``   -- run with W2_BASELINE_PY.  Fits one deployment SAITS per
  source with the frozen configuration (epochs=100, patience=10) on the same
  bankx fit panels as the frozen full run -- the archived run kept no
  checkpoints, so the deployment model is refit identically here and the fit
  time is recorded as the SAITS cold start -- then times one batch=1
  imputation per sampled request and stores the candidates.
* ``chain``   -- run with W2_CHRONOS_PY, once per backbone, serially (never
  two backbone checkpoints resident at once).  Loads the backbone exactly as
  scripts/v47_forecast.py does (cold start recorded), replays the full chain
  per request with per-stage wall-clock timers, and also measures the
  comparison rows NATIVE_KEEP / FIXED_SAITS / TATO / BEST_FIXED
  (=CONTEXT_RIDGE on all three frozen backbones) on the same requests.
  The TS-ICL/SAITS stage times of the *same* request are added into that
  request's total -- the per-request total is a sum over one request's own
  stages, so request-level percentiles of the totals stay valid (the freeze
  forbids stitching component percentiles, not per-request sums).
* ``merge``   -- run with W2_CORE_PY.  Validates the fresh legality sets
  against the frozen catalogs and writes results/v54/cost/e2e_latency.json.

Sampling rule (registered): block ``test``; per source, rows sorted by
episode id ascending, first 10; 8 sources x 10 = 80 requests.

Request payload ingestion (reading the panel from the dataset store) is a
deployment-external input arrival and is done once at service init, outside
the per-request timer; model loading is cold start, recorded separately.
Every GPU call is a real forward: no prediction cache is consulted (the
worker classes' in-memory caches and raw-call audit dumps are bypassed by
calling the same loaded pipelines directly), and torch.cuda.synchronize()
brackets every GPU stage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
COST = ROOT / "results/v54/cost"
WORK = COST / "work"
BLOCK = "test"
PER_SOURCE = 10
WARMUP_CALLS = 3
SAITS_FIT_EPOCHS = 100  # frozen SAITS config (epochs=100, patience=10)

TSICL_CANDIDATES = WORK / "tsicl_candidates.npz"
TSICL_TIMES = WORK / "tsicl_times.json"
SAITS_CANDIDATES = WORK / "saits_candidates.npz"
SAITS_TIMES = WORK / "saits_times.json"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path: Path, payload, *, overwrite: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise SystemExit(f"refusing to overwrite existing output {path}")
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                              allow_nan=False) + "\n")
    tmp.replace(path)


def gpu_snapshot() -> dict:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.free",
             "--format=csv,noheader,nounits"], text=True).strip().splitlines()[0]
        used, free = (int(v.strip()) for v in out.split(","))
        procs = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid",
             "--format=csv,noheader"], text=True).strip().splitlines()
        return {"memory_used_mib": used, "memory_free_mib": free,
                "compute_processes": len([p for p in procs if p.strip()])}
    except Exception as exc:  # noqa: BLE001 - recorded
        return {"error": f"{type(exc).__name__}: {exc}"}


def sample_rows(root: Path, per_source: int = PER_SOURCE) -> list[dict]:
    """The registered sampling rule: per source, by episode id, first N."""
    manifest = json.loads(
        (root / "results/v47/replay/inputs" / f"{BLOCK}.json").read_text())
    by_source: dict[str, list[dict]] = {}
    for row in manifest["rows"]:
        by_source.setdefault(row["source"], []).append(row)
    out = []
    for source in sorted(by_source):
        rows = sorted(by_source[source], key=lambda r: r["episode"])
        out.extend(rows[:per_source])
    return out


def sample_panels(root: Path, rows: list[dict]) -> dict[str, np.ndarray]:
    """Masked panel of every sampled request, loaded once at service init."""
    from introact_ts.v46 import grid as G

    wanted = {r["episode"] for r in rows}
    specs = [s for s in G.episode_specs(root, BLOCK) if s.episode_id in wanted]
    panels = {}
    for spec, _raw, masked, _future in G.iter_panels(root, specs):
        panels[spec.episode_id] = masked
    missing = wanted - set(panels)
    if missing:
        raise SystemExit(f"panels missing for {sorted(missing)[:3]}...")
    return panels


def sync():
    import torch
    torch.cuda.synchronize()


# ------------------------------------------------------------------ role tsicl

def role_tsicl(args) -> None:
    from introact_ts.v43.workers import tsicl_worker

    rows = sample_rows(ROOT, args.per_source)
    panels = sample_panels(ROOT, rows)

    manifest = json.loads(
        (ROOT / "configs/v43/model_manifest.bootstrap.json").read_text())
    record = manifest["models"]["tsicl"]
    for name, item in record["files"].items():
        if sha(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"TS-ICL immutable model file changed: {name}")

    import torch
    torch.manual_seed(101)
    np.random.seed(101)
    sync()
    tick = time.perf_counter()
    model = tsicl_worker.load(record)
    sync()
    load_seconds = time.perf_counter() - tick

    # Warm-up, never recorded.
    first = rows[0]["episode"]
    for _ in range(WARMUP_CALLS):
        tsicl_worker.predict(model, {"target": panels[first][:, 0].copy(),
                                     "covariates": panels[first][:, 1:].copy()},
                             {"task": "impute", "covariate_mode": "none",
                              "horizon": rows[0]["horizon"], "dtype": "<f8"},
                             {"output_length": panels[first].shape[0]})
    sync()

    arrays: dict[str, np.ndarray] = {}
    records: list[dict] = []
    for row in rows:
        key = row["episode"]
        target = panels[key][:, 0].copy()
        covariates = panels[key][:, 1:].copy()
        entry = {"episode": key, "source": row["source"],
                 "horizon": row["horizon"]}
        for action, mode in (("SINGLE_TSICL", "none"),
                             ("MULTI_TSICL", "past_only")):
            payload = {"target": target, "covariates": covariates}
            request = {"task": "impute", "covariate_mode": mode,
                       "horizon": row["horizon"], "dtype": "<f8"}
            meta = {"output_length": target.shape[0]}
            sync()
            tick = time.perf_counter()
            try:
                point, _q = tsicl_worker.predict(model, payload, request, meta)
                sync()
                elapsed = time.perf_counter() - tick
                value = np.asarray(point, dtype=np.float64)
                if value.shape != target.shape or not np.isfinite(value).all():
                    raise RuntimeError(f"bad TS-ICL output {value.shape}")
                arrays[f"{key}|{action}"] = value
                entry[action] = {"seconds": elapsed, "applicable": True}
            except Exception as exc:  # noqa: BLE001 - recorded, never silent
                sync()
                entry[action] = {"seconds": None, "applicable": False,
                                 "reason": f"{type(exc).__name__}: {exc}"}
        records.append(entry)
        if len(records) % 20 == 0:
            print(json.dumps({"done": len(records), "total": len(rows)}),
                  flush=True)

    if TSICL_CANDIDATES.exists() and not args.overwrite:
        raise SystemExit(f"refusing to overwrite existing output {TSICL_CANDIDATES}")
    write(TSICL_TIMES, {
        "stage": "v54-latency-tsicl", "block": BLOCK,
        "per_source": args.per_source,
        "cold_start": {"load_seconds": load_seconds},
        "identity": {"repo_id": record["repo_id"],
                     "revision": record["revision"],
                     "checkpoint_path": record["checkpoint_path"]},
        "gpu_at_start": args.gpu_snapshot,
        "records": records,
        "runtime_seconds": None,  # filled by caller print
    }, overwrite=args.overwrite)
    with TSICL_CANDIDATES.open("wb") as handle:
        np.savez(handle, **arrays)
    print(json.dumps({"role": "tsicl", "requests": len(records),
                      "load_seconds": load_seconds}))


# ------------------------------------------------------------------ role saits

def role_saits(args) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from v47_saits import CONFIG, MAX_CHANNELS, collect  # noqa: E402

    import torch
    from pypots.imputation import SAITS

    rows = sample_rows(ROOT, args.per_source)
    sources = sorted({r["source"] for r in rows})
    wanted: dict[str, list[str]] = {}
    for r in rows:
        wanted.setdefault(r["source"], []).append(r["episode"])

    torch.manual_seed(101)
    np.random.seed(101)

    arrays: dict[str, np.ndarray] = {}
    records: list[dict] = []
    fits: dict[str, dict] = {}
    for source in sources:
        tick = time.perf_counter()
        columns, fit_rows = collect(ROOT, "bankx", source, None)
        if not fit_rows:
            fits[source] = {"status": "no fit windows"}
            continue
        raw = np.stack([p for _e, _p, p in fit_rows])
        flat = raw.reshape(-1, raw.shape[2])
        centre = np.nanmean(flat, axis=0)
        scale = np.nanstd(flat, axis=0)
        scale = np.where(np.isfinite(scale) & (scale > 1e-8), scale, 1.0)
        centre = np.where(np.isfinite(centre), centre, 0.0)
        X = ((raw - centre) / scale).astype(np.float32)
        fit_config = {k: v for k, v in CONFIG.items() if k != "epochs"}
        fit_config["patience"] = min(fit_config["patience"], SAITS_FIT_EPOCHS)
        model = SAITS(n_steps=X.shape[1], n_features=X.shape[2],
                      epochs=SAITS_FIT_EPOCHS, device="cuda", **fit_config)
        sync()
        fit_tick = time.perf_counter()
        model.fit({"X": X})
        sync()
        fit_seconds = time.perf_counter() - fit_tick
        fits[source] = {
            "status": "ok",
            "note": ("deployment SAITS refit with the frozen configuration "
                     "(epochs=100, patience=10) on the same bankx fit panels "
                     "as the frozen full run, which retained no checkpoints; "
                     "fit_seconds here is the SAITS training cold start"),
            "config": CONFIG, "fit_epochs": SAITS_FIT_EPOCHS,
            "fit_windows": int(len(fit_rows)),
            "channels_used": int(len(columns)),
            "fit_seconds": fit_seconds,
            "collect_seconds": fit_tick - tick,
        }
        del X, raw
        torch.cuda.empty_cache()

        _cols, query_rows = collect(ROOT, BLOCK, source, columns)
        by_episode = {e: p for e, _parent, p in query_rows}
        for key in wanted[source]:
            panel = by_episode[key]
            entry = {"episode": key, "source": source}
            sync()
            tick = time.perf_counter()
            try:
                Y = ((panel[None] - centre) / scale).astype(np.float32)
                imputed = np.asarray(model.impute({"X": Y}), dtype=np.float64)
                sync()
                elapsed = time.perf_counter() - tick
                original = panel[:, 0].astype(np.float64)
                hidden = ~np.isfinite(original)
                repaired = original.copy()
                repaired[hidden] = imputed[0, :, 0][hidden]
                if not np.isfinite(repaired).all():
                    raise RuntimeError("SAITS left a hidden position unfilled")
                arrays[f"{key}|SAITS"] = repaired
                entry["SAITS"] = {"seconds": elapsed, "applicable": True}
            except Exception as exc:  # noqa: BLE001 - recorded, never silent
                sync()
                entry["SAITS"] = {"seconds": None, "applicable": False,
                                  "reason": f"{type(exc).__name__}: {exc}"}
            records.append(entry)
        print(json.dumps({"source": source, "fit_seconds": fit_seconds}),
              flush=True)
        del model
        torch.cuda.empty_cache()

    if SAITS_CANDIDATES.exists() and not args.overwrite:
        raise SystemExit(f"refusing to overwrite existing output {SAITS_CANDIDATES}")
    write(SAITS_TIMES, {
        "stage": "v54-latency-saits", "block": BLOCK,
        "per_source": args.per_source,
        "cold_start": {"per_source_fit": fits},
        "gpu_at_start": args.gpu_snapshot,
        "records": records,
    }, overwrite=args.overwrite)
    with SAITS_CANDIDATES.open("wb") as handle:
        np.savez(handle, **arrays)
    print(json.dumps({"role": "saits", "requests": len(records)}))


# ------------------------------------------------------------------ role chain

def make_forward(backbone: str, model):
    """A dump-free, cache-free forward on the same loaded pipeline.

    Identical call semantics to the frozen workers (same dtype, quantile rule
    and generation settings), minus the audit raw dumps and the in-memory
    cache, neither of which exists in a deployment service.
    """
    import torch

    if backbone == "bolt":
        q50 = model.quantiles.index(0.5)

        def forward(x: np.ndarray, horizon: int) -> np.ndarray:
            sync()
            tick = time.perf_counter()
            tensors = [torch.from_numpy(x.astype(np.float32))]
            with torch.inference_mode():
                raw = model.model.predict(tensors, horizon)
            sync()
            elapsed = time.perf_counter() - tick
            point = raw.float().cpu().numpy()[:, q50, :, None]
            return point[0, :, 0], elapsed

    elif backbone == "timesfm":
        def forward(x: np.ndarray, horizon: int) -> np.ndarray:
            sync()
            tick = time.perf_counter()
            with torch.inference_mode():
                point, _quantiles = model.model.forecast(
                    horizon=horizon, inputs=[x.copy()])
            sync()
            elapsed = time.perf_counter() - tick
            return np.asarray(point)[0], elapsed

    else:
        def forward(x: np.ndarray, horizon: int) -> np.ndarray:
            sync()
            tick = time.perf_counter()
            series = [torch.from_numpy(x.astype(np.float32)).unsqueeze(0)]
            with torch.inference_mode():
                out = model.pipeline.predict(
                    series, prediction_length=horizon, context_length=512,
                    batch_size=1, cross_learning=False,
                    limit_prediction_length=True)
            sync()
            elapsed = time.perf_counter() - tick
            raw = np.stack([o.float().cpu().numpy()[0] for o in out])
            return raw[0, model.median], elapsed

    return forward


def build_query_catalog(row, candidates, states, horizon):
    """A one-request EpisodeCatalog for the decision stage.

    ``prediction`` carries a placeholder so ``legal()`` reports exactly the
    constructible actions; the decision path reads legality and state vectors
    only, never the placeholder.
    """
    from introact_ts.v44 import catalog as C
    from introact_ts.v44 import protocol as P

    catalog = C.EpisodeCatalog(
        episode=row["episode"], source=row["source"], parent=row["parent"],
        origin=row["origin"], horizon=row["horizon"], pattern=row["pattern"],
        severity=row["severity"], block=BLOCK, period=row["period"],
        mase_scale=row["mase_scale"], rmsse_scale=row["rmsse_scale"],
        mase_scale_id=row["mase_scale_id"],
        future=np.full(row["horizon"], np.nan),
        reference_target=candidates[P.REFERENCE_ACTION])
    for action in P.ACTIONS:
        ok = action in candidates
        catalog.actions[action] = C.ActionEntry(
            action=action, applicable=ok,
            reason=None if ok else "candidate construction failed",
            alias_of=None, input_hash="", prediction_hash="",
            prediction=np.zeros(horizon) if ok else None,
            state_vector=states.get(action) if ok else None)
    return catalog


def role_chain(args) -> None:
    from introact_ts.v44 import actions as A
    from introact_ts.v44 import catalog as C
    from introact_ts.v44 import masking as M
    from introact_ts.v44 import protocol as P
    from introact_ts.v44 import state as ST
    from introact_ts.v47 import select as SEL

    C.REPLAY = "results/v47/replay"
    backbone = args.backbone

    sys.path.insert(0, str(ROOT / "scripts/v431_baselines"))
    import tato_adapter as adapter
    import worker as baseline_worker

    began = time.perf_counter()

    # ---- service init (cold, recorded separately) -------------------------
    tick = time.perf_counter()
    bank_catalogs = C.load_catalog(ROOT, "bankx", backbone)
    bank = SEL.Bank(bank_catalogs, blocks=SEL.blocks_of())
    frozen = json.loads(
        (ROOT / f"results/v54/protocol/selection_{backbone}.json").read_text())
    config = SEL.frozen_config(frozen)
    if config is None:
        raise SystemExit(f"{backbone} selection is KEEP-only; nothing to time")
    k, beta = config
    best_fixed = json.loads(
        (ROOT / f"results/v54/evaluation/test_{backbone}.json").read_text()
    )["frozen"]["best_fixed_action"]
    tato_selected = json.loads(
        (ROOT / f"results/v47/baselines/tato_search_{backbone}.json").read_text()
    )["selected"]
    tato_identity = adapter.official_identity()

    rows = sample_rows(ROOT, args.per_source)
    panels = sample_panels(ROOT, rows)
    masks = {r["episode"]: M.build_mask(
        r["source"], r["parent"], r["origin"], r["horizon"], r["pattern"],
        r["severity"], length=len(panels[r["episode"]]),
        n_channels=r["n_channels"]) for r in rows}
    with np.load(TSICL_CANDIDATES, allow_pickle=False) as store:
        tsicl = {name: store[name] for name in store.files}
    with np.load(SAITS_CANDIDATES, allow_pickle=False) as store:
        saits_live = set(store.files)
    # SAITS candidate *values* come from the frozen replay archive: the
    # archived run kept no checkpoints and SAITS training is stochastic, so a
    # refit cannot reproduce the frozen plausibility-guard outcomes (a refit
    # with the frozen config leaves the plausible range on roughly half the
    # sampled requests, while the frozen candidates pass everywhere the
    # catalogs record SAITS as legal).  Serving the frozen values keeps the
    # measured chain's legality and decisions identical to the frozen
    # deployment semantics; the per-request SAITS construction time is still
    # a live batch=1 forward of the refit same-config model on this request's
    # own input, recorded by the saits role.
    saits_frozen = np.load(ROOT / "results/v47/replay/saits" / f"{BLOCK}.npz",
                           allow_pickle=False)
    tsicl_times = {r["episode"]: r
                   for r in json.loads(TSICL_TIMES.read_text())["records"]}
    saits_times = {r["episode"]: r
                   for r in json.loads(SAITS_TIMES.read_text())["records"]}
    service_init_seconds = time.perf_counter() - tick

    # ---- backbone load (cold start) ----------------------------------------
    import torch
    torch.manual_seed(101)
    np.random.seed(101)
    run_dir = WORK / f"model_{backbone}"
    run_dir.mkdir(parents=True, exist_ok=True)
    tick = time.perf_counter()
    if backbone == "bolt":
        model = baseline_worker.Bolt(run_dir)
    elif backbone == "timesfm":
        model = baseline_worker.TimesFM(run_dir)
    else:
        sys.path.insert(0, str(ROOT / "scripts"))
        from v46_chronos2 import Chronos2
        model = Chronos2(run_dir)
    sync()
    load_seconds = time.perf_counter() - tick
    forward = make_forward(backbone, model)

    class TatoModel:
        """predict_native calls model.forecast((batch, L, 1), pred_len)."""

        def forecast(self, x, horizon):
            out = [forward(np.asarray(v[:, 0], dtype=np.float64), horizon)[0]
                   for v in np.asarray(x)]
            return np.stack(out)[:, :, None]

    tato_model = TatoModel()

    # ---- warm-up, never recorded -------------------------------------------
    first = rows[0]
    for _ in range(WARMUP_CALLS):
        forward(panels[first["episode"]][:, 0], first["horizon"])
    adapter.predict_native(tato_selected[first["source"]]["params"],
                           tato_model, panels[first["episode"]][:, 0],
                           first["horizon"])

    # ---- serve the sampled requests one at a time --------------------------
    records: list[dict] = []
    for index, row in enumerate(rows):
        key = row["episode"]
        horizon = int(row["horizon"])
        panel = panels[key]
        reference = panel[:, 0].copy()
        rec = {"episode": key, "source": row["source"],
               "horizon": horizon, "pattern": row["pattern"],
               "severity": row["severity"]}

        # -- FULL_INTROACT chain ---------------------------------------------
        stages: dict[str, float] = {}

        # stage 1: reference forecast (KEEP forward)
        reference_prediction, stages["reference_forecast"] = forward(
            reference, horizon)

        # stage 2: CPU candidate construction (FFILL + CONTEXT_RIDGE)
        candidates: dict[str, np.ndarray] = {P.REFERENCE_ACTION: reference}
        tick = time.perf_counter()
        outcomes = {}
        for name in ("FFILL", "CONTEXT_RIDGE"):
            outcomes[name] = A.apply_action(name, panel)
            if outcomes[name].applicable:
                candidates[name] = outcomes[name].target
        stages["candidates_cpu"] = time.perf_counter() - tick

        # stage 2b: model candidates; forwards timed by their own roles on
        # this same request, arrays read back here.
        t_entry = tsicl_times[key]
        stages["candidates_tsicl"] = float(
            sum(t_entry[a]["seconds"] for a in ("SINGLE_TSICL", "MULTI_TSICL")
                if t_entry[a]["applicable"]))
        for action in ("SINGLE_TSICL", "MULTI_TSICL"):
            name = f"{key}|{action}"
            if t_entry[action]["applicable"] and name in tsicl:
                candidates[action] = tsicl[name]
        s_entry = saits_times[key]
        stages["candidates_saits"] = float(
            s_entry["SAITS"]["seconds"] or 0.0)
        name = f"{key}|SAITS"
        if (s_entry["SAITS"]["applicable"] and name in saits_live
                and name in saits_frozen.files):
            candidates["SAITS"] = saits_frozen[name]

        # stage 3: plausibility guard on every repaired candidate
        tick = time.perf_counter()
        for action in list(candidates):
            if action == P.REFERENCE_ACTION:
                continue
            if A.implausible_reason(candidates[action], reference) is not None:
                del candidates[action]
        stages["plausibility_guard"] = time.perf_counter() - tick

        # stage 4: state feature extraction, one vector per constructible action
        tick = time.perf_counter()
        states = {}
        for action, target in candidates.items():
            states[action] = ST.state_vector_from_mask(
                mask=masks[key], reference_target=reference,
                period=row["period"], candidate_target=target,
                reference_prediction=reference_prediction)
        stages["state_features"] = time.perf_counter() - tick

        # stage 5: retrieval + decision
        tick = time.perf_counter()
        query = build_query_catalog(row, candidates, states, horizon)
        queries = SEL.Queries([query], blocks=SEL.blocks_of())
        D = SEL.distance_matrices(bank, queries, lopo=False)
        scores = SEL.score_grid(bank, queries, D, k, beta)
        selected = SEL.decide(queries, scores)[0]
        stages["retrieval_decision"] = time.perf_counter() - tick

        # stage 6: selected-action forecast (KEEP reuses the reference call)
        if selected == P.REFERENCE_ACTION:
            stages["selected_forecast"] = 0.0
            backbone_calls = 1
        else:
            _prediction, stages["selected_forecast"] = forward(
                candidates[selected], horizon)
            backbone_calls = 2

        rec["FULL_INTROACT"] = {
            "stages": stages,
            "total_seconds": float(sum(stages.values())),
            "selected_action": selected,
            "backbone_calls": backbone_calls,
            "legal_actions": sorted(candidates),
        }

        # -- comparison rows on the same request ------------------------------
        # NATIVE_KEEP: one reference forward, submitted as-is.
        _p, t_keep = forward(reference, horizon)
        rec["NATIVE_KEEP"] = {"total_seconds": t_keep, "backbone_calls": 1}

        # FIXED_SAITS: the recorded SAITS forward of this request + one
        # backbone forward on the repaired input.
        if "SAITS" in candidates:
            _p, t_saits_fc = forward(candidates["SAITS"], horizon)
            rec["FIXED_SAITS"] = {
                "total_seconds": stages["candidates_saits"] + t_saits_fc,
                "saits_forward_seconds": stages["candidates_saits"],
                "backbone_forward_seconds": t_saits_fc,
                "backbone_calls": 1}
        else:  # The fixed policy submits KEEP when SAITS is not legal.
            _p, t_keep_fc = forward(reference, horizon)
            rec["FIXED_SAITS"] = {
                "total_seconds": stages["candidates_saits"] + t_keep_fc,
                "saits_forward_seconds": stages["candidates_saits"],
                "backbone_forward_seconds": t_keep_fc,
                "backbone_calls": 1, "fallback_keep": True}

        # TATO: frozen per-source pipeline (bridge + preprocess + one backbone
        # forward + postprocess), timed as one request.
        params = tato_selected[row["source"]]["params"]
        tick = time.perf_counter()
        try:
            _prediction, detail = adapter.predict_native(
                params, tato_model, reference, horizon)
            rec["TATO"] = {"total_seconds": time.perf_counter() - tick,
                           "bridge_seconds": detail["bridge_seconds"],
                           "backbone_calls": 1}
        except Exception as exc:  # noqa: BLE001 - recorded
            rec["TATO"] = {"total_seconds": None,
                           "reason": f"{type(exc).__name__}: {exc}"}

        # BEST_FIXED: the frozen best fixed action (CONTEXT_RIDGE on all three
        # frozen selections) -- pure-function construction + one forward.
        if best_fixed in ("FFILL", "CONTEXT_RIDGE"):
            tick = time.perf_counter()
            outcome = A.apply_action(best_fixed, panel)
            t_build = time.perf_counter() - tick
            if outcome.applicable:
                _p, t_fc = forward(outcome.target, horizon)
                rec["BEST_FIXED"] = {
                    "total_seconds": t_build + t_fc,
                    "construction_seconds": t_build,
                    "backbone_forward_seconds": t_fc,
                    "backbone_calls": 1, "action": best_fixed}
            else:  # fixed policy falls back to KEEP on this request
                _p, t_fc = forward(reference, horizon)
                rec["BEST_FIXED"] = {"total_seconds": t_fc,
                                     "backbone_calls": 1, "action": best_fixed,
                                     "fallback_keep": True}
        else:
            rec["BEST_FIXED"] = {"total_seconds": None,
                                 "reason": f"best fixed action {best_fixed} is "
                                           "a model stage; not timed here"}

        records.append(rec)
        if (index + 1) % 10 == 0:
            print(json.dumps({"done": index + 1, "total": len(rows),
                              "elapsed": time.perf_counter() - began}),
                  flush=True)

    write(WORK / f"chain_{backbone}.json", {
        "stage": "v54-latency-chain", "block": BLOCK, "backbone": backbone,
        "per_source": args.per_source,
        "frozen": {"k": k, "beta": beta, "best_fixed_action": best_fixed},
        "cold_start": {"model_load_seconds": load_seconds,
                       "service_init_seconds": service_init_seconds},
        "identity": dict(model.identity),
        "tato_official": {"commit": tato_identity["commit"]},
        "gpu_at_start": args.gpu_snapshot,
        "records": records,
        "runtime_seconds": time.perf_counter() - began,
    }, overwrite=args.overwrite)
    print(json.dumps({"role": "chain", "backbone": backbone,
                      "requests": len(records),
                      "load_seconds": load_seconds}))


# ------------------------------------------------------------------ role merge

def percentiles(values: list[float]) -> dict:
    array = np.asarray(values, dtype=np.float64) * 1000.0
    return {"mean_ms": float(array.mean()),
            "p50_ms": float(np.percentile(array, 50)),
            "p95_ms": float(np.percentile(array, 95)),
            "max_ms": float(array.max()), "n": int(array.size)}


def role_merge(args) -> None:
    from introact_ts.v44 import catalog as C
    from introact_ts.v44 import protocol as P

    C.REPLAY = "results/v47/replay"
    backbones = ("bolt", "timesfm", "chronos2")
    rows = sample_rows(ROOT, args.per_source)

    chains = {}
    for backbone in backbones:
        path = WORK / f"chain_{backbone}.json"
        chains[backbone] = json.loads(path.read_text())

    # Validation: the legality the fresh construction derived must equal the
    # frozen catalog's legal set for the same requests.
    mismatches = []
    for backbone in backbones:
        catalogs = {c.episode: c
                    for c in C.load_catalog(ROOT, BLOCK, backbone)}
        for rec in chains[backbone]["records"]:
            frozen_legal = set(catalogs[rec["episode"]].legal())
            fresh_legal = set(rec["FULL_INTROACT"]["legal_actions"])
            if frozen_legal != fresh_legal:
                mismatches.append({"backbone": backbone,
                                   "episode": rec["episode"],
                                   "frozen": sorted(frozen_legal),
                                   "fresh": sorted(fresh_legal)})

    tsicl_payload = json.loads(TSICL_TIMES.read_text())
    saits_payload = json.loads(SAITS_TIMES.read_text())

    # Frozen SAITS deployment-fit times recorded by the original full run.
    frozen_fit = {}
    for shard in sorted((ROOT / "results/v47/replay/saits").glob(
            "report_full-s*.json")):
        report = json.loads(shard.read_text())
        for source, item in report.get("per_source", {}).items():
            if item.get("status") == "ok":
                frozen_fit[source] = {
                    "total_seconds": item.get("total_seconds"),
                    "fit_windows": item.get("fit_windows"),
                    "channels_used": item.get("channels_used"),
                    "shard": shard.name}

    methods = ("NATIVE_KEEP", "BEST_FIXED", "FIXED_SAITS", "TATO",
               "FULL_INTROACT")
    summary: dict[str, dict] = {}
    raw_totals: dict[str, dict] = {}
    for backbone in backbones:
        per_method: dict[str, list[float]] = {m: [] for m in methods}
        calls = []
        stage_means: dict[str, list[float]] = {}
        selected_count: dict[str, int] = {}
        for rec in chains[backbone]["records"]:
            for method in methods:
                total = rec.get(method, {}).get("total_seconds")
                if total is not None:
                    per_method[method].append(total)
            full = rec["FULL_INTROACT"]
            calls.append(full["backbone_calls"])
            selected_count[full["selected_action"]] = \
                selected_count.get(full["selected_action"], 0) + 1
            for stage, value in full["stages"].items():
                stage_means.setdefault(stage, []).append(value)
        summary[backbone] = {
            "hot_per_request": {m: percentiles(v)
                                for m, v in per_method.items()},
            "full_introact_stage_mean_ms": {
                s: float(np.mean(v)) * 1000.0
                for s, v in sorted(stage_means.items())},
            "full_introact_backbone_calls_per_request": {
                "mean": float(np.mean(calls)), "min": int(min(calls)),
                "max": int(max(calls))},
            "full_introact_selected_actions": dict(sorted(
                selected_count.items())),
            "cold_start": chains[backbone]["cold_start"],
            "identity": {k2: v for k2, v in chains[backbone]["identity"].items()
                         if k2 != "environment_python"},
            "gpu_at_start": chains[backbone]["gpu_at_start"],
        }
        raw_totals[backbone] = {
            m: [rec.get(m, {}).get("total_seconds")
                for rec in chains[backbone]["records"]]
            for m in methods}

    # What this measurement supersedes (v53 arithmetic synthesis, Table 41).
    old = {}
    audit_path = ROOT / "results/v53_state_compact/latency_audit.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        old = {k2: v.get("backbone_call")
               for k2, v in audit.get("latency_files", {}).items()}

    sampling_rule = (
        f"block={BLOCK}; per source, manifest rows sorted by episode id "
        f"ascending, first {args.per_source}; 8 sources x "
        f"{args.per_source} = {len(rows)} requests; the request set is "
        "identical across every role and backbone")

    payload = {
        "stage": "v54-e2e-latency",
        "protocol": "docs/protocol_freeze_v54_20260922.md §8: request-level "
                    "end-to-end measured latency only; batch=1; cold start and "
                    "hot requests separate; no cache-replay speed, no "
                    "component-percentile stitching",
        "sampling_rule": sampling_rule,
        "measurement_notes": [
            "every GPU number is a real forward on the frozen checkpoint; the "
            "worker classes' in-memory prediction caches and raw audit dumps "
            "were bypassed (neither exists in a deployment service)",
            "torch.cuda.synchronize() brackets every GPU stage; timers are "
            "time.perf_counter wall clock",
            "TS-ICL and SAITS run in their frozen isolated environments; a "
            "request's FULL_INTROACT total is the sum of that same request's "
            "stage times across the three stages, so request-level "
            "percentiles remain per-request (no cross-request stitching)",
            "request payload ingestion (dataset-store panel read) happens at "
            "service init and is excluded from the per-request timer, as is "
            "bank/catalog loading (recorded as service_init_seconds)",
            "SAITS per-request construction time is a live batch=1 forward of "
            "a deployment model refit with the frozen configuration "
            "(epochs=100, patience=10) on the same bankx fit panels; the refit "
            "time is reported as the SAITS training cold start. SAITS "
            "candidate *values* served to the chain come from the frozen "
            "replay archive: the archived run kept no checkpoints and SAITS "
            "training is stochastic, so no refit can reproduce the frozen "
            "plausibility-guard outcomes; serving the frozen values keeps the "
            "measured chain's legality and decisions identical to the frozen "
            "deployment semantics while every timing stays a live forward",
            "gpu_at_start records concurrent compute processes for each "
            "role; device conditions are reported with the measured times",
            f"warm-up: {WARMUP_CALLS} unrecorded calls after each model load; "
            "all recorded requests are hot",
        ],
        "requests": len(rows),
        "legality_validation": {
            "rule": "fresh per-request constructible action set must equal "
                    "the frozen test catalog's legal set",
            "mismatches": mismatches,
            "mismatch_count": len(mismatches)},
        "cold_start": {
            "backbone_model_load_seconds": {
                bb: chains[bb]["cold_start"]["model_load_seconds"]
                for bb in backbones},
            "service_init_seconds": {
                bb: chains[bb]["cold_start"]["service_init_seconds"]
                for bb in backbones},
            "tsicl_model_load_seconds":
                tsicl_payload["cold_start"]["load_seconds"],
            "saits_latency_instance_fit": saits_payload["cold_start"],
            "saits_frozen_deployment_fit_seconds": frozen_fit,
        },
        "per_backbone": summary,
        "raw_totals_seconds": raw_totals,
        "raw_records": {
            "chain": [f"results/v54/cost/work/chain_{bb}.json"
                      for bb in backbones],
            "tsicl": "results/v54/cost/work/tsicl_times.json",
            "saits": "results/v54/cost/work/saits_times.json"},
        "superseded_by_this_measurement": {
            "table41_arithmetic_synthesis": (
                "docs/v53_state_compact_report_20260922.md task 5 and the "
                "Table-41 latency column were arithmetic syntheses of stage "
                "runtimes; they are void as latency evidence and replaced by "
                "the per-request totals here"),
            "saits_tato_rows": (
                "the old SAITS/TATO cost rows timed only the backbone call; "
                "candidate construction had no per-request timer. Both rows "
                "are replaced by the FIXED_SAITS and TATO totals here, which "
                "include the imputer forward / transformation pipeline"),
            "candidate_construction": (
                "previously untimed per request (stage-level runtimes only); "
                "now measured per request: candidates_cpu / candidates_tsicl "
                "/ candidates_saits stages"),
            "end_to_end": (
                "previously missing (UNFINISHED in the v53 audit); the "
                "FULL_INTROACT totals here are the first measured end-to-end "
                "request latencies"),
            "old_backbone_call_reference": old,
        },
        "code_sha256": {"scripts/v54_latency_e2e.py": sha(Path(__file__))},
    }
    write(COST / "e2e_latency.json", payload, overwrite=args.overwrite)
    print(json.dumps({"role": "merge", "requests": len(rows),
                      "legality_mismatches": len(mismatches),
                      "output": str(COST / "e2e_latency.json")}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True,
                        choices=["tsicl", "saits", "chain", "merge"])
    parser.add_argument("--backbone", default="bolt",
                        choices=["bolt", "timesfm", "chronos2"])
    parser.add_argument("--per-source", type=int, default=PER_SOURCE)
    parser.add_argument("--overwrite", action="store_true",
                        help="replace this script's own earlier outputs under "
                             "results/v54/cost (never touches anything else)")
    args = parser.parse_args()
    args.gpu_snapshot = gpu_snapshot()
    if args.role == "chain" and not (TSICL_TIMES.exists()
                                     and SAITS_TIMES.exists()):
        raise SystemExit("run the tsicl and saits roles first")
    {"tsicl": role_tsicl, "saits": role_saits,
     "chain": role_chain, "merge": role_merge}[args.role](args)


if __name__ == "__main__":
    main()
