#!/usr/bin/env python3
"""Four-fold parent OOF SAITS; context-only inputs and auditable source shards."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v47_verified"
CONFIG = dict(n_layers=2, d_model=128, n_heads=4, d_k=32, d_v=32,
              d_ffn=128, dropout=0.1, epochs=100, batch_size=16, patience=10)
FOLDS = 4
MAX_CHANNELS = 64
SEED = 101


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
    os.replace(tmp, path)


def atomic_npz(path, arrays):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with tmp.open("wb") as handle:
        np.savez(handle, **arrays)
    os.replace(tmp, path)


def channel_subset(train_panels, cap=MAX_CHANNELS):
    """Select channels from this fold's training contexts only."""
    panel = np.concatenate(train_panels, axis=0)
    if panel.shape[1] <= cap:
        return np.arange(panel.shape[1])
    target = panel[:, 0]
    scores = []
    for c in range(1, panel.shape[1]):
        ok = np.isfinite(target) & np.isfinite(panel[:, c])
        if ok.sum() < 16:
            scores.append(0.0)
            continue
        a = target[ok] - target[ok].mean()
        b = panel[ok, c] - panel[ok, c].mean()
        denominator = float(np.sqrt((a @ a) * (b @ b)))
        scores.append(abs(float(a @ b / denominator)) if denominator > 1e-12 else 0.0)
    order = np.argsort(-np.asarray(scores), kind="stable")[:cap - 1] + 1
    return np.concatenate(([0], np.sort(order)))


def fit_and_impute(train_panels, query_panels, epochs, seed, artifact_dir):
    """One model fit; every requested block shares that fitted model."""
    import torch
    from pypots.imputation import SAITS

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    columns = channel_subset(train_panels)
    raw = np.stack([p[:, columns] for p in train_panels]).astype(np.float64)
    flat = raw.reshape(-1, raw.shape[2])
    centre = np.nanmean(flat, axis=0)
    scale = np.nanstd(flat, axis=0)
    centre = np.where(np.isfinite(centre), centre, 0.0)
    scale = np.where(np.isfinite(scale) & (scale > 1e-8), scale, 1.0)
    x = ((raw - centre) / scale).astype(np.float32)
    model = SAITS(n_steps=x.shape[1], n_features=x.shape[2], epochs=epochs,
                  device="cuda", **{k: (min(v, epochs) if k == "patience" else v) for k, v in CONFIG.items() if k != "epochs"})
    model.fit({"X": x})
    artifact_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = artifact_dir / "model.pypots"
    if checkpoint.exists():
        raise RuntimeError(f"Existing uncommitted checkpoint preserved: {checkpoint}")
    model.save(str(checkpoint))
    atomic_npz(artifact_dir / "preprocessing.npz", {"columns": columns, "centre": centre, "scale": scale})
    import importlib.metadata
    atomic_json(artifact_dir / "identity.json", {"checkpoint_sha256": digest(checkpoint),
                "pypots": importlib.metadata.version("pypots"), "seed": seed,
                "epochs": epochs, "patience": min(CONFIG["patience"], epochs)})
    query = np.stack([p[:, columns] for p in query_panels]).astype(np.float64)
    y = ((query - centre) / scale).astype(np.float32)
    prediction = np.asarray(model.impute({"X": y}), dtype=np.float64)
    if prediction.shape != y.shape:
        raise RuntimeError(f"SAITS output shape {prediction.shape} != {y.shape}")
    prediction = prediction * scale + centre
    repaired = []
    for original_panel, output in zip(query_panels, prediction):
        original = np.asarray(original_panel[:, 0], dtype=np.float64)
        hidden = ~np.isfinite(original)
        value = original.copy()
        value[hidden] = output[:, 0][hidden]
        if not np.isfinite(value).all():
            raise RuntimeError("SAITS returned a non-finite repaired target")
        if not np.array_equal(value[~hidden], original[~hidden]):
            raise RuntimeError("SAITS changed an observed target")
        repaired.append(value)
    del model
    torch.cuda.empty_cache()
    return repaired, columns.tolist()


def rows_hash(rows):
    h = hashlib.sha256()
    for episode, parent, panel in rows:
        h.update(json.dumps([episode, parent, panel.shape]).encode())
        h.update(np.ascontiguousarray(panel, dtype=np.float64).tobytes())
    return h.hexdigest()


def collect(root, specs):
    from introact_ts.v47_verified import grid as G
    rows = []
    for spec, _raw, masked in G.iter_contexts(root, specs):
        rows.append((spec.episode_id, spec.parent,
                     np.asarray(masked, dtype=np.float64).copy()))
    if len(rows) != len(specs) or len({e for e, _, _ in rows}) != len(rows):
        raise RuntimeError("Missing or duplicate context episodes")
    return rows


def process_source(source, blocks, specs, args, output, code_hashes):
    fit_rows = collect(ROOT, specs["bankx"])
    if not fit_rows:
        raise RuntimeError(f"No training contexts for {source}")
    block_rows = {b: (fit_rows if b == "bankx" else collect(ROOT, specs[b]))
                  for b in blocks}
    if any(not rows for rows in block_rows.values()):
        raise RuntimeError(f"Empty query block for {source}")
    ordered = sorted({(s.read_start, s.parent) for s in specs["bankx"]})
    folds = {parent: i % FOLDS for i, (_, parent) in enumerate(ordered)}
    if args.mode == "crossfit" and set(folds.values()) != set(range(FOLDS)):
        raise RuntimeError(f"{source} needs at least four bank parents")
    for block, rows in block_rows.items():
        query_parents = {p for _, p, _ in rows}
        if args.mode == "crossfit" and query_parents != set(folds):
            raise RuntimeError(f"{source}/{block} parent set differs from fit bank")
        if args.mode == "full" and query_parents & set(folds):
            raise RuntimeError(f"{source}/{block} overlaps full-fit bank parents")
    identity = dict(source=source, mode=args.mode, blocks=blocks,
                    config={**CONFIG, "epochs": args.epochs, "patience": min(CONFIG["patience"], args.epochs)}, seed=SEED,
                    folds=FOLDS, max_channels=MAX_CHANNELS,
                    parent_limit=args.pilot_parents, code_hashes=code_hashes,
                    fold_assignment=folds, training_input_hash=rows_hash(fit_rows),
                    query_input_hashes={b: rows_hash(r) for b, r in block_rows.items()})
    source_dir = output / "sources" / source / args.mode
    manifest = source_dir / "manifest.json"
    if manifest.exists():
        saved = json.loads(manifest.read_text())
        if saved["identity"] != identity:
            raise RuntimeError(f"Refusing incompatible existing shard: {manifest}")
        for b, checksum in saved["archive_hashes"].items():
            path = source_dir / f"{b}.npz"
            if not path.exists() or digest(path) != checksum:
                raise RuntimeError(f"Corrupt or missing shard: {path}")
        return saved
    # Partial files without a committed manifest are not reused.
    arrays = {b: {} for b in blocks}
    fits = []
    started = time.perf_counter()
    for fold in (range(FOLDS) if args.mode == "crossfit" else [None]):
        train = [r for r in fit_rows if fold is None or folds[r[1]] != fold]
        queries = [(b, e, p, x) for b, rows in block_rows.items() for e, p, x in rows
                   if fold is None or folds[p] == fold]
        if not train or not queries:
            raise RuntimeError(f"Empty training/query fold for {source}/{fold}")
        train_parents = sorted({p for _, p, _ in train})
        query_parents = sorted({p for _, _, p, _ in queries})
        if set(train_parents) & set(query_parents):
            raise RuntimeError("Training/query parent leakage")
        seed = SEED + (fold if fold is not None else FOLDS)
        values, columns = fit_and_impute([r[2] for r in train],
                                         [q[3] for q in queries], args.epochs, seed,
                                         source_dir / f"fold_{fold}")
        for (block, episode, _parent, _panel), value in zip(queries, values):
            arrays[block][f"{episode}|SAITS"] = value
        fits.append(dict(fold=fold, seed=seed, columns=columns,
                         training_parents=train_parents, query_parents=query_parents,
                         training_episodes=len(train), query_episodes=len(queries)))
    hashes = {}
    for block, values in arrays.items():
        if len(values) != len(block_rows[block]):
            raise RuntimeError(f"Incomplete output {source}/{block}")
        path = source_dir / f"{block}.npz"
        atomic_npz(path, values)
        hashes[block] = digest(path)
    result = dict(identity=identity, fits=fits, archive_hashes=hashes,
                  episodes={b: len(v) for b, v in arrays.items()},
                  context_only=True, future_labels_read=0,
                  runtime_seconds=time.perf_counter() - started)
    atomic_json(manifest, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["crossfit", "full"], default="crossfit")
    parser.add_argument("--blocks", default="")
    parser.add_argument("--sources", default="")
    parser.add_argument("--epochs", type=int, default=CONFIG["epochs"])
    parser.add_argument("--pilot-parents", type=int, default=None)
    parser.add_argument("--output-root", type=Path, default=OUT)
    args = parser.parse_args()
    from introact_ts.v47_verified import grid as G
    from introact_ts.v47_verified import protocol as P
    blocks = [b.strip() for b in (args.blocks or (
        "bankx,bankx2" if args.mode == "crossfit" else "train_eval")).split(",")]
    allowed = {"bankx", "bankx2"} if args.mode == "crossfit" else {"train_eval"}
    if not blocks or len(set(blocks)) != len(blocks) or not set(blocks) <= allowed:
        parser.error("Only bankx/bankx2 crossfit or train_eval full mode is permitted")
    run_root = args.output_root.resolve()
    output = run_root / "replay/saits"
    if (args.pilot_parents is not None or args.epochs != CONFIG["epochs"]) and run_root == OUT.resolve():
        parser.error("Pilot/modified-epoch runs require a separate --output-root")
    if args.epochs <= 0 or (args.pilot_parents is not None and args.pilot_parents < FOLDS):
        parser.error("Invalid epochs or parent limit")
    sources = [s.strip() for s in args.sources.split(",") if s.strip()] or list(P.SOURCES)
    if len(set(sources)) != len(sources) or not set(sources) <= set(P.SOURCES):
        parser.error("Unknown or duplicate source")
    all_specs = {b: G.episode_specs(ROOT, b, parent_limit=args.pilot_parents)
                 for b in dict.fromkeys(["bankx"] + blocks)}
    code_hashes = {"saits": digest(__file__), "grid": digest(G.__file__),
                   "protocol": digest(P.__file__)}
    import fcntl
    import subprocess
    (ROOT / "locks").mkdir(exist_ok=True)
    with (ROOT / "locks/gpu.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        resources = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.free,utilization.gpu",
                                            "--format=csv,noheader,nounits"], text=True).strip()
        print(json.dumps({"gpu_resource_snapshot": resources}), flush=True)
        if int(resources.splitlines()[0].split(",")[0]) < 3072:
            raise RuntimeError("Less than 3072 MiB GPU memory is free")
        reports = {}
        for source in sources:
            specs = {b: [s for s in rows if s.source == source] for b, rows in all_specs.items()}
            reports[source] = process_source(source, blocks, specs, args, output, code_hashes)
            print(json.dumps({"source": source, "episodes": reports[source]["episodes"]}), flush=True)
        # Canonical block archives are emitted only for the complete source roster.
        if set(sources) == set(P.SOURCES):
            for block in blocks:
                merged = {}
                for source in sources:
                    with np.load(output / "sources" / source / args.mode / f"{block}.npz",
                                 allow_pickle=False) as archive:
                        for key in archive.files:
                            if key in merged:
                                raise RuntimeError(f"Duplicate archive key {key}")
                            merged[key] = archive[key]
                atomic_npz(output / f"{block}.npz", merged)
        atomic_json(output / f"report_{args.mode}.json", dict(
            sources=reports, blocks=blocks, complete_sources=set(sources) == set(P.SOURCES),
            future_labels_read=0, code_hashes=code_hashes))


if __name__ == "__main__":
    main()
