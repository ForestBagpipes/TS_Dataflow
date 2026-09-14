"""Fixed official TS-ICL checkpoint, observed writes repaired at adapter boundary."""
import numpy as np
from ..schemas import require
from .common import run_worker


def load(record):
    import torch
    from tsicl import TSICL
    checkpoint = torch.load(record["checkpoint_path"], map_location="cpu", weights_only=True)
    require(all(k in checkpoint and len(checkpoint[k]) for k in ("config", "forecaster", "imputer")), "missing trained checkpoint component")
    del checkpoint
    model = TSICL(model_path=record["checkpoint_path"], allow_auto_download=False)
    model.forecaster.to("cuda").eval()
    model.imputer.to("cuda").eval()
    require(all(p.device.type == "cuda" for m in (model.forecaster, model.imputer) for p in m.parameters()), "TSICL not on GPU")
    return model


def predict(model, payload, request, row):
    import torch
    x = payload["target"]
    options = dict(batch_size=1, quantile_levels=[.1, .5, .9], device=torch.device("cuda"),
                   denormalize=True, point_estimator="median", squeeze_output=False)
    mode = request["covariate_mode"]
    require(mode in ("none", "past_only"), "unsupported covariate mode")
    if mode == "past_only":
        require(request["task"] == "impute", "forecast covariates not validated")
        options["covars"] = payload["covariates"][None].astype(np.float32)
    if request["task"] == "impute":
        point, quantiles = model.impute(x.astype(np.float32), replace_by_gt=True, **options)
    else:
        point, quantiles = model.forecast(x.astype(np.float32), prediction_length=request["horizon"], **options)
    require(tuple(point.shape) == (1, 1, row["output_length"], 1), "unexpected TSICL point shape")
    p = point.cpu().numpy().reshape(-1).astype(x.dtype)
    if request["task"] == "impute":
        require(p.shape == x.shape, "imputation time axis mismatch")
        # Official replace_by_gt is approximate after float32 normalization.
        # Governance identity is exact in original storage dtype and units.
        p[np.isfinite(x)] = x[np.isfinite(x)]
    return p, quantiles.cpu().numpy()


if __name__ == "__main__":
    run_worker("tsicl", load, predict)
