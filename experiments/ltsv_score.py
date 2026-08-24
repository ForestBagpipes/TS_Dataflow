"""LTSV, a value per window from a one step in context finetune on a frozen TSFM.

`arXiv:2511.11648v2`, DASFAA 2026. A block's value is the drop in a held out
context loss after one gradient step taken on that block:

    (9)  v(B) = L(D_ctx, theta) - L(D_ctx, theta - eta * grad_theta L(B, theta))
    (10) v(x_t) = mean over blocks containing x_t of v(B)
    (11) v(S)   = mean over points of v(x_t)

with eta 1e-5 and the context loss an MSE. Those are the paper's values.

The four things the paper leaves unspecified for this corpus are fixed in
`docs/ltsv_preregistration.md`, committed before this file was written: block
length 128 non overlapping, the MOMENT backbone alone, the context set as the
validation split of the 7:2:1 window split, and a per point loss average.

Two facts about the implementation are not decisions and each carries an
assertion, because both would corrupt the result silently rather than raise.

**The backbone must be unfrozen.** `MOMENTPipeline.init()` leaves the encoder
frozen, and the gradient then reaches two tensors of the reconstruction head,
under 0.05M elements out of 341M. Equation 2 differentiates with respect to the
model parameters.

**The context loss must be read in eval mode.** Gradients need train mode, where
dropout makes the loss vary between two reads of identical parameters. Measured
on the node, an exact revert returned 1.0472 against 1.0591 after the step, a
difference the size of the effect being measured.

Usage:
    python -u experiments/ltsv_score.py --corpus data/valuation_corpus.npz
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

#: The paper's values.
ETA = 1e-5
BLOCK_LEN = 128

#: MOMENT's fixed input length, which is also this corpus's window length.
SEQ_LEN = 512

#: A gradient reaching fewer parameters than this means the body is still
#: frozen and only the reconstruction head is moving. Measured: frozen gives
#: under 0.05M, unfrozen gives about 341M.
MIN_GRAD_PARAMS = 10_000_000

#: Two eval mode reads of unchanged parameters must agree to this. Dropout in
#: train mode moved the same read by about 0.012, so anything near that is a
#: regression to train mode rather than numerical noise.
EVAL_DETERMINISM_TOL = 1e-6


def build_model(device, model_name="AutonLab/MOMENT-1-large"):
    import torch
    from momentfm import MOMENTPipeline

    model = MOMENTPipeline.from_pretrained(
        model_name, model_kwargs={"task_name": "reconstruction"})
    model.init()
    model.to(device)

    # Assertion one. Equation 2 is a gradient with respect to theta, so the body
    # has to participate. `init()` leaves it frozen.
    for p in model.parameters():
        p.requires_grad_(True)
    n_grad = sum(p.numel() for p in model.parameters() if p.requires_grad)
    if n_grad < MIN_GRAD_PARAMS:
        raise SystemExit(
            f"only {n_grad} parameters carry a gradient, the backbone is still "
            f"frozen and equation 2 would be taken over the head alone")
    return model, torch, n_grad


def context_loss(model, torch, ctx, ctx_mask):
    """MSE over all points of the context set, read in eval mode.

    Assertion two lives at the call site: the caller reads this twice on
    unchanged parameters and compares, so a regression to train mode is caught
    rather than quietly returning dropout noise.
    """
    was_training = model.training
    model.eval()
    try:
        with torch.no_grad():
            total, count = 0.0, 0
            for i in range(0, ctx.shape[0], 8):
                x = ctx[i:i + 8]
                m = ctx_mask[i:i + 8]
                out = model(x_enc=x, input_mask=m)
                # Per point, not per window. See decision four.
                total += float(((out.reconstruction - x) ** 2).sum())
                count += int(x.numel())
        return total / max(count, 1)
    finally:
        if was_training:
            model.train()


def block_value(model, torch, block, blk_mask, ctx, ctx_mask, base_loss):
    """Equation 9 for one block, with the step applied then exactly reverted."""
    model.train()
    model.zero_grad(set_to_none=True)
    out = model(x_enc=block, input_mask=blk_mask)
    loss = ((out.reconstruction - block) ** 2).mean()
    loss.backward()

    touched = [p for p in model.parameters() if p.grad is not None]
    snapshot = [p.detach().clone() for p in touched]
    with torch.no_grad():
        for p in touched:
            p.add_(p.grad, alpha=-ETA)
    after = context_loss(model, torch, ctx, ctx_mask)
    with torch.no_grad():
        for p, s in zip(touched, snapshot):
            p.copy_(s)
    model.zero_grad(set_to_none=True)
    return base_loss - after


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(ROOT / "data" / "valuation_corpus.npz"))
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--context-windows", dest="n_ctx", type=int, default=32,
                    help="validation windows forming the context set")
    ap.add_argument("--limit-windows", dest="limit", type=int, default=None,
                    help="score only this many training windows, for a smoke run")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(ROOT / "results" / "ltsv_scores.json"))
    ap.add_argument("--checkpoint-every", dest="ckpt_every", type=int, default=200,
                    help="blocks between partial writes, see the resume note")
    ap.add_argument("--fresh", action="store_true",
                    help="ignore any partial result and recompute everything")
    args = ap.parse_args()

    z = np.load(args.corpus, allow_pickle=True)
    X, Y, wid, part = z["X"], z["Y"], z["window_id"], z["partition"]
    # The exported blocks are (127 features, 1 target). LTSV reconstructs, so the
    # block is put back together as its 128 points.
    blocks = np.concatenate([X, Y[:, None]], axis=1)
    tr, va = part == 0, part == 1
    print(f"{blocks.shape[0]} blocks, {tr.sum()} train, {va.sum()} validation",
          flush=True)

    model, torch, n_grad = build_model(args.device)
    print(f"{n_grad/1e6:.1f}M parameters carry a gradient", flush=True)

    def to_tensor(arr):
        # MOMENT takes a fixed 512 point input. A 128 point block is placed at
        # the start and the remainder is masked out, which is the padding path
        # `backends/moment.py` already documents.
        n = arr.shape[0]
        x = np.zeros((n, 1, SEQ_LEN), dtype=np.float32)
        m = np.zeros((n, SEQ_LEN), dtype=np.float32)
        x[:, 0, :arr.shape[1]] = arr
        m[:, :arr.shape[1]] = 1.0
        return (torch.tensor(x, device=args.device),
                torch.tensor(m, device=args.device))

    rng = np.random.RandomState(args.seed)
    va_idx = np.flatnonzero(va)
    take = min(args.n_ctx * (SEQ_LEN // BLOCK_LEN), len(va_idx))
    ctx_idx = rng.choice(va_idx, size=take, replace=False)
    ctx, ctx_mask = to_tensor(blocks[ctx_idx])

    base = context_loss(model, torch, ctx, ctx_mask)
    again = context_loss(model, torch, ctx, ctx_mask)
    if abs(base - again) > EVAL_DETERMINISM_TOL:
        raise SystemExit(
            f"two eval reads of unchanged parameters differ by {abs(base-again):.3e}, "
            f"the loss is not deterministic and equation 9 would return noise")
    print(f"context set {ctx.shape[0]} blocks, base loss {base:.6f}, "
          f"deterministic to {abs(base-again):.2e}", flush=True)

    tr_idx = np.flatnonzero(tr)
    if args.limit:
        keep = set(np.unique(wid[tr])[:args.limit].tolist())
        tr_idx = np.array([i for i in tr_idx if wid[i] in keep])
    print(f"scoring {len(tr_idx)} training blocks over "
          f"{len(np.unique(wid[tr_idx]))} windows", flush=True)

    # Resume. At about 350 ms a block a full pass is half an hour, so an
    # interruption without a checkpoint costs the whole run. Partial values are
    # written every `--checkpoint-every` blocks, keyed by block index, and a
    # restart picks up from the first index that has no value. The context set is
    # rebuilt identically from the same seed, so a resumed run computes the same
    # numbers as an uninterrupted one.
    ckpt_path = Path(args.out).with_suffix(".partial.json")
    done = {}
    if ckpt_path.exists() and not args.fresh:
        blob = json.loads(ckpt_path.read_text(encoding="utf-8"))
        if (blob.get("base_context_loss") == base
                and blob.get("n_blocks_total") == len(tr_idx)):
            done = {int(k): float(v) for k, v in blob["values"].items()}
            print(f"resuming from {len(done)} of {len(tr_idx)} blocks",
                  flush=True)
        else:
            print("checkpoint does not match this corpus, starting over",
                  flush=True)

    values = np.zeros(len(tr_idx), dtype=np.float64)
    for k, v in done.items():
        if k < len(values):
            values[k] = v

    def write_ckpt(upto):
        ckpt_path.write_text(json.dumps({
            "base_context_loss": base, "n_blocks_total": int(len(tr_idx)),
            "values": {str(k): float(values[k]) for k in range(upto)},
        }, default=float), encoding="utf-8")

    t0 = time.time()
    start_at = len(done)
    for k in range(start_at, len(tr_idx)):
        i = tr_idx[k]
        b, bm = to_tensor(blocks[i:i + 1])
        values[k] = block_value(model, torch, b, bm, ctx, ctx_mask, base)
        if (k + 1) % args.ckpt_every == 0:
            write_ckpt(k + 1)
        if (k + 1) % 50 == 0:
            el = time.time() - t0
            n = k + 1 - start_at
            print(f"  {k+1}/{len(tr_idx)} blocks, {el:.0f}s, "
                  f"{el/max(n,1)*1000:.0f} ms per block", flush=True)
    write_ckpt(len(tr_idx))

    win = {}
    for w in np.unique(wid[tr_idx]):
        win[int(w)] = float(np.mean(values[wid[tr_idx] == w]))

    report = {
        "method": "ltsv", "eta": ETA, "block_len": BLOCK_LEN,
        "backbone": "AutonLab/MOMENT-1-large",
        "grad_parameters": int(n_grad),
        "context_blocks": int(ctx.shape[0]),
        "base_context_loss": base,
        "eval_determinism": abs(base - again),
        "n_blocks_scored": int(len(tr_idx)),
        "seconds": time.time() - t0,
        "window_scores": win,
    }
    vals = np.array(list(win.values()))
    print(f"\n{len(win)} windows scored, mean {vals.mean():+.3e}, "
          f"sd {vals.std():.3e}, {report['seconds']:.0f}s")
    Path(args.out).write_text(json.dumps(report, indent=1, default=float),
                              encoding="utf-8")
    if ckpt_path.exists():
        ckpt_path.unlink()
    print("___LTSV_SCORE_DONE___", flush=True)


if __name__ == "__main__":
    main()
