#!/usr/bin/env python3
"""v54 confirmatory SAITS action, with cross-fitted bank records.

A mirror of ``scripts/v47_saits.py`` bound to the confirmatory grid and
writing only under ``results/v54/confirmatory/``.  The protocol is unchanged:
bank records are cross-fitted over two parent folds (a window is imputed only
by a model that never saw its own parent), evaluation blocks are imputed by
the model fitted on the whole bank, and one repaired target channel per
episode is spliced back against the observation mask.

Native NaN cells (US_Term_Structure) are treated exactly like injected gaps:
they are missing inputs to the imputer and are repaired by the same splice.
"""

from __future__ import annotations

import argparse
import collections
import fcntl
import json
import subprocess
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v54/confirmatory/replay/saits"

#: Frozen configuration, identical to scripts/v47_saits.py.
CONFIG = dict(n_layers=2, d_model=128, n_heads=4, d_k=32, d_v=32, d_ffn=128,
              dropout=0.1, epochs=100, batch_size=16, patience=10)

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
    from introact_ts.v54 import confirmatory as G

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
    from introact_ts.v54 import confirmatory as G

    parents = [p for p in G.parents_of(root, FIT_BLOCK) if p.source == source]
    ordered = sorted(parents, key=lambda p: p.read_start)
    return {p.parent: i % FOLDS for i, p in enumerate(ordered)}


def fit_and_impute(train_panels, query_panels, epochs: int):
    """Fit one imputer on ``train_panels`` and impute ``query_panels``."""
    from pypots.imputation import SAITS

    raw = np.stack(train_panels)
    flat = raw.reshape(-1, raw.shape[2])
    centre = np.nanmean(flat, axis=0)
    scale = np.nanstd(flat, axis=0)
    scale = np.where(np.isfinite(scale) & (scale > 1e-8), scale, 1.0)
    centre = np.where(np.isfinite(centre), centre, 0.0)
    X = ((raw - centre) / scale).astype(np.float32)
    model = SAITS(n_steps=X.shape[1], n_features=X.shape[2], epochs=epochs,
                  device="cuda", **{k: v for k, v in CONFIG.items() if k != "epochs"})
    model.fit({"X": X})
    Y_raw = np.stack(query_panels)
    Y = ((Y_raw - centre) / scale).astype(np.float32)
    imputed = np.asarray(model.impute({"X": Y}), dtype=np.float64)
    imputed = imputed * scale + centre
    del model, X, raw
    return Y_raw, imputed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="crossfit", choices=["crossfit", "full"])
    parser.add_argument("--blocks", default="",
                        help="blocks to impute; defaults depend on the mode")
    parser.add_argument("--sources", default="")
    parser.add_argument("--epochs", type=int, default=CONFIG["epochs"])
    args = parser.parse_args()

    import torch
    from introact_ts.v54 import confirmatory as G

    began = time.perf_counter()
    default_blocks = (FIT_BLOCK if args.mode == "crossfit"
                      else "train_eval,test,test_m2,test_m3")
    blocks = [b.strip() for b in (args.blocks or default_blocks).split(",") if b.strip()]
    sources = [s for s in args.sources.split(",") if s] or G.source_names(ROOT)

    arrays: dict[str, dict[str, np.ndarray]] = {b: {} for b in blocks}
    report: dict[str, dict] = {}

    with (ROOT / "locks/gpu-saits-confirmatory.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        free_mib = int(subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            text=True).strip().splitlines()[0])
        if free_mib < MIN_FREE_MIB:
            raise RuntimeError(f"only {free_mib} MiB of GPU memory is free")
        torch.manual_seed(101)
        np.random.seed(101)

        for source in sources:
            tick = time.perf_counter()
            columns, fit_rows = collect(ROOT, FIT_BLOCK, source, None)
            if not fit_rows:
                report[source] = {"status": "no fit windows"}
                continue

            if args.mode == "crossfit":
                folds = fold_of(ROOT, source)
                per_block = collections.defaultdict(int)
                used_folds = sorted(set(folds.values()))
                for fold in used_folds:
                    train = [panel for _e, parent, panel in fit_rows
                             if folds.get(parent, 0) != fold]
                    queries = [(e, parent, panel)
                               for e, parent, panel in fit_rows
                               if folds.get(parent, 0) == fold]
                    if not train or not queries:
                        continue
                    Y_raw, imputed = fit_and_impute(
                        train, [q[2] for q in queries], args.epochs)
                    for i, (episode, _parent, _panel) in enumerate(queries):
                        original = Y_raw[i, :, 0]
                        hidden = ~np.isfinite(original)
                        repaired = original.astype(np.float64).copy()
                        repaired[hidden] = imputed[i, :, 0][hidden]
                        if not np.isfinite(repaired).all():
                            continue
                        arrays[FIT_BLOCK][f"{episode}|SAITS"] = repaired
                        per_block[FIT_BLOCK] += 1
                    torch.cuda.empty_cache()
                report[source] = {
                    "status": "ok", "mode": "crossfit", "folds": len(used_folds),
                    "fit_windows": len(fit_rows),
                    "channels_used": int(len(columns)),
                    "episodes": dict(per_block),
                    "total_seconds": time.perf_counter() - tick,
                }
            else:
                train = [panel for _e, _p, panel in fit_rows]
                per_block = {}
                for block in blocks:
                    _cols, rows = collect(ROOT, block, source, columns)
                    if not rows:
                        continue
                    Y_raw, imputed = fit_and_impute(
                        train, [r[2] for r in rows], args.epochs)
                    for i, (episode, _parent, _panel) in enumerate(rows):
                        original = Y_raw[i, :, 0]
                        hidden = ~np.isfinite(original)
                        repaired = original.astype(np.float64).copy()
                        repaired[hidden] = imputed[i, :, 0][hidden]
                        if not np.isfinite(repaired).all():
                            continue
                        arrays[block][f"{episode}|SAITS"] = repaired
                    per_block[block] = len(rows)
                    torch.cuda.empty_cache()
                report[source] = {
                    "status": "ok", "mode": "full",
                    "fit_windows": len(fit_rows),
                    "channels_used": int(len(columns)),
                    "episodes": per_block,
                    "total_seconds": time.perf_counter() - tick,
                }
            print(json.dumps({source: report[source]}), flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    written = {}
    for block, payload in arrays.items():
        if not payload:
            continue
        path = OUT / f"{block}.npz"
        if path.exists():
            raise SystemExit(f"refusing to overwrite existing SAITS output {path}")
        with path.open("wb") as handle:
            np.savez(handle, **payload)
        written[str(path.name)] = len(payload)

    report_path = OUT / f"report_{args.mode}.json"
    if report_path.exists():
        raise SystemExit(f"refusing to overwrite existing SAITS report {report_path}")
    write(report_path, {
        "stage": "v54-confirmatory-saits-action",
        "mode": args.mode,
        "config": CONFIG,
        "epochs": args.epochs,
        "fit_block": FIT_BLOCK,
        "folds": FOLDS,
        "max_channels": MAX_CHANNELS,
        "standardisation": "per source and channel, statistics from the fit panels only",
        "blocks": blocks,
        "per_source": report,
        "arrays": written,
        "heldout_labels_read": 0,
        "runtime_seconds": time.perf_counter() - began,
    })
    print(json.dumps({"arrays": written,
                      "runtime_seconds": time.perf_counter() - began}, indent=1))


if __name__ == "__main__":
    main()
