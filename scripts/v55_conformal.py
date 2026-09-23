#!/usr/bin/env python3
"""v55 step 2: calibrate the execution threshold by conformal risk control.

The frozen ``(k, beta, lam)`` come from the replay bank, so the internal
evaluation block took no part in choosing them and can serve as the calibration
sample.  For each tolerance ``alpha`` the script reports the smallest threshold
whose calibrated harmful loss satisfies the conformal risk control condition,
together with the whole threshold ladder so a reader can see how the rule trades
intervention frequency for harm.

The bound assumes the calibration and deployment requests are exchangeable.
Time series requests are not exchangeable in general, so the guarantee is
nominal and the evaluation reports the harmful loss the threshold actually
produced on TEST next to the level it promised.

Writes ``results/v55/protocol/conformal_{backbone}.json``.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import state as ST
from introact_ts.v47 import select as SEL
from introact_ts.v55 import select as V55

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v54_common import ROOT, clean, code_hashes, load_catalogs, sha, write

OUT55 = ROOT / "results/v55"
PROTOCOL = OUT55 / "protocol"

#: Tolerated harmful loss, in MASE units averaged over all requests.  The three
#: levels are registered before the calibration runs and none of them is chosen
#: by looking at TEST.
ALPHA_GRID = (0.01, 0.02, 0.03, 0.05)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--bank-block", default="bankx")
    parser.add_argument("--calibration-block", default="train_eval")
    args = parser.parse_args()

    began = time.perf_counter()
    root = Path(args.root)
    selection = json.loads(
        (OUT55 / "protocol" / f"selection_{args.backbone}.json").read_text())
    config = V55.frozen_config(selection)

    blocks = SEL.blocks_of()
    bank_catalogs = load_catalogs(root, args.bank_block, args.backbone)
    bank = SEL.Bank(bank_catalogs, blocks=blocks)
    cal_catalogs = load_catalogs(root, args.calibration_block, args.backbone)
    queries = SEL.Queries(cal_catalogs, blocks=blocks)

    payload = {
        "stage": "v55-conformal-calibration",
        "state_version": ST.STATE_VERSION,
        "backbone": args.backbone,
        "bank_block": args.bank_block,
        "calibration_block": args.calibration_block,
        "calibration_episodes": len(cal_catalogs),
        "calibration_parents": int(len({c.parent for c in cal_catalogs})),
        "harm_clip": V55.HARM_CLIP,
        "alpha_grid": list(ALPHA_GRID),
        "assumption": "conformal risk control bounds the expected harmful loss "
                      "of an exchangeable request; forecasting requests are not "
                      "exchangeable in general, so the level is nominal and the "
                      "evaluation reports the realised TEST harm beside it",
        "test_records_read": 0,
    }

    if config is None:
        payload["keep_only"] = True
        payload["levels"] = []
        payload["note"] = ("the harm cap admitted no configuration, so the rule "
                           "keeps every input and no threshold is needed")
    else:
        k, beta, lam = config
        D = SEL.distance_matrices(bank, queries, lopo=False)
        moments = V55.local_moments(bank, queries, D, k)
        means = V55.source_action_means(bank)
        scores = V55.scores_from_moments(moments, means, queries, beta, lam)
        base = V55.decide(queries, scores, threshold=0.0)
        base_harm = float(V55.harm_per_request(queries, base).mean())
        levels = []
        for alpha in ALPHA_GRID:
            result = V55.conformal_threshold(queries, scores, alpha)
            chosen = result["selected"]
            levels.append({
                "alpha": alpha,
                "threshold": ("inf" if np.isinf(chosen["threshold"])
                              else chosen["threshold"]),
                "calibration_harm": chosen["empirical_harm"],
                "crc_bound": chosen["crc_bound"],
                "calibration_intervention_rate": chosen["intervention_rate"],
                "note": chosen.get("note"),
            })
        first = V55.conformal_threshold(queries, scores, ALPHA_GRID[0])
        payload["keep_only"] = False
        payload["frozen"] = {"k": k, "beta": beta,
                             "lam": (None if np.isinf(lam) else lam),
                             "lam_is_inf": bool(np.isinf(lam))}
        payload["zero_threshold_calibration_harm"] = base_harm
        payload["zero_threshold_intervention_rate"] = float(
            (base != SEL.REFERENCE).mean())
        payload["levels"] = levels
        payload["ladder"] = first["ladder"][:200]

    payload["code_sha256"] = code_hashes(root) | {
        "scripts/v55_conformal.py": sha(Path(__file__).resolve()),
        "src/introact_ts/v55/select.py": sha(
            root / "src/introact_ts/v55/select.py")}
    payload["runtime_seconds"] = time.perf_counter() - began
    write(PROTOCOL / f"conformal_{args.backbone}.json", clean(payload))
    print(json.dumps(clean({"backbone": args.backbone,
                            "frozen": payload.get("frozen"),
                            "zero_threshold_harm":
                                payload.get("zero_threshold_calibration_harm"),
                            "levels": payload["levels"]}), indent=1))


if __name__ == "__main__":
    main()
