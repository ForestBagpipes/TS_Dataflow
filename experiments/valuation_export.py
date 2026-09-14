"""Export the corpus in the shape the valuation baselines consume.

The three scoring baselines need `opendataval`, whose pins conflict with the
curation environment, so per `docs/valuation_family_protocol.md` they run in
their own environment and exchange files rather than imports. This script is the
producing half and runs in the main environment.

What it writes is fixed by that protocol and is not re-decided here:

  block length 128, non overlapping, so four blocks per 512 point window
  X is the first 127 points of a block, Y is the 128th
  the split is by window at 7:2:1, so no window contributes to both a model and
  its own valuation
  a window's score will be the arithmetic mean of its per position values, which
  is a decision about RESEGMENT's unequal window lengths rather than a preference

Usage:
    python -u experiments/valuation_export.py --scale xl --out data/valuation_corpus.npz
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402

#: Fixed in docs/valuation_family_protocol.md before any score existed.
BLOCK_LEN = 128
SPLIT = (0.7, 0.2, 0.1)
SPLIT_SEED = 20260818


def blocks_of(series: np.ndarray, blk: int = BLOCK_LEN):
    """Non overlapping blocks, dropping any tail shorter than one block."""
    x = np.asarray(series, dtype=np.float64)
    n = len(x) // blk
    if n == 0:
        return np.zeros((0, blk), dtype=np.float64)
    return x[: n * blk].reshape(n, blk)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="xl", choices=list(SCALES))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--source", default="ett")
    ap.add_argument("--out", default=str(ROOT / "data" / "valuation_corpus.npz"))
    args = ap.parse_args()

    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = build_corpus(spec, source=args.source)

    X, Y, wid, blk_idx = [], [], [], []
    kept, dropped = 0, 0
    for w in windows:
        b = blocks_of(w.series)
        if b.shape[0] == 0 or not np.isfinite(b).all():
            # A window carrying an injected gap has NaNs. The valuation family
            # cannot consume those and imputing them here would give it a
            # different corpus from the one the cleaning family sees, so the
            # block is dropped and the count is reported.
            dropped += 1
            continue
        kept += 1
        for k in range(b.shape[0]):
            X.append(b[k, :-1])
            Y.append(b[k, -1])
            wid.append(w.window_id)
            blk_idx.append(k)

    X = np.asarray(X, dtype=np.float64)
    Y = np.asarray(Y, dtype=np.float64)
    wid = np.asarray(wid, dtype=np.int64)

    # Split by window, drawn once from the pre registered seed.
    ids = np.array(sorted({int(w.window_id) for w in windows}))
    rng = np.random.RandomState(SPLIT_SEED)
    order = rng.permutation(len(ids))
    n_tr = int(round(SPLIT[0] * len(ids)))
    n_va = int(round(SPLIT[1] * len(ids)))
    train_ids = set(ids[order[:n_tr]].tolist())
    val_ids = set(ids[order[n_tr:n_tr + n_va]].tolist())
    part = np.array([0 if w in train_ids else 1 if w in val_ids else 2
                     for w in wid], dtype=np.int8)

    meta = {
        "scale": args.scale, "seed": args.seed, "source": args.source,
        "block_len": BLOCK_LEN, "split": list(SPLIT), "split_seed": SPLIT_SEED,
        "n_windows": len(windows), "windows_with_blocks": kept,
        "windows_dropped_non_finite": dropped,
        "n_blocks": int(X.shape[0]),
        "blocks_train": int((part == 0).sum()),
        "blocks_val": int((part == 1).sum()),
        "blocks_test": int((part == 2).sum()),
        "strata": {s: int(sum(1 for w in windows if w.stratum == s))
                   for s in sorted({w.stratum for w in windows})},
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, X=X, Y=Y, window_id=wid,
                        block_index=np.asarray(blk_idx, dtype=np.int32),
                        partition=part,
                        stratum=np.array([w.stratum for w in windows], dtype=object),
                        stratum_window_id=np.array([w.window_id for w in windows],
                                                   dtype=np.int64))
    (out.parent / (out.stem + "_meta.json")).write_text(
        json.dumps(meta, indent=1), encoding="utf-8")
    for k, v in meta.items():
        print(f"{k}: {v}")
    print("___VALUATION_EXPORT_DONE___", flush=True)


if __name__ == "__main__":
    main()
