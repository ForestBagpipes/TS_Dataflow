"""Multivariate downstream evaluation, channel independent.

What this delivers, stated without inflation because the temptation runs the
other way. It makes the evaluation setting defensible: training pairs come from
aligned positions rather than from unrelated positions in unrelated channels,
and error is reported over multivariate blocks rather than over isolated
windows. Those are real differences and the paper may state them.

**It does not change the model.** Channel independent modelling means each
channel is unrolled separately and all channels share one set of weights, which
is what the existing univariate evaluation already did. The tensors here carry
a channel axis so the interface matches the standard multivariate setting, and
the axis is folded into the batch before any parameter sees it. No number should
be expected to move because of this file.

**It does not raise the fraction of the corpus that curation touched**, which is
the reason the downstream effects for the conservative methods sit inside the
noise floor. An earlier expectation that a multivariate evaluation would surface
those effects is withdrawn. This file is not a response to that problem.

Kept separate from `downstream.py` so every result already in the repository
remains reproducible by the code that produced it.
"""

import numpy as np

CONTEXT_LEN = 96
HORIZON = 32
STRIDE = 8
MIN_CONTEXT_SPREAD = 1e-6


def _instance_norm_mv(ctx, tgt):
    """Normalise per channel, using statistics from the context only.

    ctx is (L, C) and tgt is (H, C). Each channel gets its own centre and scale,
    which is required rather than optional here: the seven ETT channels differ
    in units and in magnitude, and a shared scale would let the largest channel
    dominate the loss.
    """
    mu = ctx.mean(axis=0, keepdims=True)
    sd = ctx.std(axis=0, keepdims=True)
    sd = np.where(sd < 1e-12, 1.0, sd)
    return (ctx - mu) / sd, (tgt - mu) / sd


def make_pairs_mv(blocks, context_len=CONTEXT_LEN, horizon=HORIZON,
                  stride=STRIDE):
    """Slide over multivariate blocks to build (N, C, L) and (N, C, H).

    Blocks may differ in channel count, since the corpus builder shuffles its
    pool and most positions contribute some of their channels rather than all.
    Pairs are therefore grouped by channel count and returned as a list of
    arrays, one per width, plus a flat view for models that do not care.
    """
    need = context_len + horizon
    by_width = {}
    dropped = 0
    for b in blocks:
        b = np.asarray(b, dtype=np.float64)
        if b.ndim != 2 or len(b) < need:
            continue
        C = b.shape[1]
        for start in range(0, len(b) - need + 1, stride):
            ctx = b[start:start + context_len]
            tgt = b[start + context_len:start + need]
            if not (np.isfinite(ctx).all() and np.isfinite(tgt).all()):
                continue
            floor = MIN_CONTEXT_SPREAD * max(float(np.std(b)), 1e-12)
            if float(np.min(np.std(ctx, axis=0))) <= floor:
                dropped += 1
                continue
            cn, tn = _instance_norm_mv(ctx, tgt)
            d = by_width.setdefault(C, ([], []))
            d[0].append(cn.T)
            d[1].append(tn.T)
    out = {C: (np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64))
           for C, (x, y) in by_width.items()}
    return out, dropped


def flatten_channels(pairs_by_width):
    """Fold the channel axis into the batch, which is what the models consume.

    This is the operational content of channel independence. (N, C, L) becomes
    (N*C, L), so a block of four aligned channels contributes four training
    pairs that share weights with every other channel in the corpus.
    """
    X, Y, owner = [], [], []
    for C, (x, y) in sorted(pairs_by_width.items()):
        if len(x) == 0:
            continue
        n = len(x)
        X.append(x.reshape(n * C, x.shape[2]))
        Y.append(y.reshape(n * C, y.shape[2]))
        owner.append(np.repeat(np.arange(n), C))
    if not X:
        return np.zeros((0, CONTEXT_LEN)), np.zeros((0, HORIZON)), np.zeros(0, int)
    return np.vstack(X), np.vstack(Y), np.concatenate(owner)


def block_report(blocks):
    """Channel count distribution, which has to be reported alongside results.

    A reader told only that the evaluation is multivariate will assume seven
    channels throughout. It is not, and the distribution is part of the setting.
    """
    from collections import Counter
    widths = [b.shape[1] for b in blocks]
    c = Counter(widths)
    return {
        "n_blocks": len(blocks),
        "total_channel_series": int(sum(widths)),
        "channels_per_block": dict(sorted(c.items())),
        "median_channels": float(np.median(widths)) if widths else float("nan"),
        "min_channels": int(min(widths)) if widths else 0,
        "max_channels": int(max(widths)) if widths else 0,
    }


def evaluate_mv(blocks, pristine_blocks, train_idx, test_idx, models):
    """Train on curated blocks, score against pristine blocks.

    Same protocol as the univariate evaluation. The split is over blocks and is
    made before curation, the training data is whatever a method produced, and
    the test target is always the pristine series.
    """
    tr = [blocks[i] for i in train_idx if i < len(blocks)]
    te = [pristine_blocks[i] for i in test_idx if i < len(pristine_blocks)]
    ptr, dropped = make_pairs_mv(tr)
    pte, _ = make_pairs_mv(te)
    X_tr, Y_tr, _ = flatten_channels(ptr)
    X_te, Y_te, owner_te = flatten_channels(pte)
    if len(X_tr) < 32 or len(X_te) < 8:
        return {"error": f"too few pairs (train={len(X_tr)}, test={len(X_te)})"}

    out = {"n_train_pairs": int(len(X_tr)), "n_test_pairs": int(len(X_te)),
           "n_train_pairs_dropped": int(dropped),
           "train_blocks": len(tr), "test_blocks": len(te)}
    for model in models:
        model.horizon = Y_tr.shape[1]
        model.fit(X_tr, Y_tr)
        pred = model.predict(X_te)
        err = (pred - Y_te) ** 2
        # Per pair error, then averaged over blocks so that a block with seven
        # channels does not count seven times as much as one with three.
        per_pair = err.mean(axis=1)
        per_block = np.zeros(owner_te.max() + 1) if len(owner_te) else np.zeros(0)
        counts = np.zeros_like(per_block)
        np.add.at(per_block, owner_te, per_pair)
        np.add.at(counts, owner_te, 1.0)
        block_mse = float(np.mean(per_block / np.maximum(counts, 1)))
        out[model.name] = {
            "mse": float(err.mean()),
            "mae": float(np.abs(pred - Y_te).mean()),
            "block_mse": block_mse,
        }
    return out
