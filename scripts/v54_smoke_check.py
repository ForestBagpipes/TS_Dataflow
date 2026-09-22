#!/usr/bin/env python3
"""Smoke-check a v54 external-imputer archive against the SAITS archive.

For every episode the repaired channel must equal the observed target at every
observed position (bitwise), be finite at every hidden position, and its
plausibility-guard failures are counted next to SAITS's on the same episodes.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", required=True)
    parser.add_argument("--block", default="test")
    parser.add_argument("--tag", default="smoke")
    parser.add_argument("--source", default="ETTh1")
    args = parser.parse_args()

    from introact_ts.v44 import actions as A

    inputs = np.load(ROOT / f"results/v47/replay/inputs/{args.block}.npz")
    saits = np.load(ROOT / f"results/v47/replay/saits/{args.block}.npz")
    mine_path = ROOT / (f"results/v54/replay/external/{args.method.lower()}/"
                        f"{args.block}__{args.tag}.npz")
    mine = np.load(mine_path, allow_pickle=False)

    episodes = sorted({k.rsplit("|", 1)[0] for k in inputs.files
                       if k.endswith("|KEEP") and k.startswith(args.source + "|")})
    report = {"episodes": len(episodes), "observed_mismatch": [],
              "hidden_non_finite": [], "keys_missing_in_saits": 0,
              "unsupported": collections.Counter()}
    for episode in episodes:
        keep = inputs[f"{episode}|KEEP"]
        key = f"{episode}|{args.method.upper()}"
        repaired = mine[key]
        observed = np.isfinite(keep)
        if not np.array_equal(repaired[observed], keep[observed]):
            report["observed_mismatch"].append(episode)
        if not np.isfinite(repaired[~observed]).all():
            report["hidden_non_finite"].append(episode)
        if A.implausible_reason(repaired, keep) is not None:
            report["unsupported"][args.method.upper()] += 1
        skey = f"{episode}|SAITS"
        if skey not in saits.files:
            report["keys_missing_in_saits"] += 1
        elif A.implausible_reason(saits[skey], keep) is not None:
            report["unsupported"]["SAITS"] += 1
    report["unsupported"] = dict(report["unsupported"])
    report["ok"] = (not report["observed_mismatch"]
                    and not report["hidden_non_finite"])
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
