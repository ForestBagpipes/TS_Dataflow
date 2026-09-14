"""P0-C: audit existing result files against the frozen corpus manifest.

For every record that carries a window_id, look it up in the manifest and check
that dataset/stratum/true_kind agree. Result files written before the data
provenance contract do not store series hashes, so they are marked
"metadata_verifiable" when the metadata matches and "hash_unverifiable"
otherwise. Files without window-level linkage are marked "aggregate_only".
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))


def load_manifest(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    by_window_id = {r["window_id"]: r for r in data["records"]}
    return by_window_id, data


def _norm(x):
    """Treat JSON null and the string 'null' as equivalent."""
    return "null" if x is None else x


def verify_window_record(rec: dict, manifest: dict, expected_keys: tuple):
    wid = rec.get("window_id")
    if wid is None:
        return {"status": "no_window_id", "reason": "missing window_id"}
    m = manifest.get(wid)
    if m is None:
        return {"status": "window_not_in_manifest", "window_id": wid}
    diffs = {}
    for k in expected_keys:
        if k in rec and _norm(rec[k]) != _norm(m[k]):
            diffs[k] = {"result": rec[k], "manifest": m[k]}
    if diffs:
        return {"status": "metadata_mismatch", "window_id": wid, "diffs": diffs}
    return {"status": "metadata_verifiable", "window_id": wid,
            "sample_uid": m["sample_uid"], "hash_unverifiable": True}


def audit_family_scores(path: Path, manifest: dict):
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            rows.append(rec)
    statuses = Counter()
    details = []
    for rec in rows:
        # family_scores records one row per window with candidate list.
        res = verify_window_record(rec, manifest, ("dataset", "stratum"))
        statuses[res["status"]] += 1
        if res["status"] != "metadata_verifiable":
            details.append({"window_id": rec.get("window_id"), **res})
    return {"n": len(rows), "status_counts": dict(statuses), "anomalies": details}


def audit_level_shift_probe(path: Path, manifest: dict):
    data = json.loads(path.read_text(encoding="utf-8"))
    per_window = data.get("per_window", {})
    statuses = Counter()
    anomalies = []
    total = 0
    for variant, rows in per_window.items():
        for rec in rows:
            total += 1
            res = verify_window_record(rec, manifest,
                                       ("dataset", "stratum", "true_kind"))
            statuses[res["status"]] += 1
            if res["status"] != "metadata_verifiable":
                anomalies.append({"variant": variant, "window_id": rec.get("window_id"), **res})
    return {"n": total, "status_counts": dict(statuses), "anomalies": anomalies}


def audit_route_conditioned_shift(path: Path, manifest: dict):
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("per_window", [])
    statuses = Counter()
    anomalies = []
    for rec in rows:
        res = verify_window_record(rec, manifest,
                                   ("dataset", "stratum", "true_kind"))
        statuses[res["status"]] += 1
        if res["status"] != "metadata_verifiable":
            anomalies.append({"window_id": rec.get("window_id"), **res})
    return {"n": len(rows), "status_counts": dict(statuses), "anomalies": anomalies}


def audit_counterfactual_routing(path: Path, manifest: dict):
    data = json.loads(path.read_text(encoding="utf-8"))
    # No window_id linkage; check that n_windows matches manifest size.
    n_manifest = len(manifest)
    n_result = data.get("n_windows")
    return {
        "status": "aggregate_only",
        "n_windows_result": n_result,
        "n_windows_manifest": n_manifest,
        "match": n_result == n_manifest,
        "datasets": data.get("datasets"),
    }


def audit_misroute_evidence(path: Path, manifest: dict):
    data = json.loads(path.read_text(encoding="utf-8"))
    detail = data.get("detail", {})
    statuses = Counter()
    anomalies = []
    total = 0
    for family, rows in detail.items():
        for rec in rows:
            total += 1
            res = verify_window_record(rec, manifest, ("true_kind",))
            # Misroute evidence may not store dataset/stratum, so only check true_kind.
            statuses[res["status"]] += 1
            if res["status"] != "metadata_verifiable":
                anomalies.append({"family": family, "window_id": rec.get("window_id"), **res})
    return {"n": total, "status_counts": dict(statuses), "anomalies": anomalies}


def audit_conformal_family(path: Path, manifest: dict):
    data = json.loads(path.read_text(encoding="utf-8"))
    n_result = data.get("n_windows")
    n_manifest = len(manifest)
    return {
        "status": "aggregate_only",
        "n_windows_result": n_result,
        "n_windows_manifest": n_manifest,
        "match": n_result == n_manifest,
        "families": list(data.get("families", {}).keys()),
    }


def audit_resegment_noop(path: Path, manifest: dict):
    data = json.loads(path.read_text(encoding="utf-8"))
    n_result = data.get("n_windows")
    n_manifest = len(manifest)
    return {
        "status": "aggregate_only",
        "n_windows_result": n_result,
        "n_windows_manifest": n_manifest,
        "match": n_result == n_manifest,
        "slice_seed": data.get("slice_seed"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(ROOT / "results" / "p0_corpus_manifest_a.json"))
    ap.add_argument("--out", default=str(ROOT / "results" / "p0_result_manifest_audit.json"))
    args = ap.parse_args()

    manifest, manifest_meta = load_manifest(Path(args.manifest))
    print(f"loaded manifest with {len(manifest)} windows")

    results_root = ROOT / "results"
    report = {
        "manifest": {
            "path": args.manifest,
            "n_windows": len(manifest),
            "unique_uids": manifest_meta["diagnostics"]["unique_uids"],
        },
        "audits": {},
    }

    report["audits"]["family_scores.jsonl"] = audit_family_scores(
        results_root / "family_scores.jsonl", manifest)
    report["audits"]["level_shift_probe.json"] = audit_level_shift_probe(
        results_root / "level_shift_probe.json", manifest)
    report["audits"]["route_conditioned_shift.json"] = audit_route_conditioned_shift(
        results_root / "route_conditioned_shift.json", manifest)
    report["audits"]["counterfactual_routing.json"] = audit_counterfactual_routing(
        results_root / "counterfactual_routing.json", manifest)
    report["audits"]["misroute_evidence.json"] = audit_misroute_evidence(
        results_root / "misroute_evidence.json", manifest)
    report["audits"]["conformal_family.json"] = audit_conformal_family(
        results_root / "conformal_family.json", manifest)
    report["audits"]["resegment_noop.json"] = audit_resegment_noop(
        results_root / "resegment_noop.json", manifest)

    # Minimum reconstruction list: any record that is not metadata_verifiable.
    reconstruction = []
    for fname, audit in report["audits"].items():
        if "status_counts" in audit:
            for status, count in audit["status_counts"].items():
                if status != "metadata_verifiable":
                    reconstruction.append({"file": fname, "status": status, "count": count})
        elif audit.get("status") != "metadata_verifiable":
            reconstruction.append({
                "file": fname,
                "status": audit.get("status"),
                "note": "aggregate-only file, rebuild from manifest if used quantitatively",
            })
    report["reconstruction_list"] = reconstruction
    report["all_metadata_verifiable"] = all(
        audit.get("status_counts", {}).get("metadata_verifiable", 0) == audit.get("n", 0)
        for audit in report["audits"].values() if "status_counts" in audit
    )

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"___P0_RESULT_MANIFEST_AUDIT_DONE___ wrote {args.out}")
    for fname, audit in report["audits"].items():
        if "status_counts" in audit:
            print(f"  {fname}: n={audit['n']} {audit['status_counts']}")
        else:
            print(f"  {fname}: {audit['status']} match={audit.get('match')}")


if __name__ == "__main__":
    main()
