"""Downstream transfer: train on curated data, test on pristine data.

The zero-shot transfer metric asks whether another frozen model forecasts
better *from* a curated context. This asks the question data curation actually
exists to answer: if you train a model on what the agent produced, does it
learn the real signal better?

The protocol is deliberately unforgiving:

  * windows are split into train and test **before** curation, so no test
    window ever influences the model that is scored on it;
  * the training set is whatever a method produced -- repaired, rolled back, or
    left alone;
  * the test set is always the *pristine* series, identical for every method.

That last point is what makes the comparison meaningful. A pipeline that
smooths everything produces training data that predicts its own smoothed
future beautifully and the real one badly, and only a clean test target
exposes it.

Models are ordinary supervised forecasters, none of them a foundation model and
none of them consulted during curation:

  seasonal_naive  no parameters; the reference every method must beat
  ridge_ar        linear autoregression on the raw context
  dlinear         trend/seasonal decomposition, one linear map each
  patchtst        patch embedding + transformer encoder (optional, needs torch)
"""

import numpy as np

CONTEXT_LEN = 96
HORIZON = 32
#: Dense sampling matters here. A 96->32 linear map has ~3k parameters, and at
#: stride 32 a few hundred windows yield fewer training pairs than that -- the
#: model then loses to seasonal-naive for want of data, and the metric stops
#: telling you anything about the curation.
STRIDE = 8


#: A context whose spread has collapsed relative to its own series is not a
#: training example, it is a division by zero waiting to happen: the fallback
#: denominator leaves the target at raw scale, producing values orders of
#: magnitude larger than everything else and derailing gradient training. Such
#: pairs are dropped for every method alike. Aggressive smoothing produces most
#: of them, so dropping them is if anything generous to the pipelines that
#: flatten hardest.
MIN_CONTEXT_SPREAD = 1e-3


def _instance_norm(ctx: np.ndarray, tgt: np.ndarray) -> tuple:
    """Normalise a pair by the context statistics, as LTSF models do."""
    mu = float(np.mean(ctx))
    sd = float(np.std(ctx))
    if sd < 1e-8:
        sd = 1.0
    return (ctx - mu) / sd, (tgt - mu) / sd


def make_pairs(
    series_list: list,
    context_len: int = CONTEXT_LEN,
    horizon: int = HORIZON,
    stride: int = STRIDE,
) -> tuple:
    """Slide over each series to build (context, target) matrices."""
    X, Y, dropped = [], [], 0
    need = context_len + horizon
    for s in series_list:
        s = np.asarray(s, dtype=np.float64)
        s = s[np.isfinite(s)] if not np.isfinite(s).all() else s
        if len(s) < need:
            continue
        floor = MIN_CONTEXT_SPREAD * max(float(np.std(s)), 1e-12)
        for start in range(0, len(s) - need + 1, stride):
            ctx = s[start : start + context_len]
            tgt = s[start + context_len : start + need]
            if not (np.isfinite(ctx).all() and np.isfinite(tgt).all()):
                continue
            if float(np.std(ctx)) <= floor:
                dropped += 1
                continue
            ctx_n, tgt_n = _instance_norm(ctx, tgt)
            X.append(ctx_n)
            Y.append(tgt_n)
    make_pairs.last_dropped = dropped
    if not X:
        return np.zeros((0, context_len)), np.zeros((0, horizon))
    return np.asarray(X, dtype=np.float64), np.asarray(Y, dtype=np.float64)


# -- models -----------------------------------------------------------------


class SeasonalNaive:
    """Repeat the last period.

    Having no parameters, it never sees the training set, so its score is
    identical for every curation method. It is reported as a difficulty
    reference for the test split, not as a comparison between methods --
    listing it alongside the trained models would suggest ten methods tied.
    """

    name = "seasonal_naive"
    trainable = False

    def __init__(self, period: int = 24):
        self.period = period

    def fit(self, X, Y):
        return self

    def predict(self, X):
        H = self.horizon
        tail = X[:, -self.period :]
        reps = int(np.ceil(H / self.period))
        return np.tile(tail, (1, reps))[:, :H]


#: Ridge strengths searched on a held-out slice of the *training* pairs. The
#: right amount of regularisation depends on how much usable data a curation
#: method left behind, so fixing it would quietly favour whichever method
#: happened to suit the constant.
ALPHA_GRID = (0.1, 1.0, 10.0, 100.0, 1000.0)


def _fit_ridge_cv(F: np.ndarray, Y: np.ndarray, alphas=ALPHA_GRID, val_frac=0.2):
    """Closed-form ridge with alpha chosen on a held-out tail of the training set."""
    n = len(F)
    n_val = max(8, int(val_frac * n))
    if n - n_val < F.shape[1] // 2:
        n_val = max(4, n // 5)
    F_tr, Y_tr = F[: n - n_val], Y[: n - n_val]
    F_va, Y_va = F[n - n_val :], Y[n - n_val :]

    best, best_err = None, np.inf
    gram_base = F_tr.T @ F_tr
    rhs = F_tr.T @ Y_tr
    eye = np.eye(F.shape[1])
    for alpha in alphas:
        try:
            W = np.linalg.solve(gram_base + alpha * eye, rhs)
        except np.linalg.LinAlgError:
            continue
        err = float(np.mean((F_va @ W - Y_va) ** 2))
        if err < best_err:
            best, best_err = alpha, err
    alpha = best if best is not None else alphas[-1]
    # Refit on everything once the strength is settled.
    W = np.linalg.solve(F.T @ F + alpha * eye, F.T @ Y)
    return W, alpha


class RidgeAR:
    """Linear autoregression, solved in closed form."""

    name = "ridge_ar"
    trainable = True

    def __init__(self):
        self.W = None
        self.alpha = None

    def fit(self, X, Y):
        F = np.column_stack([X, np.ones(len(X))])
        self.W, self.alpha = _fit_ridge_cv(F, Y)
        return self

    def predict(self, X):
        return np.column_stack([X, np.ones(len(X))]) @ self.W


class DLinear:
    """Decomposition-linear: a moving-average trend plus its residual.

    Each component gets its own linear map to the horizon, which is exactly
    the original formulation -- and because both maps are linear, they are
    fitted in closed form rather than by gradient descent.
    """

    name = "dlinear"
    trainable = True

    def __init__(self, kernel: int = 25):
        self.kernel = kernel | 1
        self.W = None
        self.alpha = None

    def _decompose(self, X):
        k = min(self.kernel, X.shape[1] - 1 if X.shape[1] % 2 == 0 else X.shape[1])
        k = max(3, k | 1)
        pad = k // 2
        padded = np.pad(X, ((0, 0), (pad, pad)), mode="edge")
        kernel = np.ones(k) / k
        trend = np.apply_along_axis(
            lambda r: np.convolve(r, kernel, mode="valid"), 1, padded
        )[:, : X.shape[1]]
        return trend, X - trend

    def fit(self, X, Y):
        trend, seasonal = self._decompose(X)
        F = np.column_stack([trend, seasonal, np.ones(len(X))])
        self.W, self.alpha = _fit_ridge_cv(F, Y)
        return self

    def predict(self, X):
        trend, seasonal = self._decompose(X)
        return np.column_stack([trend, seasonal, np.ones(len(X))]) @ self.W


class PatchTST:
    """Patch embedding + transformer encoder + flatten head.

    Optional: needs torch. Kept small (2 layers, 64 dims) because it is trained
    from scratch once per curation method, and the comparison is between
    training sets rather than between architectures.
    """

    name = "patchtst"
    trainable = True

    def __init__(
        self,
        patch_len: int = 16,
        stride: int = 8,
        d_model: int = 64,
        n_heads: int = 4,
        n_layers: int = 2,
        epochs: int = 30,
        batch_size: int = 128,
        lr: float = 1e-3,
        seed: int = 0,
        n_repeats: int = 3,
    ):
        self.cfg = dict(
            patch_len=patch_len, stride=stride, d_model=d_model, n_heads=n_heads,
            n_layers=n_layers, epochs=epochs, batch_size=batch_size, lr=lr, seed=seed,
        )
        self.n_repeats = int(n_repeats)
        self.models = []

    def _build(self, context_len: int, horizon: int):
        import torch
        import torch.nn as nn

        c = self.cfg
        torch.manual_seed(c["seed"])
        n_patches = (context_len - c["patch_len"]) // c["stride"] + 1

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.embed = nn.Linear(c["patch_len"], c["d_model"])
                self.pos = nn.Parameter(torch.zeros(1, n_patches, c["d_model"]))
                layer = nn.TransformerEncoderLayer(
                    d_model=c["d_model"], nhead=c["n_heads"],
                    dim_feedforward=2 * c["d_model"], batch_first=True,
                    dropout=0.0,
                )
                self.enc = nn.TransformerEncoder(layer, num_layers=c["n_layers"])
                self.head = nn.Linear(n_patches * c["d_model"], horizon)

            def forward(self, x):
                patches = x.unfold(1, c["patch_len"], c["stride"])
                h = self.embed(patches) + self.pos
                h = self.enc(h)
                return self.head(h.flatten(1))

        return Net()

    def fit(self, X, Y):  # pragma: no cover - exercised only with torch present
        import torch

        xt = torch.tensor(X, dtype=torch.float32)
        yt = torch.tensor(Y, dtype=torch.float32)
        n, bs = len(xt), self.cfg["batch_size"]
        base_seed = self.cfg["seed"]

        self.models = []
        for rep in range(self.n_repeats):
            seed = base_seed + 1000 * rep
            self.cfg["seed"] = seed
            model = self._build(X.shape[1], Y.shape[1])
            opt = torch.optim.Adam(model.parameters(), lr=self.cfg["lr"])
            gen = torch.Generator().manual_seed(seed)
            model.train()
            for _ in range(self.cfg["epochs"]):
                perm = torch.randperm(n, generator=gen)
                for i in range(0, n, bs):
                    idx = perm[i : i + bs]
                    opt.zero_grad()
                    loss = torch.nn.functional.mse_loss(model(xt[idx]), yt[idx])
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    opt.step()
            model.eval()
            self.models.append(model)
        self.cfg["seed"] = base_seed
        return self

    def predict(self, X):  # pragma: no cover
        """Mean prediction over the repeats, so one unlucky init cannot decide."""
        import torch

        xt = torch.tensor(X, dtype=torch.float32)
        with torch.no_grad():
            preds = [m(xt).numpy() for m in self.models]
        return np.mean(preds, axis=0)


def make_models(include_deep: bool = False, seed: int = 0) -> list:
    models = [SeasonalNaive(), RidgeAR(), DLinear()]
    if include_deep:
        try:
            import torch  # noqa: F401

            models.append(PatchTST(seed=seed))
        except ImportError:
            print("  [skip] patchtst: torch not available")
    return models


# -- protocol ---------------------------------------------------------------


def split_windows(windows: list, train_frac: float = 0.7, seed: int = 42) -> tuple:
    """Partition window ids into train and test, once, before any curation."""
    ids = np.asarray([w.window_id for w in windows])
    rng = np.random.RandomState(seed)
    order = rng.permutation(len(ids))
    cut = int(train_frac * len(ids))
    return set(ids[order[:cut]].tolist()), set(ids[order[cut:]].tolist())


def evaluate(
    traces: list,
    windows: list,
    train_ids: set,
    test_ids: set,
    include_deep: bool = False,
    seed: int = 42,
) -> dict:
    """Train on this method's curated output, score against pristine futures."""
    byid = {w.window_id: w for w in windows}

    train_series = [t.final_series for t in traces if t.window_id in train_ids]
    test_series = [
        byid[t.window_id].clean_series
        for t in traces
        if t.window_id in test_ids and byid[t.window_id].clean_series is not None
    ]

    X_tr, Y_tr = make_pairs(train_series)
    dropped = getattr(make_pairs, "last_dropped", 0)
    X_te, Y_te = make_pairs(test_series)
    if len(X_tr) < 32 or len(X_te) < 8:
        return {"error": f"too few pairs (train={len(X_tr)}, test={len(X_te)})"}

    out = {
        "n_train_pairs": int(len(X_tr)),
        "n_test_pairs": int(len(X_te)),
        "n_train_pairs_dropped": int(dropped),
    }
    for model in make_models(include_deep=include_deep, seed=seed):
        model.horizon = Y_tr.shape[1]
        model.fit(X_tr, Y_tr)
        pred = model.predict(X_te)
        out[model.name] = {
            "mse": float(np.mean((pred - Y_te) ** 2)),
            "mae": float(np.mean(np.abs(pred - Y_te))),
            "trainable": bool(getattr(model, "trainable", True)),
        }
    return out


def compare(results: dict, reference: str = "no_action") -> dict:
    """Express each method's downstream error relative to the untouched corpus."""
    ref = results.get(reference, {})
    rel = {}
    for method, scores in results.items():
        if "error" in scores:
            rel[method] = scores
            continue
        entry = {}
        for model, v in scores.items():
            if not isinstance(v, dict) or model not in ref or "mse" not in ref.get(model, {}):
                continue
            base = ref[model]["mse"]
            entry[model] = {
                "mse": v["mse"],
                "improvement": 1.0 - v["mse"] / max(base, 1e-12),
            }
        rel[method] = entry
    return rel
