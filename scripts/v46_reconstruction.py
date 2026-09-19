#!/usr/bin/env python3
"""Reconstruction quality against realised forecasting utility, on the catalog.

The premise this supports is that a repair which recovers the hidden values
more accurately is not thereby the repair that helps the forecast more.  The
cleanest way to test it here is on the catalog itself: the four interventions
all produce an explicit estimate of the hidden positions, and their realised
forecasting utility is already recorded, so both rankings exist for the same
episodes under one protocol.

For every evaluation episode the script recomputes the raw context from the
source container, measures each action's reconstruction error on the positions
the mask hid, and compares the within-episode ranking of that error with the
within-episode ranking of realised utility.  Nothing here touches the decision
rule; it is a property of the catalog and the backbone.
"""

from __future__ import annotations

import argparse
import collections
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v44 import masking as M
from introact_ts.v44 import protocol as P
from introact_ts.v44 import registry as R
from introact_ts.v46 import grid as G

ROOT = Path(__file__).resolve().parent.parent
C.REPLAY = "results/v46/replay"
OUT = ROOT / "results/v46/diagnostics"
REPAIRS = ("FFILL", "SINGLE_TSICL", "MULTI_TSICL", "CONTEXT_RIDGE")
#: The published reconstruction baseline enters the same comparison when its
#: repaired inputs and its forecasts are both on disk, which is what makes the
#: two criteria comparable for it as well.
EXTERNAL = {"SAITS": ("saits", "SAITS")}


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def raw_targets(root: Path, block: str) -> dict[str, np.ndarray]:
    """Target-channel raw context of every parent in a block, keyed by parent."""
    registry = R.source_registry(root)
    parents = G.parents_of(root, block)
    out: dict[str, np.ndarray] = {}
    by_source: dict[str, list] = collections.defaultdict(list)
    for parent in parents:
        by_source[parent.source].append(parent)
    for source, windows in sorted(by_source.items()):
        info = registry[source]
        ordered = sorted(windows, key=lambda w: w.read_start)
        for window, context, _future in R.read_windows(
                root, info, ordered, horizon=min(P.HORIZONS)):
            out[window.parent] = context[:, 0].copy()
    return out


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return float("nan")
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    rx -= rx.mean()
    ry -= ry.mean()
    denom = float(np.sqrt((rx @ rx) * (ry @ ry)))
    return float(rx @ ry / denom) if denom > 1e-12 else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--block", default="test")
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    catalogs = C.load_catalog(root, args.block, args.backbone)
    raw = raw_targets(root, args.block)

    per_action = {a: {"rec_mse": [], "rec_mae": [], "utility": []} for a in REPAIRS}
    concordant = discordant = 0
    winner_agree = winner_total = 0
    rhos = []
    episodes = 0
    # Joint distribution of the two within-episode ranks, for Figure 3(a).
    rank_grid = np.zeros((len(REPAIRS), len(REPAIRS)), dtype=int)

    store = np.load(root / "results/v46/replay/inputs" / f"{args.block}.npz",
                    allow_pickle=False)
    tsicl = np.load(root / "results/v46/replay/tsicl" / f"{args.block}.npz",
                    allow_pickle=False)
    external_inputs, external_loss, names = {}, {}, list(REPAIRS)
    for label, (method, _tag) in EXTERNAL.items():
        cand = root / f"results/v46/baselines/{method}/candidates.npz"
        recs = root / f"results/v46/baselines/{method}_{args.block}_{args.backbone}/records.json"
        if cand.exists() and recs.exists():
            external_inputs[label] = np.load(cand, allow_pickle=False)
            external_loss[label] = json.loads(recs.read_text())["records"]
            names.append(label)
            per_action[label] = {"rec_mse": [], "rec_mae": [], "utility": []}
    rank_grid = np.zeros((len(names), len(names)), dtype=int)
    try:
        for cat in catalogs:
            truth = raw.get(cat.parent)
            if truth is None:
                continue
            mask = M.build_mask(cat.source, cat.parent, cat.origin, cat.horizon,
                                cat.pattern, cat.severity, length=len(truth),
                                n_channels=1 if truth.ndim == 1 else truth.shape[1])
            hidden = mask[:, 0] if mask.ndim == 2 else mask
            if not hidden.any():
                continue
            rec, util = {}, {}
            for action in REPAIRS:
                entry = cat.actions.get(action)
                if entry is None or not entry.scored or entry.utility is None:
                    continue
                name = f"{cat.episode}|{action}"
                values = (store[name] if name in store.files
                          else (tsicl[name] if name in tsicl.files else None))
                if values is None:
                    continue
                error = np.asarray(values, dtype=np.float64)[hidden] - truth[hidden]
                error = error[np.isfinite(error)]
                if error.size == 0:
                    continue
                rec[action] = (float(np.mean(error ** 2)), float(np.mean(np.abs(error))))
                util[action] = float(entry.utility)
                per_action[action]["rec_mse"].append(rec[action][0])
                per_action[action]["rec_mae"].append(rec[action][1])
                per_action[action]["utility"].append(util[action])
            for label in external_inputs:
                name = f"{args.block}|{cat.episode}"
                item = external_loss[label].get(cat.episode)
                if name not in external_inputs[label].files or item is None:
                    continue
                if item.get("mase") is None or cat.reference_mase is None:
                    continue
                values = np.asarray(external_inputs[label][name], dtype=np.float64)
                error = values[hidden] - truth[hidden]
                error = error[np.isfinite(error)]
                if error.size == 0:
                    continue
                rec[label] = (float(np.mean(error ** 2)), float(np.mean(np.abs(error))))
                util[label] = float(cat.reference_mase - item["mase"])
                per_action[label]["rec_mse"].append(rec[label][0])
                per_action[label]["rec_mae"].append(rec[label][1])
                per_action[label]["utility"].append(util[label])
            if len(rec) < 2:
                continue
            episodes += 1
            actions = sorted(rec)
            r = np.array([rec[a][0] for a in actions])
            u = np.array([util[a] for a in actions])
            rhos.append(spearman(-r, u))
            if len(actions) == len(names):
                rec_rank = np.argsort(np.argsort(r))
                util_rank = np.argsort(np.argsort(-u))
                for a, b in zip(rec_rank, util_rank):
                    rank_grid[int(a), int(b)] += 1
            winner_total += 1
            if actions[int(np.argmin(r))] == actions[int(np.argmax(u))]:
                winner_agree += 1
            for i in range(len(actions)):
                for j in range(i + 1, len(actions)):
                    if abs(r[i] - r[j]) < 1e-12 or abs(u[i] - u[j]) < 1e-12:
                        continue
                    if (r[i] < r[j]) == (u[i] > u[j]):
                        concordant += 1
                    else:
                        discordant += 1
    finally:
        store.close()
        tsicl.close()
        for handle in external_inputs.values():
            handle.close()

    pairs = concordant + discordant
    payload = {
        "rank_grid": rank_grid.tolist(),
        "rank_grid_order": sorted(names),
        "stage": "v46-reconstruction-vs-utility",
        "backbone": args.backbone, "block": args.block,
        "episodes_compared": episodes,
        "winner_agreement": (winner_agree / winner_total) if winner_total else None,
        "discordant_rate": (discordant / pairs) if pairs else None,
        "pairs": pairs,
        "mean_within_episode_spearman": float(np.nanmean(rhos)) if rhos else None,
        "per_action": {
            a: {"rec_mse": float(np.mean(v["rec_mse"])) if v["rec_mse"] else None,
                "rec_mae": float(np.mean(v["rec_mae"])) if v["rec_mae"] else None,
                "mean_utility": float(np.mean(v["utility"])) if v["utility"] else None,
                "n": len(v["utility"])}
            for a, v in per_action.items()},
        "runtime_seconds": time.perf_counter() - began,
    }
    write(OUT / f"reconstruction_{args.block}_{args.backbone}.json", payload)
    print(json.dumps(payload, indent=1))


if __name__ == "__main__":
    main()
