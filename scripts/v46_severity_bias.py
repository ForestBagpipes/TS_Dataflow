#!/usr/bin/env python3
"""Does the bank's severity mixture bias what the local estimate expects?

The replay bank draws one severity per historical episode from the registered
ladder, so it contains 10, 30 and 50 per cent episodes.  The main comparison
runs at 10 per cent.  If an action's realised utility depends strongly on
severity, the utility an unrestricted neighbourhood reports for a 10 per cent
request is pulled toward the harsher episodes, and the conservative rule then
abstains more often than the evidence at 10 per cent would justify.

This script measures that directly: the mean realised utility of every action
on the bank as a whole and on its 10 per cent episodes alone.  It selects
nothing and changes no configuration.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v44 import protocol as P

ROOT = Path(__file__).resolve().parent.parent
C.REPLAY = "results/v46/replay"
OUT = ROOT / "results/v46/diagnostics"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backbone", default="bolt")
    args = parser.parse_args()

    began = time.perf_counter()
    catalogs = C.load_catalog(ROOT, "bank", args.backbone)
    severities = sorted({round(c.severity, 2) for c in catalogs})
    table = {}
    for action in P.ACTIONS:
        row = {}
        for level in [None] + severities:
            values = [c.actions[action].utility for c in catalogs
                      if (level is None or round(c.severity, 2) == level)
                      and c.actions.get(action) is not None
                      and c.actions[action].utility is not None]
            key = "all" if level is None else f"s{int(level * 100):02d}"
            row[key] = {"mean": float(np.mean(values)) if values else None,
                        "positive_rate": float(np.mean(np.asarray(values) > 0)) if values else None,
                        "n": len(values)}
        table[action] = row

    payload = {"stage": "v46-severity-bias", "backbone": args.backbone,
               "bank_episodes": len(catalogs), "severities": severities,
               "utility_by_severity": table,
               "runtime_seconds": time.perf_counter() - began}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"severity_bias_{args.backbone}.json").write_text(
        json.dumps(payload, indent=1) + "\n")
    for action, row in table.items():
        print(action, {k: (None if v["mean"] is None else round(v["mean"], 4))
                       for k, v in row.items()})


if __name__ == "__main__":
    main()
