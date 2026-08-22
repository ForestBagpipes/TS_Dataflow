"""Score the corpus with the three valuation baselines, in their own environment.

Runs in the `dataval` environment, which pins `opendataval` and its numpy and
sklearn versions against the curation environment's. It reads the npz written by
`valuation_export.py` and writes per window scores, so nothing from this
environment is imported by the agent.

Every hyperparameter below is the one the source paper published, taken from
`scoring/baseline_annotate.py` in `clsr1008/TSRating`, which implements all four
on one fetcher with one utility model. Using their configuration rather than our
reading of the methods is the decision `docs/valuation_family_protocol.md`
records, and it is what makes the four comparable to each other as well as to us.

  Data-OOB       num_models 1000
  Data Shapley   gr_threshold 1.1, max_mc_epochs 100, min_models 100
  KNN Shapley    k_neighbors 0.1 times the training size
  TimeInf        mean influence of a training block over the validation blocks

TimeInf uses the influence of a training block averaged over validation blocks,
which is signed and ranks blocks by how much they help. Its own repository uses
self influence wrapped in an absolute deviation, which is the anomaly detection
reading and would score deviation rather than value. That trap is recorded in
the protocol and avoided here.

A window's score is the arithmetic mean of its block scores, never the sum,
because RESEGMENT produces windows of unequal length and a sum would rank a long
window above a short one for length alone.

Usage, in the dataval environment:
    python -u experiments/valuation_score.py --corpus data/valuation_corpus.npz
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "third_party" / "TimeInf"))

#: Published hyperparameters, see the module docstring for the source.
OOB_MODELS = 1000
SHAPLEY_GR = 1.1
SHAPLEY_MAX_EPOCHS = 100
SHAPLEY_MIN_MODELS = 100
KNN_K_FRACTION = 0.1


def check_environment():
    """Refuse to run outside the environment the protocol pins.

    `docs/environment_preflight.md` requires the launcher to assert the
    interpreter and the pinned versions before starting, because a score
    computed under different pins is not the score the protocol describes.
    """
    import sklearn
    import opendataval
    info = {"python": sys.version.split()[0], "numpy": np.__version__,
            "sklearn": sklearn.__version__,
            "opendataval": getattr(opendataval, "__version__", "unknown"),
            "executable": sys.executable}
    if not np.__version__.startswith("1."):
        raise SystemExit(
            f"numpy is {np.__version__}, opendataval pins the 1.x line, "
            f"this is not the dataval environment")
    return info


def timeinf_scores(Xtr, Ytr, Xva, Yva):
    """Mean influence of each training block over the validation blocks.

    The linear AR path is used, which is the one TSRating calls and which is
    58 lines of numpy. The heavier blackbox and transformer paths in that
    repository serve a different experiment.
    """
    from timeinf.linear_influence import calc_linear_time_inf
    from sklearn.linear_model import LinearRegression

    model = LinearRegression().fit(Xtr, Ytr)
    beta, b = model.coef_, model.intercept_
    # Hessian of the squared loss for a linear model, plus a ridge term so the
    # inverse exists when blocks are collinear.
    n, d = Xtr.shape
    hess = (Xtr.T @ Xtr) / n + 1e-6 * np.eye(d)
    inv_hess = np.linalg.inv(hess)
    params = (beta, b, inv_hess)

    n_val = Xva.shape[0]
    out = np.zeros(n, dtype=np.float64)
    for i in range(n):
        acc = 0.0
        for j in range(n_val):
            acc += calc_linear_time_inf(i, j, Xtr, Ytr, Xva, Yva, params)
        out[i] = acc / max(n_val, 1)
    return out


def opendataval_scores(Xtr, Ytr, Xva, Yva):
    """Data-OOB, Data Shapley and KNN Shapley, at their published settings."""
    from opendataval.dataval import DataOob, DataShapley, KNNShapley
    from opendataval.model import RegressionSkLearnWrapper
    from sklearn.linear_model import LinearRegression

    pred = RegressionSkLearnWrapper(LinearRegression)
    out = {}
    specs = [
        ("data_oob", DataOob(num_models=OOB_MODELS)),
        ("data_shapley", DataShapley(gr_threshold=SHAPLEY_GR,
                                     max_mc_epochs=SHAPLEY_MAX_EPOCHS,
                                     min_models=SHAPLEY_MIN_MODELS)),
        ("knn_shapley", KNNShapley(k_neighbors=max(1, int(KNN_K_FRACTION * len(Xtr))))),
    ]
    for name, dv in specs:
        t0 = time.time()
        dv.train(Xtr, Ytr, Xva, Yva, pred_model=pred)
        out[name] = {"scores": np.asarray(dv.data_values, dtype=np.float64),
                     "seconds": time.time() - t0}
        print(f"  {name} done in {out[name]['seconds']:.0f}s", flush=True)
    return out


def to_window_scores(block_scores, window_ids):
    """Arithmetic mean of a window's block scores. See the module docstring."""
    out = {}
    for wid in np.unique(window_ids):
        out[int(wid)] = float(np.mean(block_scores[window_ids == wid]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(ROOT / "data" / "valuation_corpus.npz"))
    ap.add_argument("--methods", nargs="+",
                    default=["timeinf", "data_oob", "data_shapley", "knn_shapley"])
    ap.add_argument("--out", default=str(ROOT / "results" / "valuation_scores.json"))
    args = ap.parse_args()

    env = check_environment()
    for k, v in env.items():
        print(f"{k}: {v}")

    z = np.load(args.corpus, allow_pickle=True)
    X, Y, wid, part = z["X"], z["Y"], z["window_id"], z["partition"]
    tr, va = part == 0, part == 1
    print(f"{X.shape[0]} blocks, {tr.sum()} train, {va.sum()} validation, "
          f"{(part == 2).sum()} test, {len(np.unique(wid))} windows", flush=True)

    report = {"environment": env, "corpus": str(args.corpus),
              "n_blocks": int(X.shape[0]), "methods": {}}

    if "timeinf" in args.methods:
        t0 = time.time()
        s = timeinf_scores(X[tr], Y[tr], X[va], Y[va])
        report["methods"]["timeinf"] = {
            "seconds": time.time() - t0,
            "window_scores": to_window_scores(s, wid[tr]),
        }
        print(f"  timeinf done in {time.time()-t0:.0f}s", flush=True)

    wanted = [m for m in args.methods if m != "timeinf"]
    if wanted:
        res = opendataval_scores(X[tr], Y[tr], X[va], Y[va])
        for name, v in res.items():
            if name not in wanted:
                continue
            report["methods"][name] = {
                "seconds": v["seconds"],
                "window_scores": to_window_scores(v["scores"], wid[tr]),
            }

    for name, v in report["methods"].items():
        vals = np.array(list(v["window_scores"].values()))
        print(f"{name:14s} {len(vals):5d} windows scored, "
              f"mean {vals.mean():+.6f}, sd {vals.std():.6f}, "
              f"{v['seconds']:.0f}s")

    Path(args.out).write_text(json.dumps(report, indent=1, default=float),
                              encoding="utf-8")
    print("___VALUATION_SCORE_DONE___", flush=True)


if __name__ == "__main__":
    main()
