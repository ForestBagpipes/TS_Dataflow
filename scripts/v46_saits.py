#!/usr/bin/env python3
"""SAITS on the v4.6 protocol: one imputer per source, trained on TRAIN only.

SAITS is the reconstruction baseline.  It is trained per source on the TRAIN
bank windows after the registered missingness protocol has been injected, which
is the same input distribution the evaluation sees, and it is never shown a
TEST window or a future target during training.

The output is spliced back against the observation mask, so an entry that
arrived and is valid is returned unchanged and only the missing positions carry
the imputed values.  That is the same integrity constraint every catalog action
obeys, and it is what makes the comparison a comparison of input versions.

Writes one candidate array per episode, which the forecast stage then runs
through each frozen backbone.
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
REPLAY = ROOT / "results/v46/replay"
OUT = ROOT / "results/v46/baselines"

#: Frozen before any run.  Small enough to train eight imputers inside the
#: budget, large enough to be the published architecture rather than a toy.
CONFIG = dict(n_layers=2, d_model=128, n_heads=4, d_k=32, d_v=32, d_ffn=128,
              dropout=0.1, epochs=100, batch_size=16, patience=10)
TRAIN_BLOCK = "bank"
#: Sources with many channels are imputed on the target channel plus the
#: covariates most correlated with it on TRAIN, because a full 862-channel
#: panel does not fit the budget.  The cap is a protocol constant.
MAX_CHANNELS = 64


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def panels(root: Path, block: str, source: str):
    """Masked panels of one source, in episode order, as (episode, panel)."""
    from introact_ts.v46 import grid as G

    specs = [s for s in G.episode_specs(root, block) if s.source == source]
    for spec, _raw, masked, _future in G.iter_panels(root, specs):
        yield spec.episode_id, masked


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blocks", default="test,test30,test50")
    parser.add_argument("--sources", default="")
    parser.add_argument("--epochs", type=int, default=CONFIG["epochs"])
    args = parser.parse_args()

    import torch
    from pypots.imputation import SAITS
    from introact_ts.v44 import protocol as P

    began = time.perf_counter()
    blocks = [b for b in args.blocks.split(",") if b]
    sources = [s for s in args.sources.split(",") if s] or list(P.SOURCES)
    run_dir = OUT / "saits"
    run_dir.mkdir(parents=True, exist_ok=True)

    arrays: dict[str, np.ndarray] = {}
    report: dict[str, dict] = {}

    with (ROOT / "locks/gpu.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        active = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
            text=True).strip()
        if active:
            raise RuntimeError("GPU has active processes; refusing to interfere")
        torch.manual_seed(101)
        np.random.seed(101)

        for source in sources:
            tick = time.perf_counter()
            train_keys, train_panels = [], []
            for key, panel in panels(ROOT, TRAIN_BLOCK, source):
                train_keys.append(key)
                train_panels.append(panel.astype(np.float32))
            if not train_panels:
                report[source] = {"status": "no training windows"}
                continue
            columns = channel_subset(train_panels[0], MAX_CHANNELS)
            raw = np.stack([p[:, columns] for p in train_panels])
            # SAITS expects a standardised input; the statistics come from the
            # TRAIN panels of this source only and are reused unchanged on the
            # evaluation panels, so no evaluation value enters the scaling.
            centre = np.nanmean(raw.reshape(-1, raw.shape[2]), axis=0)
            scale = np.nanstd(raw.reshape(-1, raw.shape[2]), axis=0)
            scale = np.where(np.isfinite(scale) & (scale > 1e-8), scale, 1.0)
            centre = np.where(np.isfinite(centre), centre, 0.0)
            X = ((raw - centre) / scale).astype(np.float32)
            model = SAITS(n_steps=X.shape[1], n_features=X.shape[2],
                          epochs=args.epochs, device="cuda",
                          **{k: v for k, v in CONFIG.items() if k != "epochs"})
            model.fit({"X": X})
            fit_seconds = time.perf_counter() - tick

            per_block = {}
            for block in blocks:
                keys, stack = [], []
                for key, panel in panels(ROOT, block, source):
                    keys.append(key)
                    stack.append(panel[:, columns].astype(np.float32))
                if not stack:
                    continue
                Y_raw = np.stack(stack)
                Y = ((Y_raw - centre) / scale).astype(np.float32)
                imputed = np.asarray(model.impute({"X": Y}), dtype=np.float64)
                imputed = imputed * scale + centre
                for i, key in enumerate(keys):
                    original = Y_raw[i, :, 0]
                    hidden = ~np.isfinite(original)
                    repaired = original.astype(np.float64).copy()
                    repaired[hidden] = imputed[i, :, 0][hidden]
                    if not np.isfinite(repaired).all():
                        continue
                    arrays[f"{block}|{key}"] = repaired
                per_block[block] = len(keys)
            report[source] = {
                "status": "ok", "train_windows": len(train_panels),
                "channels_used": int(len(columns)),
                "channels_available": int(train_panels[0].shape[1]),
                "fit_seconds": fit_seconds,
                "episodes": per_block,
                "total_seconds": time.perf_counter() - tick,
            }
            print(json.dumps({source: report[source]}), flush=True)
            del model, X, raw
            torch.cuda.empty_cache()

    with (run_dir / "candidates.npz").open("wb") as handle:
        np.savez(handle, **arrays)
    write(run_dir / "report.json", {
        "stage": "v46-saits", "config": CONFIG, "epochs": args.epochs,
        "train_block": TRAIN_BLOCK, "max_channels": MAX_CHANNELS,
        "standardisation": "per source and channel, statistics from the TRAIN panels only",
        "blocks": blocks, "per_source": report, "arrays": len(arrays),
        "heldout_labels_read": 0,
        "runtime_seconds": time.perf_counter() - began,
    })
    print(json.dumps({"arrays": len(arrays),
                      "runtime_seconds": time.perf_counter() - began}, indent=1))


if __name__ == "__main__":
    main()
