"""Parallel shard runner for BRITS/CSDI on the v47_saits.py protocol.

Same protocol and frozen configuration as ``scripts/v54_external_imputers.py``
(same cross-fitting, same splice-back, same CONFIGS), with three execution
changes that do not change any model output semantics:

* ``full`` mode fits the deployment model **once per source** and imputes all
  evaluation blocks with that single model -- the protocol describes one
  deployment model fitted on the whole bank, not one per block.
* Units are shards ``(method, source, mode)`` addressed by ``--tag``; a shard
  whose archive already exists is skipped before any compute, so a scheduler
  can relaunch freely.
* Status is written per shard (``status_<mode>-<tag>.json``) so concurrent
  shards never race on a shared file.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

CONFIGS = {
    "BRITS": dict(rnn_hidden_size=128, epochs=100, batch_size=16, patience=10),
    "CSDI": dict(n_layers=2, n_heads=4, n_channels=128, d_time_embedding=128,
                 d_feature_embedding=128, d_diffusion_embedding=128,
                 n_diffusion_steps=50, target_strategy="random",
                 epochs=100, batch_size=16, patience=10),
}

MAX_CHANNELS = 64
MIN_FREE_MIB = 3072
FOLDS = 2
FIT_BLOCK = "bankx"


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def channel_subset(panel: np.ndarray, cap: int) -> np.ndarray:
    """Target channel plus the covariates most correlated with it."""
    if panel.shape[1] <= cap:
        return np.arange(panel.shape[1])
    target = panel[:, 0]
    finite = np.isfinite(target)
    scores = []
    for c in range(1, panel.shape[1]):
        other = panel[:, c]
        ok = finite & np.isfinite(other)
        if ok.sum() < 16:
            scores.append(0.0)
            continue
        a, b = target[ok] - target[ok].mean(), other[ok] - other[ok].mean()
        denom = float(np.sqrt((a @ a) * (b @ b)))
        scores.append(abs(float(a @ b / denom)) if denom > 1e-12 else 0.0)
    order = np.argsort(scores)[::-1][:cap - 1] + 1
    return np.concatenate([[0], np.sort(order)])


def collect(root: Path, block: str, source: str, columns: np.ndarray | None):
    """``(episode, parent, panel)`` of one source, already channel subset."""
    from introact_ts.v46 import grid as G

    specs = [s for s in G.episode_specs(root, block) if s.source == source]
    if not specs:
        return columns, []
    rows = []
    for spec, _raw, masked, _future in G.iter_panels(root, specs):
        if columns is None:
            columns = channel_subset(masked, MAX_CHANNELS)
        rows.append((spec.episode_id, spec.parent,
                     masked[:, columns].astype(np.float32)))
    return columns, rows


def fold_of(root: Path, source: str) -> dict[str, int]:
    """Parent to fold, by origin order, fixed before any model runs."""
    from introact_ts.v46 import grid as G

    parents = [p for p in G.parents_of(root, FIT_BLOCK) if p.source == source]
    ordered = sorted(parents, key=lambda p: p.read_start)
    return {p.parent: i % FOLDS for i, p in enumerate(ordered)}


def fit_model(method: str, train_panels, epochs: int):
    """Fit one imputer; returns (model, centre, scale) for reuse."""
    from pypots.imputation import BRITS, CSDI

    config = {k: v for k, v in CONFIGS[method].items() if k != "epochs"}
    raw = np.stack(train_panels)
    flat = raw.reshape(-1, raw.shape[2])
    centre = np.nanmean(flat, axis=0)
    scale = np.nanstd(flat, axis=0)
    scale = np.where(np.isfinite(scale) & (scale > 1e-8), scale, 1.0)
    centre = np.where(np.isfinite(centre), centre, 0.0)
    X = ((raw - centre) / scale).astype(np.float32)
    cls = {"BRITS": BRITS, "CSDI": CSDI}[method]
    model = cls(n_steps=X.shape[1], n_features=X.shape[2], epochs=epochs,
                device="cuda", **config)
    model.fit({"X": X})
    del X, raw
    return model, centre, scale


def impute_with(model, centre, scale, query_panels):
    Y_raw = np.stack(query_panels)
    Y = ((Y_raw - centre) / scale).astype(np.float32)
    imputed = np.asarray(model.impute({"X": Y}), dtype=np.float64)
    return Y_raw, imputed * scale + centre


def splice(method: str, Y_raw, imputed, rows, arrays, failures):
    """Write one repaired target channel per episode, as v47_saits.py does."""
    from introact_ts.v44 import actions as A

    written = 0
    for i, (episode, _parent, _panel) in enumerate(rows):
        original = Y_raw[i, :, 0]
        hidden = ~np.isfinite(original)
        repaired = original.astype(np.float64).copy()
        repaired[hidden] = imputed[i, :, 0][hidden]
        if not np.isfinite(repaired).all():
            failures["non_finite_repair"] += 1
            continue
        reason = A.implausible_reason(repaired, original)
        if reason is not None:
            failures["implausible"] += 1
        arrays[f"{episode}|{method}"] = repaired
        written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", required=True, choices=sorted(CONFIGS))
    parser.add_argument("--mode", default="crossfit", choices=["crossfit", "full"])
    parser.add_argument("--blocks", default="")
    parser.add_argument("--sources", default="")
    parser.add_argument("--epochs", type=int, default=0)
    parser.add_argument("--tag", required=True, help="shard name (required)")
    args = parser.parse_args()

    import torch
    from introact_ts.v44 import protocol as P

    method = args.method
    config = dict(CONFIGS[method])
    if args.epochs:
        config["epochs"] = args.epochs
    config_sha = hashlib.sha256(
        json.dumps({method: config}, sort_keys=True).encode()).hexdigest()[:16]
    out = ROOT / f"results/v54/replay/external/{method.lower()}"

    began = time.perf_counter()
    default_blocks = (FIT_BLOCK if args.mode == "crossfit"
                      else "train_eval,test,test30,test50,test_m2,test_m3")
    blocks = [b.strip() for b in (args.blocks or default_blocks).split(",") if b.strip()]
    sources = [s for s in args.sources.split(",") if s] or list(P.SOURCES)
    if len(sources) != 1:
        raise SystemExit("parallel shards take exactly one --sources entry")

    def shard_path(block: str) -> Path:
        return out / f"{block}__{args.tag}.npz"

    todo = [b for b in blocks if not shard_path(b).exists()]
    if not todo:
        print(json.dumps({"skipped": "all shard archives exist"}))
        return

    free_mib = int(subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        text=True).strip().splitlines()[0])
    if free_mib < MIN_FREE_MIB:
        raise RuntimeError(f"only {free_mib} MiB of GPU memory is free")
    torch.manual_seed(101)
    np.random.seed(101)

    arrays: dict[str, dict[str, np.ndarray]] = {b: {} for b in todo}
    report: dict[str, dict] = {}
    failures = collections.Counter()

    source = sources[0]
    tick = time.perf_counter()
    try:
        columns, fit_rows = collect(ROOT, FIT_BLOCK, source, None)
        if not fit_rows:
            report[source] = {"status": "no fit windows"}
            failures["no_fit_windows"] += 1
        elif args.mode == "crossfit":
            folds = fold_of(ROOT, source)
            used_folds = sorted(set(folds.values()))
            for fold in used_folds:
                train = [panel for _e, parent, panel in fit_rows
                         if folds.get(parent, 0) != fold]
                queries = [(e, parent, panel)
                           for e, parent, panel in fit_rows
                           if folds.get(parent, 0) == fold]
                if not train or not queries:
                    continue
                model, centre, scale = fit_model(method, train, config["epochs"])
                Y_raw, imputed = impute_with(model, centre, scale,
                                             [q[2] for q in queries])
                splice(method, Y_raw, imputed, queries,
                       arrays[FIT_BLOCK], failures)
                del model
                torch.cuda.empty_cache()
            report[source] = {
                "status": "ok", "mode": "crossfit", "folds": len(used_folds),
                "fit_windows": len(fit_rows),
                "channels_used": int(len(columns)),
                "episodes": {FIT_BLOCK: len(arrays[FIT_BLOCK])},
                "total_seconds": time.perf_counter() - tick,
            }
        else:
            # One deployment model per source, reused across every eval block.
            train = [panel for _e, _p, panel in fit_rows]
            model, centre, scale = fit_model(method, train, config["epochs"])
            per_block = {}
            for block in todo:
                _cols, rows = collect(ROOT, block, source, columns)
                if not rows:
                    continue
                Y_raw, imputed = impute_with(model, centre, scale,
                                             [r[2] for r in rows])
                per_block[block] = splice(method, Y_raw, imputed, rows,
                                          arrays[block], failures)
                torch.cuda.empty_cache()
            del model
            report[source] = {
                "status": "ok", "mode": "full",
                "fit_windows": len(fit_rows),
                "channels_used": int(len(columns)),
                "episodes": per_block,
                "total_seconds": time.perf_counter() - tick,
            }
    except Exception as exc:  # a failed shard must not sink the scheduler
        report[source] = {"status": f"failed: {type(exc).__name__}: {exc}"}
        failures[f"exception:{type(exc).__name__}"] += 1

    out.mkdir(parents=True, exist_ok=True)
    written = {}
    for block, payload in arrays.items():
        if not payload:
            continue
        path = shard_path(block)
        tmp = path.with_suffix(".npz.tmp")
        with tmp.open("wb") as handle:
            np.savez(handle, **payload)
        tmp.rename(path)  # atomic publish: a scheduler never sees a half file
        written[path.name] = len(payload)

    run_record = {
        "mode": args.mode,
        "blocks": blocks,
        "todo_blocks": todo,
        "sources": sources,
        "per_source": report,
        "failures": dict(sorted(failures.items())),
        "arrays": written,
        "runtime_seconds": time.perf_counter() - began,
    }
    payload = {
        "stage": "v54-external-imputers-par",
        "method": method,
        "config": config,
        "config_sha256": config_sha,
        "fit_block": FIT_BLOCK,
        "folds": FOLDS,
        "max_channels": MAX_CHANNELS,
        "standardisation": "per source and channel, statistics from the fit panels only",
        "heldout_labels_read": 0,
        **run_record,
    }
    write(out / f"report_{args.mode}-{args.tag}.json", payload)
    write(out / f"status_{args.mode}-{args.tag}.json", payload)
    print(json.dumps({"arrays": written, "failures": dict(failures),
                      "runtime_seconds": run_record["runtime_seconds"]},
                     indent=1))


if __name__ == "__main__":
    main()
