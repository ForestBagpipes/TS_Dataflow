#!/usr/bin/env python3
"""TATO on the v4.6 protocol: one transformation pipeline per source and backbone.

TATO adapts a frozen forecaster to a domain by searching a transformation
pipeline and selecting it from historical task performance, so the unit of
adaptation here is the source.  The search runs on TRAIN windows only and
scores a candidate pipeline by its mean absolute error against the realised
future of those TRAIN windows, which is the same evidence the replay bank is
built from, so neither method is given information the other lacks.  The
selected pipeline is then applied unchanged to every TEST request of that
source.

The official implementation is used through the frozen r5 adapter, which
forbids the upstream non-finite replacement and checks that the checkout is
unmodified.  Nothing here touches the backbone's parameters.
"""

from __future__ import annotations

import argparse
import collections
import fcntl
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BASELINES = ROOT / "scripts/v431_baselines"
REPLAY = ROOT / "results/v46/replay"
OUT = ROOT / "results/v46/baselines"

#: Search budget.  A trial costs one backbone call per search window, so the
#: cost of the search is trials x windows per (source, backbone).
DEFAULT_TRIALS = 48
DEFAULT_WINDOWS = 8
SEARCH_BLOCK = "bank"


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def load_rows(block: str) -> list[dict]:
    return json.loads((REPLAY / "inputs" / f"{block}.json").read_text())["rows"]


def search_windows(rows: list[dict], per_source: int) -> dict[str, list[dict]]:
    """A deterministic, fixed subset of TRAIN episodes per source.

    Sorted by episode id and taken at an even stride so the subset spans the
    block rather than its first few parents.
    """
    by_source: dict[str, list[dict]] = collections.defaultdict(list)
    for row in sorted(rows, key=lambda r: r["episode"]):
        by_source[row["source"]].append(row)
    out = {}
    for source, items in by_source.items():
        if not items:
            continue
        step = max(1, len(items) // per_source)
        out[source] = items[::step][:per_source]
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--block", default="test")
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument("--windows", type=int, default=DEFAULT_WINDOWS)
    parser.add_argument("--deadline-minutes", type=float, default=0.0)
    args = parser.parse_args()

    began = time.perf_counter()
    limit = began + args.deadline_minutes * 60 if args.deadline_minutes else None
    sys.path[:0] = [str(BASELINES)]
    # The adapter puts the vendored dependency directory on the path when it is
    # imported, so it has to come before optuna.
    import tato_adapter as adapter
    import optuna
    import worker as baseline_worker

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    identity = adapter.official_identity()
    _, tuner_factory = adapter.load_official()

    train_rows = load_rows(SEARCH_BLOCK)
    eval_rows = load_rows(args.block)
    picks = search_windows(train_rows, args.windows)

    run_dir = OUT / f"tato_{args.block}_{args.backbone}"
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)

    with (ROOT / "locks/gpu.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        active = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
            text=True).strip()
        if active:
            raise RuntimeError("GPU has active processes; refusing to interfere")
        import torch
        torch.manual_seed(101)
        np.random.seed(101)
        if args.backbone == "bolt":
            model = baseline_worker.Bolt(run_dir)
        elif args.backbone == "timesfm":
            model = baseline_worker.TimesFM(run_dir)
        else:
            sys.path.insert(0, str(ROOT / "scripts"))
            from v46_chronos2 import Chronos2
            model = Chronos2(run_dir)

        # ---- search, per source, on TRAIN only -----------------------------
        # The search depends only on the backbone and the TRAIN windows, so it
        # is done once per backbone and reused across evaluation blocks.
        cache = OUT / f"tato_search_{args.backbone}.json"
        selected: dict[str, dict] = {}
        search_log: list[dict] = []
        if cache.exists():
            payload = json.loads(cache.read_text())
            selected = payload["selected"]
            search_log = payload.get("search_log", [])
            print(json.dumps({"search": "reused", "sources": sorted(selected)}), flush=True)
        else:
          with np.load(REPLAY / "inputs" / f"{SEARCH_BLOCK}.npz", allow_pickle=False) as store:
              for source, items in sorted(picks.items()):
                  tuner = tuner_factory.build_optuna_tuner(
                      enqueue_param_dicts=[adapter.vanilla()], mode="train", seed=101)
                  space = tuner_factory.build_search_space(
                      adapter.NAMES, patch_len=16 if args.backbone == "bolt" else 32)
                  best = None
                  for number in range(args.trials):
                      if limit and time.perf_counter() > limit:
                          break
                      trial = tuner.pick_trial(space)
                      losses = []
                      try:
                          for row in items:
                              # The search sees the same evidence the replay bank sees: a
                              # TRAIN window, its injected missingness, and the future that
                              # window already has. Scoring on the context tail instead
                              # would hand TATO strictly less information than the method
                              # it is compared with.
                              context = store[f"{row['episode']}|reference"]
                              target = store[f"{row['episode']}|future"]
                              horizon = int(row["horizon"])
                              seen = np.isfinite(target)
                              if not seen.any():
                                  continue
                              prediction, _ = adapter.predict_native(
                                  trial.params, model, context, horizon)
                              losses.append(float(np.mean(
                                  np.abs(prediction[seen] - target[seen]))))
                          if not losses:
                              raise ValueError("no usable search window")
                          loss = float(np.mean(losses))
                          tuner.tell(trial, loss)
                          search_log.append({"source": source, "trial": number,
                                             "status": "completed", "loss": loss})
                          if best is None or loss < best["loss"]:
                              best = {"loss": loss, "params": dict(trial.params),
                                      "trial": number}
                      except (ValueError, FloatingPointError, AssertionError,
                              RuntimeError) as exc:
                          tuner.study.tell(trial, state=optuna.trial.TrialState.FAIL)
                          search_log.append({"source": source, "trial": number,
                                             "status": "failed",
                                             "error": f"{type(exc).__name__}: {exc}"})
                  if best is None:
                      best = {"loss": None, "params": adapter.vanilla(), "trial": -1,
                              "note": "every searched pipeline failed; the vanilla "
                                      "pipeline is used and the failure is recorded"}
                  selected[source] = best
                  print(json.dumps({"source": source, "selected_trial": best["trial"],
                                    "loss": best["loss"],
                                    "elapsed": time.perf_counter() - began}), flush=True)

          write(cache, {"stage": "v46-tato-search", "backbone": args.backbone,
                        "trials": args.trials, "windows_per_source": args.windows,
                        "selected": selected, "search_log": search_log})

        # ---- deploy the selected pipeline on the evaluation block ----------
        records: dict[str, dict] = {}
        failures: list[dict] = []
        predictions: dict[str, np.ndarray] = {}
        with np.load(REPLAY / "inputs" / f"{args.block}.npz", allow_pickle=False) as store:
            for index, row in enumerate(eval_rows):
                key = row["episode"]
                params = selected.get(row["source"], {}).get("params")
                if params is None:
                    failures.append({"episode": key, "reason": "no pipeline for source"})
                    continue
                try:
                    context = store[f"{key}|reference"]
                    future = store[f"{key}|future"]
                    prediction, _ = adapter.predict_native(
                        params, model, context, int(row["horizon"]))
                    error = prediction - future
                    mae = float(np.mean(np.abs(error)))
                    mse = float(np.mean(error ** 2))
                    records[key] = {
                        "mae": mae, "mse": mse,
                        "mase": mae / row["mase_scale"] if row["mase_scale"] else None,
                        "rmsse": (float(np.sqrt(mse / row["rmsse_scale"]))
                                  if row["rmsse_scale"] else None),
                        "source": row["source"], "parent": row["parent"],
                        "horizon": row["horizon"], "pattern": row["pattern"],
                        "severity": row["severity"],
                    }
                    predictions[key] = prediction.astype(np.float64)
                except (ValueError, FloatingPointError, AssertionError) as exc:
                    failures.append({"episode": key,
                                     "reason": f"{type(exc).__name__}: {exc}"})
                if index % 100 == 0:
                    print(json.dumps({"done": index, "total": len(eval_rows),
                                      "elapsed": time.perf_counter() - began}), flush=True)

    with (run_dir / "predictions.npz").open("wb") as handle:
        np.savez(handle, **predictions)
    # The per-call dumps are a byte-level trace of calls whose predictions are
    # already in predictions.npz, and the search alone makes thousands of them.
    # Their count is recorded and the files are removed.
    raw_files = sorted((run_dir / "raw").glob("call_*.npz"))
    raw_calls = len(raw_files)
    for path in raw_files:
        path.unlink()
    (run_dir / "raw").rmdir()
    write(run_dir / "records.json", {
        "stage": "v46-tato", "backbone": args.backbone, "block": args.block,
        "trials": args.trials, "windows_per_source": args.windows,
        "search_block": SEARCH_BLOCK,
        "selected": {s: {k: v for k, v in b.items() if k != "params"} | {"params": b["params"]}
                     for s, b in selected.items()},
        "search_log": search_log,
        "scored": len(records), "failed": len(failures), "failures": failures,
        "backbone_calls": raw_calls,
        "raw_call_dumps": "removed after the run; predictions.npz is the retained artefact",
        "records": records,
        "official": {"commit": identity["commit"]},
        "runtime_seconds": time.perf_counter() - began,
    })
    print(json.dumps({"backbone": args.backbone, "block": args.block,
                      "scored": len(records), "failed": len(failures),
                      "runtime_seconds": time.perf_counter() - began}, indent=1))


if __name__ == "__main__":
    main()
