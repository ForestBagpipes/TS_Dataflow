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
import hashlib
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


def opendataval_scores(Xtr, Ytr, Xva, Yva, wanted=None):
    """Data-OOB, Data Shapley and KNN Shapley, at their published settings.

    Yields `(name, scores, seconds)` as each finishes rather than returning them
    together, so the caller can persist one before the next starts.

    **Only the requested methods are built.** Data Shapley is not a row of the
    frozen matrix, `docs/valuation_family_protocol.md` keeps it out because it is
    the same game theoretic family as Data-OOB at an order of magnitude more
    cost, and running it by default once cost forty minutes of a machine that was
    needed elsewhere.
    """
    from opendataval.dataval import DataOob, DataShapley, KNNShapley
    from opendataval.model import RegressionSkLearnWrapper
    from sklearn.linear_model import LinearRegression

    from opendataval.dataloader import DataFetcher

    # `train` takes a DataFetcher rather than raw arrays in this version, so the
    # three splits are handed over through the fetcher's own from_data_splits
    # entry point. This is the same object TSRating's baseline file builds, so
    # the four methods still see one fetcher between them.
    fetcher = DataFetcher.from_data_splits(
        x_train=Xtr, y_train=Ytr[:, None],
        x_valid=Xva, y_valid=Yva[:, None],
        x_test=Xva, y_test=Yva[:, None],
        one_hot=False,
    )
    pred = RegressionSkLearnWrapper(LinearRegression)
    builders = {
        "data_oob": lambda: DataOob(num_models=OOB_MODELS),
        "data_shapley": lambda: DataShapley(gr_threshold=SHAPLEY_GR,
                                            max_mc_epochs=SHAPLEY_MAX_EPOCHS,
                                            min_models=SHAPLEY_MIN_MODELS),
        "knn_shapley": lambda: KNNShapley(
            k_neighbors=max(1, int(KNN_K_FRACTION * len(Xtr)))),
    }
    for name in (wanted if wanted is not None else builders):
        if name not in builders:
            continue
        t0 = time.time()
        dv = builders[name]()
        dv.train(fetcher, pred_model=pred)
        secs = time.time() - t0
        print(f"  {name} done in {secs:.0f}s", flush=True)
        yield name, np.asarray(dv.data_values, dtype=np.float64), secs


def to_window_scores(block_scores, window_ids):
    """Arithmetic mean of a window's block scores. See the module docstring."""
    out = {}
    for wid in np.unique(window_ids):
        out[int(wid)] = float(np.mean(block_scores[window_ids == wid]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(ROOT / "data" / "valuation_corpus.npz"))
    #: The frozen matrix's valuation rows are L4 Data-OOB and L5 TimeInf, plus
    #: L6 LTSV which has its own script. Data Shapley and KNN Shapley are not
    #: rows and are not computed unless asked for by name.
    ap.add_argument("--methods", nargs="+", default=["timeinf", "data_oob"])
    ap.add_argument("--out", default=str(ROOT / "results" / "valuation_scores.json"))
    ap.add_argument("--fresh", action="store_true",
                    help="ignore any partial result and recompute everything")
    args = ap.parse_args()

    env = check_environment()
    for k, v in env.items():
        print(f"{k}: {v}")

    z = np.load(args.corpus, allow_pickle=True)
    X, Y, wid, part = z["X"], z["Y"], z["window_id"], z["partition"]
    tr, va = part == 0, part == 1
    print(f"{X.shape[0]} blocks, {tr.sum()} train, {va.sum()} validation, "
          f"{(part == 2).sum()} test, {len(np.unique(wid))} windows", flush=True)

    # Resume. Each method writes as soon as it finishes, so a run that is
    # interrupted, or a machine that is shut down, loses only the method that
    # was in flight. The corpus fingerprint is stored with the results and a
    # mismatch discards them, since a partial file computed on another corpus is
    # worse than no file.
    fingerprint = hashlib.sha256(
        np.ascontiguousarray(X[:64]).tobytes()
        + np.ascontiguousarray(wid).tobytes()).hexdigest()[:16]
    out_path = Path(args.out)
    report = {"environment": env, "corpus": str(args.corpus),
              "corpus_fingerprint": fingerprint,
              "n_blocks": int(X.shape[0]), "methods": {}}
    if out_path.exists() and not args.fresh:
        old = json.loads(out_path.read_text(encoding="utf-8"))
        if old.get("corpus_fingerprint") == fingerprint:
            report["methods"] = old.get("methods", {})
            done = sorted(report["methods"])
            print(f"resuming, {len(done)} method(s) already computed: "
                  f"{', '.join(done) or 'none'}", flush=True)
        else:
            print("existing result is from a different corpus, discarding it",
                  flush=True)

    def flush():
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=1, default=float),
                            encoding="utf-8")

    if "timeinf" in args.methods and "timeinf" not in report["methods"]:
        t0 = time.time()
        s = timeinf_scores(X[tr], Y[tr], X[va], Y[va])
        report["methods"]["timeinf"] = {
            "seconds": time.time() - t0,
            "window_scores": to_window_scores(s, wid[tr]),
        }
        print(f"  timeinf done in {time.time()-t0:.0f}s", flush=True)
        flush()

    wanted = [m for m in args.methods
              if m != "timeinf" and m not in report["methods"]]
    if wanted:
        # The methods are handed the same fetcher one at a time, and each one is
        # written out before the next begins.
        for name, scores, secs in opendataval_scores(
                X[tr], Y[tr], X[va], Y[va], wanted):
            report["methods"][name] = {
                "seconds": secs,
                "window_scores": to_window_scores(scores, wid[tr]),
            }
            flush()

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
