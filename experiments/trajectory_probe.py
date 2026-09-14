"""Do training dynamics separate a mis perceived window from a contaminated one.

Every static signal has been tried and none of them works. Structural
distortion, utility gain and decision risk all fail to separate a protected
window the perception layer mislabelled from a genuinely contaminated one, and
on two families the risk condition prefers the wrong ones. The perception
layer's own confidence fails a pre registered separation criterion at all
fourteen thresholds swept.

The reason is structural. The injected contaminations imitate the shape of real
anomalies and the protected strata are by construction the windows that look
anomalous while being real, so on any static snapshot the two classes intersect.

This asks a different question: not what a window looks like, but how it behaves
under learning pressure. An injected segment has no generative relationship with
the rest of its window, so a learner fitting it should show conflict, learning
it late, forgetting it, and disagreeing about it across seeds. A genuinely rare
window shares its generating process with the corpus and should be learned
slowly but stably.

**Whose dynamics.** Not the frozen foundation models. A proxy learner already in
the evaluation pipeline is trained on the corpus and its per window loss is
logged every epoch, which costs the logging and two extra seeds.

**The gate.** Combined AUROC of at least 0.80 separating mislabelled protected
windows from genuinely contaminated ones, five fold cross validated, with the
test fold excluded from feature selection and from any threshold choice. Between
0.65 and 0.80 the frozen model probing axis is added and it is measured once
more. Below 0.65 the v3 design is not built. Fixed before the run.

Usage:
    python -u experiments/trajectory_probe.py --device cuda --seeds 0,1,2
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from build_calibration import build as build_calibration  # noqa: E402
from downstream import CONTEXT_LEN, HORIZON, STRIDE, _instance_norm  # noqa: E402

PROTECTED = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")


def window_pairs(windows, context_len=CONTEXT_LEN, horizon=HORIZON,
                 stride=STRIDE):
    """Samples plus the window each came from.

    `downstream.make_pairs` drops the provenance, and the whole probe is about
    provenance: a window's trajectory is the trajectory of the samples covering
    it. Built here rather than there so the evaluation path keeps its own
    function unchanged.
    """
    X, Y, owner = [], [], []
    need = context_len + horizon
    for w in windows:
        s = np.asarray(w.series, dtype=np.float64)
        s = s[np.isfinite(s)]
        if len(s) < need:
            continue
        for start in range(0, len(s) - need + 1, stride):
            ctx = s[start:start + context_len]
            tgt = s[start + context_len:start + need]
            if not (np.isfinite(ctx).all() and np.isfinite(tgt).all()):
                continue
            if float(np.std(ctx)) <= 1e-9:
                continue
            c, t = _instance_norm(ctx, tgt)
            X.append(c)
            Y.append(t)
            owner.append(int(w.window_id))
    if not X:
        return (np.zeros((0, context_len)), np.zeros((0, horizon)),
                np.zeros(0, dtype=np.int64))
    return (np.asarray(X, dtype=np.float64), np.asarray(Y, dtype=np.float64),
            np.asarray(owner, dtype=np.int64))


def train_and_log(X, Y, owner, seed, epochs, device, out_path, batch=128,
                  lr=1e-3):
    """Train once and append the per window loss after every epoch."""
    import torch

    torch.manual_seed(seed)
    dev = torch.device(device if torch.cuda.is_available() else "cpu")
    xt = torch.tensor(X, dtype=torch.float32, device=dev)
    yt = torch.tensor(Y, dtype=torch.float32, device=dev)
    ot = torch.tensor(owner, dtype=torch.long, device=dev)
    uniq = torch.unique(ot)
    index = {int(w): i for i, w in enumerate(uniq.tolist())}
    slot = torch.tensor([index[int(w)] for w in owner], dtype=torch.long,
                        device=dev)

    # The architecture the design document names. The first run used a three
    # layer MLP, which was faster and was not what had been registered, so its
    # AUROC described a model nobody had agreed to use. DLinear cannot serve
    # here at all: it is fitted in closed form and therefore has no epochs to
    # form a trajectory from.
    from downstream import PatchTST
    model = PatchTST(epochs=epochs, seed=seed)._build(
        X.shape[1], Y.shape[1]).to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    gen = torch.Generator(device="cpu").manual_seed(seed)
    n = len(xt)

    with out_path.open("a", encoding="utf-8") as fh:
        for ep in range(epochs):
            model.train()
            perm = torch.randperm(n, generator=gen).to(dev)
            for i in range(0, n, batch):
                idx = perm[i:i + batch]
                opt.zero_grad()
                loss = torch.nn.functional.mse_loss(model(xt[idx]), yt[idx])
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
            model.eval()
            with torch.no_grad():
                per = ((model(xt) - yt) ** 2).mean(dim=1)
                tot = torch.zeros(len(uniq), device=dev).index_add_(0, slot, per)
                cnt = torch.zeros(len(uniq), device=dev).index_add_(
                    0, slot, torch.ones_like(per))
                mean = (tot / cnt.clamp(min=1)).cpu().numpy()
            fh.write(json.dumps({
                "seed": int(seed), "epoch": int(ep),
                "loss": {str(int(w)): float(v)
                         for w, v in zip(uniq.tolist(), mean)}}) + chr(10))
            fh.flush()
    return True


def features(curves):
    """Six trajectory features per window. Thresholds fixed here, not tuned.

    The learning threshold is relative to the window's own range, the geometric
    midpoint between its first and last loss, so a window that is simply hard
    is not counted as never learned.
    """
    out = {}
    for wid, ls in curves.items():
        a = np.asarray(ls, dtype=np.float64)
        if a.size < 4 or not np.isfinite(a).all() or a.min() <= 0:
            continue
        lo, hi = float(a[-3:].mean()), float(a[0])
        mid = float(np.sqrt(max(lo, 1e-12) * max(hi, 1e-12)))
        learned = a < mid
        first = int(np.argmax(learned)) if learned.any() else len(a)
        flips = int(np.sum(learned[:-1] & ~learned[1:]))
        early = max(1, int(0.1 * len(a)))
        tail = max(2, int(0.2 * len(a)))
        x = np.arange(tail, dtype=np.float64)
        slope = float(np.polyfit(x, np.log(a[-tail:] + 1e-12), 1)[0])
        out[wid] = {
            "learn_speed": float(first) / len(a),
            "aulc": float(np.mean(np.log(a + 1e-12))),
            "forget_n": flips,
            "el2n_early": float(a[early - 1]),
            "tail_slope": slope,
            "final_loss": float(lo),
        }
    return out


def auroc(y, s):
    """Rank based AUROC, no sklearn dependency."""
    y = np.asarray(y, dtype=np.int64)
    s = np.asarray(s, dtype=np.float64)
    pos, neg = int(y.sum()), int((1 - y).sum())
    if pos == 0 or neg == 0:
        return float("nan")
    order = np.argsort(s)
    ranks = np.empty(len(s), dtype=np.float64)
    ranks[order] = np.arange(1, len(s) + 1)
    # Average ranks over ties.
    sv = s[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return float((ranks[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


def cv_auroc(F, y, folds=5, seed=0, groups=None):
    """Cross validated logistic regression AUROC, grouped when groups are given.

    The test fold takes no part in the scaling or the fit, which is the point of
    fixing the gate in advance. It also takes no part through a neighbour: with
    a random split, two windows cut from adjacent positions of one source series
    can land on opposite sides of the fold boundary, and the classifier then
    scores itself on data it has almost seen. Grouping by source dataset removes
    that channel. The first run did not group and its number is therefore an
    optimistic bound rather than an estimate.
    """
    rng = np.random.RandomState(seed)
    if groups is None:
        idx = rng.permutation(len(y))
        parts = np.array_split(idx, folds)
    else:
        g = np.asarray(groups)
        names = list(dict.fromkeys(g.tolist()))
        rng.shuffle(names)
        assign = {n: i % folds for i, n in enumerate(names)}
        parts = [np.where(np.array([assign[x] for x in g]) == k)[0]
                 for k in range(folds)]
        parts = [p for p in parts if len(p)]
    scores = np.zeros(len(y), dtype=np.float64)
    for k in range(len(parts)):
        te = parts[k]
        tr = np.concatenate([parts[j] for j in range(len(parts)) if j != k])
        if len(np.unique(y[tr])) < 2 or len(te) == 0:
            continue
        mu, sd = F[tr].mean(axis=0), F[tr].std(axis=0) + 1e-9
        A, B = (F[tr] - mu) / sd, (F[te] - mu) / sd
        w = np.zeros(A.shape[1])
        b = 0.0
        for _ in range(300):
            z = A @ w + b
            p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
            g = A.T @ (p - y[tr]) / len(tr) + 1e-3 * w
            gb = float(np.mean(p - y[tr]))
            w -= 0.5 * g
            b -= 0.5 * gb
        scores[te] = B @ w + b
    return auroc(y, scores)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1600)
    ap.add_argument("--corpus-seed", dest="corpus_seed", type=int, default=101)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--labels", default=str(ROOT / "results" / "confidence_split.json"))
    ap.add_argument("--curves", default=str(ROOT / "results" / "trajectory_probe" / "curves.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "results" / "trajectory_probe" / "probe.json"))
    args = ap.parse_args()

    seeds = [int(x) for x in args.seeds.replace(" ", "").split(",") if x]
    curves_path = Path(args.curves)
    curves_path.parent.mkdir(parents=True, exist_ok=True)

    windows, _ = build_calibration(n=args.n, seed=args.corpus_seed,
                                   source=args.source, verbose=True)
    X, Y, owner = window_pairs(windows)
    print(f"{len(X)} samples over {len(set(owner.tolist()))} windows", flush=True)

    done = set()
    if curves_path.exists():
        for line in curves_path.open(encoding="utf-8"):
            try:
                r = json.loads(line)
                done.add((r["seed"], r["epoch"]))
            except Exception:
                pass
        print(f"resuming, {len(done)} epochs already logged", flush=True)

    for s in seeds:
        if all((s, e) in done for e in range(args.epochs)):
            print(f"seed {s} already complete, skipped", flush=True)
            continue
        t0 = time.time()
        train_and_log(X, Y, owner, s, args.epochs, args.device, curves_path)
        print(f"seed {s} trained in {time.time() - t0:.0f}s", flush=True)

    # Assemble per seed curves.
    per_seed = defaultdict(lambda: defaultdict(list))
    for line in curves_path.open(encoding="utf-8"):
        r = json.loads(line)
        for wid, v in r["loss"].items():
            per_seed[r["seed"]][int(wid)].append((r["epoch"], v))
    feats = {}
    for s, curves in per_seed.items():
        ordered = {w: [v for _, v in sorted(pts)] for w, pts in curves.items()}
        feats[s] = features(ordered)

    common = set.intersection(*[set(f) for f in feats.values()]) if feats else set()
    print(f"{len(common)} windows with a complete trajectory in every seed")

    keys = ("learn_speed", "aulc", "forget_n", "el2n_early", "tail_slope",
            "final_loss")
    table = {}
    for wid in common:
        row = {}
        for k in keys:
            vals = [feats[s][wid][k] for s in feats]
            row[k] = float(np.mean(vals))
        row["seed_var"] = float(np.var([feats[s][wid]["final_loss"]
                                        for s in feats], ddof=0))
        table[wid] = row

    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    meta = {int(r["window_id"]): r for r in labels["rows"]}
    strata = {w: meta[w]["stratum"] for w in table if w in meta}
    hyp = {w: meta[w]["hypothesis"] for w in table if w in meta}
    dataset = {int(w.window_id): w.dataset for w in windows}

    print()
    print("trajectory signature by stratum, median")
    cols = keys + ("seed_var",)
    print(f"{'stratum':14s}{'n':>6s}" + "".join(f"{c[:11]:>13s}" for c in cols))
    sig = {}
    for st in sorted(set(strata.values())):
        ws = [w for w in table if strata.get(w) == st]
        if not ws:
            continue
        med = {c: float(np.median([table[w][c] for w in ws])) for c in cols}
        sig[st] = {"n": len(ws), **med}
        print(f"{st:14s}{len(ws):6d}" + "".join(f"{med[c]:13.4f}" for c in cols))

    # The gate: mislabelled protected windows against genuinely contaminated.
    pos = [w for w in table
           if strata.get(w) in PROTECTED and hyp.get(w) == "contaminated"]
    neg = [w for w in table if strata.get(w) == "contaminated"]
    print()
    print(f"gate set: {len(pos)} mislabelled protected, {len(neg)} contaminated")
    if len(pos) < 30 or len(neg) < 30:
        print("too few on one side to judge")
        return

    ids = pos + neg
    y = np.array([1] * len(pos) + [0] * len(neg), dtype=np.int64)
    F = np.array([[table[w][c] for c in cols] for w in ids], dtype=np.float64)

    print()
    print(f"{'feature':14s}{'AUROC':>9s}")
    singles = {}
    for i, c in enumerate(cols):
        a = auroc(y, F[:, i])
        singles[c] = a
        print(f"{c:14s}{a:9.4f}")
    G = [dataset.get(w, "unknown") for w in ids]
    combined_random = cv_auroc(F, y, folds=5, seed=0)
    combined = cv_auroc(F, y, folds=5, seed=0, groups=G)
    print(f"{'combined, random':14s}{combined_random:9.4f}  "
          f"(optimistic, neighbours leak across folds)")
    print(f"{'combined, grouped':14s}{combined:9.4f}  "
          f"(grouped by source dataset, this is the gate)")

    print()
    if combined >= 0.80:
        verdict = "green, trajectory features confirmed as v3 state features"
    elif combined >= 0.65:
        verdict = ("amber, add the frozen model probing axis and measure once "
                   "more")
    else:
        verdict = "red, do not build the v3 design on this signal"
    print(f"gate: combined AUROC {combined:.4f} -> {verdict}")

    # Second check, not a gate: is clean_ood separable from contaminated.
    pos2 = [w for w in table if strata.get(w) == "clean_ood"]
    if len(pos2) >= 30:
        ids2 = pos2 + neg
        y2 = np.array([1] * len(pos2) + [0] * len(neg), dtype=np.int64)
        F2 = np.array([[table[w][c] for c in cols] for w in ids2],
                      dtype=np.float64)
        G2 = [dataset.get(w, "unknown") for w in ids2]
        c2 = cv_auroc(F2, y2, folds=5, seed=0, groups=G2)
        print(f"clean_ood against contaminated, combined AUROC {c2:.4f} "
              f"(reported, not a gate)")
    else:
        c2 = None

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(
        {"n_windows": len(table), "seeds": seeds, "epochs": args.epochs,
         "signature_by_stratum": sig, "single_auroc": singles,
         "combined_auroc": combined,
         "combined_auroc_random_split": combined_random,
         "architecture": "PatchTST as registered",
         "cv": "grouped by source dataset",
         "verdict": verdict,
         "clean_ood_auroc": c2,
         "n_positive": len(pos), "n_negative": len(neg)},
        indent=1, default=float), encoding="utf-8")
    print()
    print("___TRAJECTORY_PROBE_DONE___", flush=True)


if __name__ == "__main__":
    main()
