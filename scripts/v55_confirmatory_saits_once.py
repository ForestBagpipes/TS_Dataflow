#!/usr/bin/env python3
"""One full-bank SAITS fit per confirmatory source, reused for every block.

This corrects the repeated-fit behavior of the v54 full stage. Outputs are
isolated under results/v55 and the v54 archives remain available for audit.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from introact_ts.v54 import confirmatory as G

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v54_confirmatory_saits as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v55/confirmatory/replay/saits"
BLOCKS = ("train_eval", "test", "test_m2", "test_m3")


def source_fit(source: str, blocks: tuple[str, ...], epochs: int,
               fit_fn=S.fit_and_impute) -> tuple[dict[str, dict[str, np.ndarray]], dict]:
    """Fit once, then split a single inference batch back into its blocks."""
    columns, fit_rows = S.collect(ROOT, S.FIT_BLOCK, source, None)
    if not fit_rows:
        raise RuntimeError(f"{source}: no bank windows")
    grouped = {}
    queries = []
    for block in blocks:
        _columns, rows = S.collect(ROOT, block, source, columns)
        grouped[block] = rows
        queries.extend((block, episode, panel) for episode, _parent, panel in rows)
    if not queries:
        raise RuntimeError(f"{source}: no evaluation windows")
    raw, imputed = fit_fn([panel for _episode, _parent, panel in fit_rows],
                          [panel for _block, _episode, panel in queries], epochs)
    if len(raw) != len(queries) or imputed.shape != raw.shape:
        raise RuntimeError(f"{source}: unexpected SAITS output shape")
    arrays = {block: {} for block in blocks}
    for i, (block, episode, _panel) in enumerate(queries):
        original = raw[i, :, 0]
        repaired = original.astype(np.float64).copy()
        hidden = ~np.isfinite(original)
        repaired[hidden] = imputed[i, :, 0][hidden]
        if not np.isfinite(repaired).all():
            raise RuntimeError(f"{source}/{block}/{episode}: non-finite repair")
        arrays[block][f"{episode}|SAITS"] = repaired
    return arrays, {
        "status": "ok", "fits": 1, "fit_windows": len(fit_rows),
        "channels_used": int(len(columns)),
        "episodes": {block: len(grouped[block]) for block in blocks},
        "inference_windows": len(queries),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=S.CONFIG["epochs"])
    parser.add_argument("--sources", default="")
    args = parser.parse_args()
    sources = tuple(s for s in args.sources.split(",") if s) or tuple(G.source_names(ROOT))
    if OUT.exists() and any(OUT.glob("*.npz")):
        raise SystemExit(f"refusing to overwrite existing SAITS output in {OUT}")
    import torch

    began = time.perf_counter()
    arrays = {block: {} for block in BLOCKS}
    report = {}
    with (ROOT / "locks/gpu.lock").open("a") as gpu_lock, \
            (ROOT / "locks/gpu-saits-confirmatory.lock").open("a") as own_lock:
        fcntl.flock(gpu_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(own_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        free_mib = int(subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            text=True).strip().splitlines()[0])
        if free_mib < S.MIN_FREE_MIB:
            raise RuntimeError(f"only {free_mib} MiB of GPU memory is free")
        for source in sources:
            torch.manual_seed(101)
            np.random.seed(101)
            tick = time.perf_counter()
            payload, meta = source_fit(source, BLOCKS, args.epochs)
            for block in BLOCKS:
                arrays[block].update(payload[block])
            report[source] = {**meta, "total_seconds": time.perf_counter() - tick}
            torch.cuda.empty_cache()
            print(json.dumps({source: report[source]}), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    written = {}
    for block, payload in arrays.items():
        path = OUT / f"{block}.npz"
        if path.exists():
            raise SystemExit(f"refusing to overwrite {path}")
        with path.open("wb") as handle:
            np.savez(handle, **payload)
        written[path.name] = len(payload)
    S.write(OUT / "report_full_once.json", {
        "stage": "v55-confirmatory-saits-once", "config": S.CONFIG,
        "epochs": args.epochs, "fit_block": S.FIT_BLOCK,
        "fit_per_source": 1, "blocks": BLOCKS, "per_source": report,
        "arrays": written, "heldout_labels_used_for_training": 0,
        "runtime_seconds": time.perf_counter() - began,
    })


if __name__ == "__main__":
    main()
