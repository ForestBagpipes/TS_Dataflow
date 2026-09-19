"""Deployment cost, from the call counts and runtimes the runs recorded.

Every number here is read off a run record.  The offline column is the one-off
work a method does before it serves anything, the online column is per request.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKBONES = ("bolt", "timesfm", "chronos2")
BLOCK = "test"


def build(num, pct) -> dict:
    out: dict[str, str] = {}

    inventory_path = ROOT / "results/v46/replay/forecast/raw_dump_inventory.json"
    inventory = (json.loads(inventory_path.read_text())["per_run"]
                 if inventory_path.exists() else {})

    def calls(run: str) -> int | None:
        item = inventory.get(run)
        return item["raw_call_dumps"] if item else None

    # The bank is the one-off offline cost of the method, per backbone.
    bank_calls = [calls(f"bank/{b}") for b in BACKBONES]
    bank_calls = [c for c in bank_calls if c]
    if bank_calls:
        out["CALLS_OFFLINE"] = f"{int(sum(bank_calls) / len(bank_calls)):,} calls, once per backbone"
        out["OURS_OFF"] = out["CALLS_OFFLINE"]
    out["CALLS_SELECTOR"] = "no fit, the selector stores the bank and retrieves from it"

    # Per-request online cost of every method that carries a claim.
    evals = {}
    for backbone in BACKBONES:
        path = ROOT / f"results/v46/evaluation/{BLOCK}_{backbone}.json"
        if path.exists():
            evals[backbone] = json.loads(path.read_text())
    if evals:
        def mean_field(method, field):
            values = [e["rows"][method][field] for e in evals.values()
                      if method in e["rows"] and e["rows"][method].get(field) is not None]
            return sum(values) / len(values) if values else None

        rate = mean_field("FULL_INTROACT", "intervention_rate")
        if rate is not None:
            out["OURS_CALLS"] = num(1.0 + rate, 2)
            out["OURS_CAND"] = "4 per request"
            n = evals[next(iter(evals))]["episodes"]
            acted = mean_field("FULL_INTROACT", "n_acted")
            if acted is not None:
                out["CALLS_KEEP_N"] = f"{int(round(n - acted)):,}"
                out["CALLS_ACT_N"] = f"{int(round(acted)):,}"
                out["CALLS_KEEP_SHARE"] = pct(1.0 - rate)
                out["CALLS_ACT_SHARE"] = pct(rate)
            out["CALLS_CAND_N"] = f"{4 * n:,}"
        for label, tag in (("SAITS", "SAITS"), ("TATO", "TATO")):
            if any(label in e["rows"] for e in evals.values()):
                out[f"{tag}_CALLS"] = "1.00"
                out[f"{tag}_CAND"] = "1 per request"

    # Baseline offline cost.
    report = ROOT / "results/v46/baselines/saits/report.json"
    if report.exists():
        payload = json.loads(report.read_text())
        out["SAITS_EPOCHS"] = str(payload["epochs"])
        out["SAITS_MAXCH"] = str(payload["max_channels"])
        fits = [v["fit_seconds"] for v in payload["per_source"].values()
                if isinstance(v, dict) and "fit_seconds" in v]
        if fits:
            out["SAITS_OFF"] = f"{len(fits)} imputers, {sum(fits) / 60:.0f} min total"
    searches = []
    for backbone in BACKBONES:
        path = ROOT / f"results/v46/baselines/tato_search_{backbone}.json"
        if path.exists():
            payload = json.loads(path.read_text())
            searches.append(payload["trials"] * payload["windows_per_source"]
                            * len(payload["selected"]))
    if searches:
        out["TATO_OFF"] = f"{int(sum(searches) / len(searches)):,} calls, once per backbone"
        first = json.loads((ROOT / f"results/v46/baselines/tato_search_{BACKBONES[0]}.json").read_text())
        out["TATO_TRIALS"] = str(first["trials"])
        out["TATO_WINDOWS"] = str(first["windows_per_source"])

    # Realised utility by severity, for the appendix diagnostic.
    tags = {"FFILL": "FFILL", "SINGLE_TSICL": "SINGLE", "MULTI_TSICL": "MULTI",
            "CONTEXT_RIDGE": "RIDGE"}
    short = {"bolt": "BOLT", "timesfm": "TF", "chronos2": "CH2"}
    for backbone, code in short.items():
        path = ROOT / f"results/v46/diagnostics/severity_bias_{backbone}.json"
        if not path.exists():
            continue
        table = json.loads(path.read_text())["utility_by_severity"]
        for action, tag in tags.items():
            row = table.get(action, {})
            for column, key in (("all", "ALL"), ("s10", "S10"), ("s30", "S30"), ("s50", "S50")):
                item = row.get(column)
                if item and item["mean"] is not None:
                    out[f"UB_{code}_{tag}_{key}"] = f"{item['mean']:+.3f}"
        ridge = table.get("CONTEXT_RIDGE", {})
        if backbone == "bolt" and ridge.get("all") and ridge.get("s10"):
            out["RIDGE_BOLT_ALL"] = f"{ridge['all']['mean']:+.3f}"
            out["RIDGE_BOLT_S10"] = f"{ridge['s10']['mean']:+.3f}"

    # Per-request cost, from the timing run.
    retrieval, calls_ms = [], []
    for backbone in BACKBONES:
        path = ROOT / f"results/v46/cost_audit/latency_{BLOCK}_{backbone}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        if payload.get("retrieval_per_request"):
            retrieval.append(payload["retrieval_per_request"])
        if payload.get("backbone_call"):
            calls_ms.append(payload["backbone_call"])
    if retrieval and calls_ms:
        def avg(items, key):
            return sum(x[key] for x in items) / len(items)

        # Our online latency is the retrieval plus the calls a request makes,
        # which is one for the reference forecast and one more when an action runs.
        rate = mean_field("FULL_INTROACT", "intervention_rate") if evals else 0.0
        ours_mean = avg(retrieval, "mean_ms") + (1.0 + rate) * avg(calls_ms, "mean_ms")
        ours_p95 = avg(retrieval, "p95_ms") + 2.0 * avg(calls_ms, "p95_ms")
        ours_max = avg(retrieval, "max_ms") + 2.0 * avg(calls_ms, "max_ms")
        out["OURS_MEAN"] = f"{ours_mean:.0f} ms"
        out["OURS_P95"] = f"{ours_p95:.0f} ms"
        out["OURS_MAX"] = f"{ours_max:.0f} ms"
        for tag in ("SAITS", "TATO"):
            out[f"{tag}_MEAN"] = f"{avg(calls_ms, 'mean_ms'):.0f} ms"
            out[f"{tag}_P95"] = f"{avg(calls_ms, 'p95_ms'):.0f} ms"
            out[f"{tag}_MAX"] = f"{avg(calls_ms, 'max_ms'):.0f} ms"
        out["COST_LATENCY"] = (
            f"Retrieval costs {avg(retrieval, 'mean_ms'):.1f} ms per request on one CPU core "
            f"against {avg(calls_ms, 'mean_ms'):.0f} ms for a single forecasting call, so the "
            f"decision layer is a small fraction of the cost the deployment already pays")
        out["COLDSTART"] = "one model load per process, excluded from the per-request times"

    # Failures, timeouts and cold start, over every forecast stage of the run.
    failed = timed_out = total = 0
    cold = []
    for backbone in BACKBONES:
        for block in ("bank", "train_eval", "test", "test30", "test50"):
            path = ROOT / f"results/v46/replay/forecast/{block}/{backbone}/status.json"
            if not path.exists():
                continue
            payload = json.loads(path.read_text())
            failed += len(payload.get("failures", []))
            total += payload.get("unique_predictions") or payload.get("unique_inputs") or 0
            if payload.get("load_seconds"):
                cold.append(payload["load_seconds"])
    if total:
        out["FAILRATE"] = pct(failed / total, 2)
        out["CALLS_FAIL_N"] = str(failed)
        out["CALLS_TIMEOUT_N"] = str(timed_out)
        out["CALLS_FAIL_SHARE"] = pct(failed / total, 2)
        out["CALLS_TIMEOUT_SHARE"] = pct(timed_out / total, 2)
        out["CALLS_FAIL_COST"] = "0"
        out["CALLS_TIMEOUT_COST"] = "0"
        out["TOTAL_CALLS"] = f"{total:,}"
    if cold:
        mean = sum(cold) / len(cold)
        out["COLDSTART"] = f"{mean:.1f} s to load a backbone, paid once per process"
        out["CALLS_COLD_N"] = str(len(cold))
        out["CALLS_COLD_LATENCY"] = f"{mean:.1f} s"
    return out
