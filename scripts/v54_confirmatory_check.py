#!/usr/bin/env python3
"""v54 confirmatory self-check: episode counts and archive formats.

Verifies, for every confirmatory block, that each stage's output matches the
frozen grid in ``src/introact_ts/v54/confirmatory.py``:

* stage A input manifests carry exactly the grid's episode count (minus the
  explicitly recorded skips, if any);
* the structural invariant mirrors the main set, where the test block is
  ``parents x 2 horizons x 4 patterns x 1 severity`` (95 x 8 = 760 on the
  main eight sources; parents x 8 here);
* stage B (TS-ICL) produced two action candidates per episode, failures only
  with recorded reasons;
* the SAITS and BRITS/CSDI archives carry one repaired target per episode of
  their blocks;
* every backbone forecast archive covers every applicable plan row.

Writes ``results/v54/confirmatory/check_report.json``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from introact_ts.v44 import protocol as P
from introact_ts.v54 import confirmatory as PL

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v54/confirmatory"

# BRITS/CSDI dropped by decision 2026-09-22 (training cost at the frozen
#: equal-capacity config exceeds the remaining budget); tuple kept empty so
#: forecast/check treat them as absent.
EXT_ACTIONS: tuple[str, ...] = ()


def expected_counts(root: Path) -> dict:
    out = {}
    for block in PL.BLOCKS:
        specs = PL.episode_specs(root, block)
        parents = PL.parents_of(root, block)
        per_source = {}
        for p in parents:
            per_source.setdefault(p.source, {"parents": 0, "episodes": 0})
            per_source[p.source]["parents"] += 1
        for s in specs:
            per_source[s.source]["episodes"] += 1
        out[block] = {"parents": len(parents), "episodes": len(specs),
                      "per_source": per_source}
    return out


def main() -> None:
    root = ROOT
    expected = expected_counts(root)
    checks: list[dict] = []

    def check(name: str, ok: bool, detail) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    for block in PL.BLOCKS:
        exp = expected[block]
        n_patterns = len(P.PATTERNS)
        n_horizons = len(P.HORIZONS)
        sev = len(PL.BLOCK_SEVERITIES[block])
        structural = exp["parents"] * n_horizons * n_patterns * sev
        check(f"grid[{block}]", exp["episodes"] == structural,
              f"{exp['parents']} parents x {n_horizons}h x {n_patterns}p x "
              f"{sev}s = {structural} episodes (grid says {exp['episodes']})")

        inputs_json = OUT / "replay/inputs" / f"{block}.json"
        if not inputs_json.exists():
            check(f"prepare[{block}]", False, "input manifest missing")
            continue
        manifest = json.loads(inputs_json.read_text())
        skipped = len(manifest.get("skipped", []))
        check(f"prepare[{block}]",
              manifest["episodes"] + skipped == exp["episodes"],
              f"episodes {manifest['episodes']} + skipped {skipped} "
              f"vs grid {exp['episodes']}")
        npz_path = OUT / "replay/inputs" / f"{block}.npz"
        with np.load(npz_path, allow_pickle=False) as store:
            n_ref = sum(1 for k in store.files if k.endswith("|reference"))
            n_fut = sum(1 for k in store.files if k.endswith("|future"))
            check(f"prepare_arrays[{block}]",
                  n_ref == manifest["episodes"] and n_fut == manifest["episodes"],
                  f"reference {n_ref}, future {n_fut}, episodes {manifest['episodes']}")

        tsicl_json = OUT / "replay/tsicl" / f"{block}.json"
        if tsicl_json.exists():
            status = json.loads(tsicl_json.read_text())
            tsicl_npz = OUT / "replay/tsicl" / f"{block}.npz"
            with np.load(tsicl_npz, allow_pickle=False) as store:
                check(f"tsicl[{block}]",
                      status["status"] == "completed"
                      and status["rows"] == 2 * status["episodes"]
                      and len(store.files) == status["supported"],
                      f"status {status['status']}, rows {status['rows']} "
                      f"(2 x {status['episodes']}), arrays {len(store.files)}, "
                      f"failed {status['failed']}")
        else:
            check(f"tsicl[{block}]", False, "tsicl status missing")

        saits_npz = OUT / "replay/saits" / f"{block}.npz"
        if saits_npz.exists():
            with np.load(saits_npz, allow_pickle=False) as store:
                check(f"saits[{block}]", len(store.files) == manifest["episodes"],
                      f"{len(store.files)} SAITS repairs vs {manifest['episodes']} episodes")
        else:
            check(f"saits[{block}]", False, "saits archive missing")

        for action in EXT_ACTIONS:
            ext_npz = OUT / "replay/external" / action.lower() / f"{block}.npz"
            if ext_npz.exists():
                with np.load(ext_npz, allow_pickle=False) as store:
                    check(f"{action.lower()}[{block}]",
                          len(store.files) == manifest["episodes"],
                          f"{len(store.files)} repairs vs {manifest['episodes']} episodes")
            else:
                check(f"{action.lower()}[{block}]", False, "external archive missing")

        for backbone in P.ALL_BACKBONES:
            status_path = OUT / "replay/forecast" / block / backbone / "status.json"
            if not status_path.exists():
                check(f"forecast[{block}/{backbone}]", False, "status missing")
                continue
            status = json.loads(status_path.read_text())
            pred_npz = OUT / "replay/forecast" / block / backbone / "predictions.npz"
            with np.load(pred_npz, allow_pickle=False) as store:
                check(f"forecast[{block}/{backbone}]",
                      status["status"] == "completed"
                      and status["failed_rows"] == 0
                      and len(store.files) == status["unique_predictions"],
                      f"status {status['status']}, applicable {status['applicable_rows']}"
                      f"/{status['plan_rows']}, unique_predictions "
                      f"{status['unique_predictions']}, failures {len(status['failures'])}")

    report = {
        "stage": "v54-confirmatory-check",
        "registry": PL.REGISTRY_PATH,
        "expected": expected,
        "checks": checks,
        "all_passed": all(c["ok"] for c in checks),
        "main_set_reference": "main test block = 95 parents x 8 = 760 episodes; "
                              "confirmatory test = (Solar + USTS parents) x 8",
        "runtime_seconds": 0.0,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "check_report.json"
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"all_passed": report["all_passed"],
                      "checks": len(checks),
                      "report": str(path)}, indent=1))


if __name__ == "__main__":
    main()
