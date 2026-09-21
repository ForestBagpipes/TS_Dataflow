#!/usr/bin/env python3
"""v53 harm-cap infeasible-branch audit and code proposal (task 4).

Audits the current behaviour without changing any library code:

* ``introact_ts.v47.select.select_hyperparameters`` (the module that produced
  the frozen selections): when no grid setting satisfies the cap, it replaces
  the feasible set with ``[r for r in rows if r["beta"] == max(beta_grid)]``
  and picks the lowest-LOPO-MASE row among them.  That fallback keeps the
  largest registered penalty but can still violate the cap -- the selected
  configuration's conditional harmful rate is never re-checked.
* ``introact_ts.v47_verified.select.select_hyperparameters`` (the stricter
  rewrite) instead raises ``ValueError("no grid setting satisfies the
  registered harm cap; freeze refused")``.

This script scans selection records (the frozen v47 JSONs and, when present,
the v53 Compact-17 reruns) for whether the branch was ever triggered, and
registers the proposed behaviour as an independent function below: when the
cap is infeasible, the selector must abstain -- disable intervention, return
KEEP for every request, and record the infeasibility -- rather than deploy a
cap-violating configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select_on_infeasible_keep(grid_rows: list[dict], cap: float) -> dict:
    """PROPOSAL (not wired into any library): harm-cap-infeasible branch.

    Drop-in replacement for the fallback branch of
    ``select_hyperparameters``.  ``grid_rows`` are the per-setting outcome
    dicts the grid loop already collects.  When no row respects ``cap`` the
    selector must not deploy: it freezes to KEEP-everything and registers the
    infeasibility, instead of taking the maximum penalty while possibly
    still violating the cap.
    """
    feasible = [r for r in grid_rows if r["conditional_hir"] <= cap]
    if feasible:
        best = min(feasible, key=lambda r: (r["lopo_mase"],
                                            r["intervention_rate"], r["k"]))
        return {"status": "feasible", "selected": {"k": best["k"], "beta": best["beta"]},
                "cap": cap, "decision": "deploy selector"}
    return {"status": "infeasible",
            "selected": None,
            "cap": cap,
            "min_conditional_hir": min(r["conditional_hir"] for r in grid_rows),
            "decision": "abstain: intervention disabled, every request KEEP",
            "registered": "harm cap infeasible on the selection bank"}


def audit_file(path: Path) -> dict:
    data = json.loads(path.read_text())
    out = {"file": str(path), "triggers": []}
    # Frozen v47 layout
    if "selection" in data:
        sel = data["selection"]
        out["triggers"].append({
            "variant": "FULL22",
            "fallback_to_most_conservative": sel.get("fallback_to_most_conservative"),
            "cap": sel.get("cap"),
            "selected": sel.get("selected"),
            "feasible_settings": sel.get("feasible_settings"),
            "selected_conditional_hir": next(
                (r["conditional_hir"] for r in sel.get("grid", [])
                 if r["k"] == sel["selected"]["k"]
                 and r["beta"] == sel["selected"]["beta"]), None),
        })
    # v53 layout
    for variant, pack in (data.get("variants") or {}).items():
        sel = pack["selection"]
        out["triggers"].append({
            "variant": variant,
            "fallback_to_most_conservative": sel.get("fallback_to_most_conservative"),
            "cap": sel.get("cap"),
            "selected": sel.get("selected"),
            "feasible_settings": sel.get("feasible_settings"),
            "selected_conditional_hir": next(
                (r["conditional_hir"] for r in sel.get("grid", [])
                 if r["k"] == sel["selected"]["k"]
                 and r["beta"] == sel["selected"]["beta"]), None),
        })
    for t in out["triggers"]:
        hir = t["selected_conditional_hir"]
        cap = t["cap"]
        t["selected_respects_cap"] = (hir is not None and cap is not None
                                      and hir <= cap + 1e-12)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output-root", default="results/v53_state_compact")
    args = parser.parse_args()
    root = Path(args.root)

    began = time.perf_counter()
    files = sorted((root / "results/v47/protocol").glob("selection_*.json"))
    files += sorted((root / args.output_root).glob("selection_*.json"))
    audits = [audit_file(f) for f in files]

    payload = {
        "stage": "v53-harmcap-infeasible-audit",
        "current_behaviour": {
            "introact_ts.v47.select": (
                "infeasible -> feasible := rows with beta == max(beta_grid); "
                "pick lowest LOPO MASE among them; the cap is NOT re-checked, "
                "so a cap-violating configuration can be frozen "
                "(fallback_to_most_conservative=true)"),
            "introact_ts.v47_verified.select": (
                "infeasible -> raise ValueError('no grid setting satisfies "
                "the registered harm cap; freeze refused')"),
        },
        "proposal": {
            "function": "select_on_infeasible_keep (this file)",
            "behaviour": ("when the cap is infeasible, abstain: disable "
                          "intervention, return KEEP for every request, and "
                          "register the infeasibility in the freeze record"),
            "library_modified": False,
        },
        "code_sha256": {
            "scripts/v53_harmcap_proposal.py": sha256_of(Path(__file__).resolve()),
            "src/introact_ts/v47/select.py": sha256_of(
                root / "src/introact_ts/v47/select.py"),
            "src/introact_ts/v47_verified/select.py": sha256_of(
                root / "src/introact_ts/v47_verified/select.py"),
        },
        "audits": audits,
        "ever_triggered": any(t["fallback_to_most_conservative"]
                              for a in audits for t in a["triggers"]),
        "runtime_seconds": time.perf_counter() - began,
    }
    out = root / args.output_root
    out.mkdir(parents=True, exist_ok=True)
    (out / "harmcap_audit.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(payload, indent=1))


if __name__ == "__main__":
    main()
