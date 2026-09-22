#!/usr/bin/env python3
"""The trained imputer as a catalog action, with cross-fitted bank records.

The imputer is a model, so the utility it earns on a window it was trained on
is not the utility it earns on a new request.  A bank record built that way
would tell the selector that this action is better than it is, and the
selector would then execute it too often at deployment.  The bank records are
therefore cross-fitted: the parents of each source are split into folds, and a
window is imputed only by a model that never saw its own parent.  Evaluation
blocks are imputed by the model fitted on the whole bank, which is what a
deployment would hold.

Both paths write one repaired target channel per episode into
``results/v47/replay/saits/<block>.npz`` under the key ``<episode>|SAITS``.
The repaired panel is spliced back against the observation mask, so an entry
that arrived and is valid is returned unchanged.
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
OUT = ROOT / "results/v47/replay/saits"

#: Frozen before any run and identical to the configuration the published
#: baseline was given in v4.6, so the action and the baseline row are the same
#: model rather than two different ones.
CONFIG = dict(n_layers=2, d_model=128, n_heads=4, d_k=32, d_v=32, d_ffn=128,
              dropout=0.1, epochs=100, batch_size=16, patience=10)

#: Sources with many channels are imputed on the target channel plus the
#: covariates most correlated with it on TRAIN, because a full 862-channel
#: panel does not fit the budget.  The cap is a protocol constant.
MAX_CHANNELS = 64

#: Free device memory a stage requires before it starts.  The checkpoints
#: here are small and several stages share the device, so the floor only has
#: to rule out a genuinely full device.
MIN_FREE_MIB = 3072

#: Number of parent folds used to cross-fit the bank records.  Two folds keep
#: the fitted model at half the parents of the deployment model, which is the
#: gap the appendix reports, and they cost a third of what four folds cost.
FOLDS = 2

#: The block whose panels train the model, and the blocks the folds cover.
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
    parser.add_argument("--tag", default="",
                        help="shard name; shards write their own archive and are merged")
    args = parser.parse_args()

    import torch
    from introact_ts.v44 import protocol as P

    began = time.perf_counter()
    default_blocks = ("bankx,bankx2" if args.mode == "crossfit"
                      else "train_eval,test,test30,test50,test_m2,test_m3")
    blocks = [b.strip() for b in (args.blocks or default_blocks).split(",") if b.strip()]
    sources = [s for s in args.sources.split(",") if s] or list(P.SOURCES)

    arrays: dict[str, dict[str, np.ndarray]] = {b: {} for b in blocks}
    report: dict[str, dict] = {}

    shard = f"-{args.tag}" if args.tag else ""
    with (ROOT / f"locks/gpu-saits-{args.mode}{shard}.lock").open("a") as lock:
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
                block_rows = {}
                for block in blocks:
                    if block == FIT_BLOCK:
                        block_rows[block] = fit_rows
                    else:
                        _cols, rows = collect(ROOT, block, source, columns)
                        block_rows[block] = rows
                used_folds = sorted(set(folds.values()))
                for fold in used_folds:
                    train = [panel for _e, parent, panel in fit_rows
                             if folds.get(parent, 0) != fold]
                    queries = [(block, e, panel)
                               for block in blocks
                               for e, parent, panel in block_rows[block]
                               if folds.get(parent, 0) == fold]
                    if not train or not queries:
                        continue
                    Y_raw, imputed = fit_and_impute(
                        train, [q[2] for q in queries], args.epochs)
                    for i, (block, episode, _panel) in enumerate(queries):
                        original = Y_raw[i, :, 0]
                        hidden = ~np.isfinite(original)
                        repaired = original.astype(np.float64).copy()
                        repaired[hidden] = imputed[i, :, 0][hidden]
                        if not np.isfinite(repaired).all():
                            continue
                        arrays[block][f"{episode}|SAITS"] = repaired
                        per_block[block] += 1
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
        # A shard writes its own archive; the merge step joins them, so two
        # shards never write the same file at the same time.
        path = OUT / (f"{block}__{args.tag}.npz" if args.tag else f"{block}.npz")
        with path.open("wb") as handle:
            np.savez(handle, **payload)
        written[str(path.name)] = len(payload)

    write(OUT / f"report_{args.mode}{shard}.json", {
        "stage": "v47-saits-action",
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
