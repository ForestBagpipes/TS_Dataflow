"""Chronos-Bolt only; Chronos-2 requires its own validated implementation."""
import numpy as np
from ..schemas import require
from .common import run_worker


def load(record):
    import torch
    from chronos import BaseChronosPipeline, ChronosBoltPipeline
    pipeline = BaseChronosPipeline.from_pretrained(record["snapshot_path"], device_map="cuda",
                                                  torch_dtype=torch.bfloat16, local_files_only=True)
    require(isinstance(pipeline, ChronosBoltPipeline), "wrong Chronos pipeline")
    require(all(p.device.type == "cuda" for p in pipeline.model.parameters()), "Bolt not on GPU")
    return pipeline


def predict(model, payload, request, row):
    import torch
    require(request["task"] == "forecast" and request["covariate_mode"] == "none", "unsupported Bolt task")
    x = torch.from_numpy(payload["target"].astype(np.float32))
    with torch.inference_mode():
        output = model.predict([x], request["horizon"])
    quantiles = model.model.config.chronos_config["quantiles"]
    require(tuple(output.shape) == (1, len(quantiles), request["horizon"]), "unexpected Bolt shape")
    require(quantiles.count(.5) == 1, "median quantile missing")
    raw = output.float().cpu().numpy()
    return raw[0, quantiles.index(.5)], raw


if __name__ == "__main__":
    run_worker("bolt", load, predict)
