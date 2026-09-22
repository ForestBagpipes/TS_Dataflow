"""BRITS and CSDI as catalog actions, on the exact protocol of v47_saits.py.

The pipeline mirrors ``scripts/v47_saits.py`` line for line: bank records are
cross-fitted over two parent folds (a window is imputed only by a model that
never saw its own parent), evaluation blocks are imputed by the model fitted
on the whole bank, one repaired target channel per episode is spliced back
against the observation mask, and only finite repairs are written.  The
plausibility guard is not applied at write time (downstream scoring marks a
repair that leaves the plausible range as unsupported, as it does for SAITS),
but every repair is checked here and the unsupported counts are reported, so
the guard statistics are comparable across imputers.

Outputs go to ``results/v54/replay/external/<method>/<block>.npz`` under the
key ``<episode>|<METHOD>``; v47 scripts and artifacts are not touched.
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

#: Frozen before any run.  Both imputers sit at the same capacity tier as the
#: frozen SAITS action (n_layers=2, d_model=128, epochs=100, batch_size=16,
#: patience=10): BRITS gets rnn_hidden_size=128, CSDI gets two layers of width
#: 128 with matching embedding widths.  The diffusion schedule and the number
#: of posterior samples stay at the PyPOTS 1.5 defaults (n_diffusion_steps=50,
#: target_strategy="random", n_sampling_times=1), because no hyperparameter of
#: an external baseline may be tuned on this benchmark.
CONFIGS = {
    "BRITS": dict(rnn_hidden_size=128, epochs=100, batch_size=16, patience=10),
    "CSDI": dict(n_layers=2, n_heads=4, n_channels=128, d_time_embedding=128,
                 d_feature_embedding=128, d_diffusion_embedding=128,
                 n_diffusion_steps=50, target_strategy="random",
                 epochs=100, batch_size=16, patience=10),
}

#: Same protocol constants as v47_saits.py.
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


def fit_and_impute(method: str, train_panels, query_panels, epochs: int):
    """Fit one imputer on ``train_panels`` and impute ``query_panels``."""
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
    Y_raw = np.stack(query_panels)
    Y = ((Y_raw - centre) / scale).astype(np.float32)
    imputed = np.asarray(model.impute({"X": Y}), dtype=np.float64)
    if imputed.ndim == 4:
        # CSDI returns (n, n_sampling_times, n_steps, n_features); the
        # point estimate is the median over the sampling axis, as in the
        # original paper.
        imputed = np.median(imputed, axis=1)
    imputed = imputed * scale + centre
    del model, X, raw
    return Y_raw, imputed


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
        # The guard is recorded, not enforced: downstream scoring marks the
        # repair unsupported, exactly as it does for the SAITS archive.
        reason = A.implausible_reason(repaired, original)
        if reason is not None:
            failures["implausible"] += 1
        arrays[f"{episode}|{method}"] = repaired
        written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", required=True,
                        choices=sorted(CONFIGS), help="external imputer")
    parser.add_argument("--mode", default="crossfit", choices=["crossfit", "full"])
    parser.add_argument("--blocks", default="",
                        help="blocks to impute; defaults depend on the mode")
    parser.add_argument("--sources", default="")
    parser.add_argument("--epochs", type=int, default=0,
                        help="defaults to the frozen configuration")
    parser.add_argument("--tag", default="",
                        help="shard name; shards write their own archive")
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

    arrays: dict[str, dict[str, np.ndarray]] = {b: {} for b in blocks}
    report: dict[str, dict] = {}
    failures = collections.Counter()

    free_mib = int(subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        text=True).strip().splitlines()[0])
    if free_mib < MIN_FREE_MIB:
        raise RuntimeError(f"only {free_mib} MiB of GPU memory is free")
    torch.manual_seed(101)
    np.random.seed(101)

    def flush() -> None:
        out.mkdir(parents=True, exist_ok=True)
        for block, payload in arrays.items():
            if not payload:
                continue
            path = out / (f"{block}__{args.tag}.npz" if args.tag
                          else f"{block}.npz")
            with path.open("wb") as handle:
                np.savez(handle, **payload)

    for source in sources:
        tick = time.perf_counter()
        try:
            columns, fit_rows = collect(ROOT, FIT_BLOCK, source, None)
            if not fit_rows:
                report[source] = {"status": "no fit windows"}
                failures["no_fit_windows"] += 1
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
                        method, train, [q[2] for q in queries],
                        config["epochs"])
                    per_block[FIT_BLOCK] += splice(
                        method, Y_raw, imputed, queries,
                        arrays[FIT_BLOCK], failures)
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
                        method, train, [r[2] for r in rows], config["epochs"])
                    per_block[block] = splice(
                        method, Y_raw, imputed, rows, arrays[block], failures)
                    torch.cuda.empty_cache()
                report[source] = {
                    "status": "ok", "mode": "full",
                    "fit_windows": len(fit_rows),
                    "channels_used": int(len(columns)),
                    "episodes": per_block,
                    "total_seconds": time.perf_counter() - tick,
                }
        except Exception as exc:  # a failed source must not sink the rest
            report[source] = {"status": f"failed: {type(exc).__name__}: {exc}"}
            failures[f"exception:{type(exc).__name__}"] += 1
        print(json.dumps({source: report[source]}), flush=True)
        flush()

    flush()
    written = {}
    for block in blocks:
        path = out / (f"{block}__{args.tag}.npz" if args.tag
                      else f"{block}.npz")
        if path.exists():
            with np.load(path, allow_pickle=False) as store:
                written[path.name] = len(store.files)

    shard = f"-{args.tag}" if args.tag else ""
    run_record = {
        "mode": args.mode,
        "blocks": blocks,
        "sources": sources,
        "per_source": report,
        "failures": dict(sorted(failures.items())),
        "arrays": written,
        "runtime_seconds": time.perf_counter() - began,
    }
    write(out / f"report_{args.mode}{shard}.json", {
        "stage": "v54-external-imputers",
        "method": method,
        "config": config,
        "config_sha256": config_sha,
        "fit_block": FIT_BLOCK,
        "folds": FOLDS,
        "max_channels": MAX_CHANNELS,
        "standardisation": "per source and channel, statistics from the fit panels only",
        "heldout_labels_read": 0,
        **run_record,
    })
    status_path = out / "status.json"
    status = {}
    if status_path.exists():
        status = json.loads(status_path.read_text())
    status.update({
        "stage": "v54-external-imputers",
        "method": method,
        "config": config,
        "config_sha256": config_sha,
        "fit_block": FIT_BLOCK,
        "folds": FOLDS,
        "max_channels": MAX_CHANNELS,
        "heldout_labels_read": 0,
    })
    status.setdefault("runs", {})[f"{args.mode}{shard}"] = run_record
    write(status_path, status)
    print(json.dumps({"arrays": written, "failures": dict(failures),
                      "runtime_seconds": time.perf_counter() - began},
                     indent=1))


if __name__ == "__main__":
    main()
