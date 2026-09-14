"""v3.5 Phase 0: ACV evidence-availability structural audit.

Pre-registered in ``docs/v3_5_acv_preregistration.md`` §4. Pure structural
audit -- no TSFM is queried, no labels are read. For every one of the 2414
candidates in the frozen v3.3 candidate table, the production operator is
re-run on the rebuilt seed-101 corpus window (matched by ``corrupted_hash``
and cross-checked against the p0 manifest, exactly as v3.4 did), the output
hash is verified against the table, the changed support is derived, and the
pre-registered post-action anchor rule of ``v35_acv_common`` is applied.

Writes ``results/v35_acv_support_audit.json`` with the five Phase 0 gates.

Usage:
    python experiments/v35_acv_support_audit.py --n-jobs 32
"""

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from v33_labels import hash_array  # noqa: E402
import v35_acv_common as acv  # noqa: E402

# Phase 0 gate thresholds (pre-registered §4).
GATE2_MIN_ANCHOR1 = 0.85
GATE3_MIN_ANCHOR2 = 0.70

FAMILIES = ("IMPUTE", "DESPIKE", "DENOISE", "RESEGMENT")


def _params_key(params: dict) -> str:
    return json.dumps(params, sort_keys=True)


def _audit_uid(task) -> list:
    """Audit every candidate of one window. Top-level for pickling."""
    sample_uid, series, rows = task
    out = []
    for row in rows:
        rec = acv.audit_candidate(sample_uid, series, row["family"],
                                  row["params"])
        rec["output_matches_table"] = (
            rec["output_hash"] == row.get("output_hash"))
        out.append(rec)
    return out


def _share(recs, pred) -> float:
    n = sum(1 for r in recs if pred(r))
    return n / max(len(recs), 1)


def _coverage_block(recs) -> dict:
    """Anchor-coverage counts for one candidate population."""
    n = len(recs)
    return {
        "n": n,
        "n_support_nonempty": sum(r["support_n"] > 0 for r in recs),
        "n_anchors_ge1": sum(r["n_anchors"] >= 1 for r in recs),
        "n_anchors_ge2": sum(r["n_anchors"] >= 2 for r in recs),
        "n_anchors_ge3": sum(r["n_anchors"] >= 3 for r in recs),
        "share_anchors_ge1": _share(recs, lambda r: r["n_anchors"] >= 1),
        "share_anchors_ge2": _share(recs, lambda r: r["n_anchors"] >= 2),
        "share_anchors_ge3": _share(recs, lambda r: r["n_anchors"] >= 3),
        "n_prequential_supported": sum(r["prequential_supported"]
                                       for r in recs),
        "n_conformity_supported": sum(r["support_conformity_supported"]
                                      for r in recs),
        "n_either_supported": sum(
            r["prequential_supported"] or r["support_conformity_supported"]
            for r in recs),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data",
                    default=str(ROOT / "results" / "v33_training_data.jsonl"))
    ap.add_argument("--manifest",
                    default=str(ROOT / "results" / "p0_corpus_manifest_a.json"))
    ap.add_argument("--out",
                    default=str(ROOT / "results" / "v35_acv_support_audit.json"))
    ap.add_argument("--records-out", default=None,
                    help="optional per-candidate records jsonl")
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
    ap.add_argument("--n-corpus", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    args = ap.parse_args()

    t0 = time.time()

    rows = [json.loads(l) for l in open(args.data, encoding="utf-8")]
    print(f"{len(rows)} candidates", flush=True)

    # Rebuild the frozen seed-101 calibration corpus exactly as the candidate
    # table builder did, then match windows by corrupted_hash -- the pristine
    # series is never read anywhere in this script.
    from build_calibration import build as build_calibration
    windows, _ = build_calibration(n=args.n_corpus, seed=args.seed,
                                   source="mixed", verbose=False)
    print(f"rebuilt {len(windows)} windows in {time.time() - t0:.1f}s",
          flush=True)
    by_hash = defaultdict(list)
    for w in windows:
        by_hash[hash_array(np.asarray(w.series, dtype=np.float64))].append(w)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    manifest_by_uid = {r["sample_uid"]: r for r in manifest["records"]}

    uid_series, n_hash_mismatch, unmatched_uids = {}, 0, []
    for r in rows:
        uid = r["sample_uid"]
        if uid in uid_series:
            continue
        cands = by_hash.get(r["corrupted_hash"], [])
        if len(cands) != 1:
            unmatched_uids.append(uid)
            continue
        series = np.asarray(cands[0].series, dtype=np.float64)
        m = manifest_by_uid.get(uid)
        if hash_array(series) != r["corrupted_hash"] or m is None or \
                m["corrupted_hash"] != r["corrupted_hash"]:
            n_hash_mismatch += 1
            continue
        uid_series[uid] = series
    print(f"matched {len(uid_series)} windows, unmatched "
          f"{len(unmatched_uids)}, hash mismatches {n_hash_mismatch}",
          flush=True)
    if unmatched_uids or n_hash_mismatch:
        raise SystemExit("window reconstruction failed verification; refusing "
                         "to audit against unverified series")

    by_uid = defaultdict(list)
    for r in rows:
        by_uid[r["sample_uid"]].append(r)
    work = [(uid, uid_series[uid], sorted(rs, key=_row_key))
            for uid, rs in sorted(by_uid.items())]

    t1 = time.time()
    if args.n_jobs > 1 and len(work) > 1:
        with ProcessPoolExecutor(max_workers=args.n_jobs) as ex:
            per_uid = list(ex.map(_audit_uid, work))
    else:
        per_uid = [_audit_uid(w) for w in work]
    print(f"audited {len(work)} windows in {time.time() - t1:.1f}s "
          f"(n_jobs={args.n_jobs})", flush=True)

    # Join audit records back to candidate-table metadata (no labels read --
    # only identity fields: family/rung/dataset/stratum/window_id).
    records = []
    for (uid, _, rs), recs in zip(work, per_uid):
        for row, rec in zip(rs, recs):
            records.append({
                "sample_uid": uid,
                "window_id": row["window_id"],
                "dataset": row["dataset"],
                "stratum": row["stratum"],
                "true_kind": row["true_kind"],
                "family": row["family"],
                "rung": row["rung"],
                "params": row["params"],
                "missing_fraction": row["missing_fraction"],
                "corrupted_hash": row["corrupted_hash"],
                **rec,
            })

    n_hash_bad = sum(1 for r in records if not r["output_matches_table"])
    bad_by_family = Counter(r["family"] for r in records
                            if not r["output_matches_table"])
    print(f"output hash mismatches: {n_hash_bad} {dict(bad_by_family)}",
          flush=True)

    # -- population slices -----------------------------------------------------
    # Eligible for the prequential gates (§4): candidates with a non-empty
    # changed support. KEEP is implicit and always legal; it carries no
    # support (see v35_acv_common docstring) and is not an eligible row.
    eligible = [r for r in records if r["support_n"] > 0]

    per_family = {f: _coverage_block([r for r in records if r["family"] == f])
                  for f in FAMILIES}
    per_source = {s: _coverage_block([r for r in records
                                      if r["dataset"] == s])
                  for s in sorted({r["dataset"] for r in records})}
    per_geometry = {g: _coverage_block([r for r in records
                                        if r["geometry"] == g])
                    for g in ("block", "scattered")}
    eligible_by_family = {
        f: _coverage_block([r for r in eligible if r["family"] == f])
        for f in FAMILIES}

    # -- window-level structure --------------------------------------------------
    win = defaultdict(list)
    for r in records:
        win[r["sample_uid"]].append(r)
    cand_per_win = Counter(len(v) for v in win.values())
    ops_per_win = Counter(len({r["family"] for r in v}) for v in win.values())
    tournament_by_stratum = {}
    uid_stratum = {}
    for uid, v in win.items():
        uid_stratum[uid] = v[0]["stratum"]
    for st in sorted(set(uid_stratum.values())):
        uids = [u for u, s in uid_stratum.items() if s == st]
        tournament_by_stratum[st] = {
            "n_windows": len(uids),
            # KEEP is implicit and always legal, so every window has at
            # least KEEP + its candidates; an action tournament among
            # non-KEEP candidates requires >= 2 of them.
            "n_windows_ge2_candidates": sum(
                len(win[u]) >= 2 for u in uids),
            "n_windows_ge2_candidates_with_anchor": sum(
                sum(r["n_anchors"] >= 1 for r in win[u]) >= 2 for u in uids),
        }

    # -- end-of-support failure decomposition -----------------------------------
    no_anchor = [r for r in eligible if r["n_anchors"] == 0]
    failure_reasons = Counter(r["anchor_failure_reason"] for r in no_anchor)
    end_fail_by_family = Counter(r["family"] for r in no_anchor)

    # -- gates (pre-registered §4) -------------------------------------------------
    g1 = n_hash_bad == 0
    cov = _coverage_block(eligible)
    g2 = cov["share_anchors_ge1"] >= GATE2_MIN_ANCHOR1
    g3 = cov["share_anchors_ge2"] >= GATE3_MIN_ANCHOR2
    # Gates 4/5 hold by construction (asserted per candidate inside
    # v35_acv_common.audit_candidate); re-verified here over every record.
    g4 = g5 = True
    for (uid, series, rs), recs in zip(work, per_uid):
        x = np.asarray(series, dtype=np.float64)
        for rec in recs:
            sup = np.zeros(len(x), dtype=bool)
            for lo, hi in rec["support_runs"]:
                sup[lo:hi] = True
            for a in rec["anchors"]:
                if sup[a["start"]:a["end"]].any():
                    g4 = False
                if not np.isfinite(x[a["start"]:a["end"]]).all():
                    g5 = False

    gates = {
        "gate1_support_verifiable": {
            "pass": bool(g1),
            "n_candidates": len(records),
            "n_output_hash_mismatches": int(n_hash_bad),
            "mismatches_by_family": dict(bad_by_family),
            "uncovered_families": sorted(set(bad_by_family)),
        },
        "gate2_anchor_coverage_ge1": {
            "pass": bool(g2),
            "share": cov["share_anchors_ge1"],
            "threshold": GATE2_MIN_ANCHOR1,
            "n_eligible": cov["n"],
            "eligible_definition":
                "candidates with non-empty changed support (KEEP implicit, "
                "no support, excluded from the denominator)",
        },
        "gate3_anchor_coverage_ge2": {
            "pass": bool(g3),
            "share": cov["share_anchors_ge2"],
            "threshold": GATE3_MIN_ANCHOR2,
            "n_eligible": cov["n"],
        },
        "gate4_anchor_support_disjoint": {
            "pass": bool(g4),
            "note": "anchor target intersects changed support for no "
                    "candidate (asserted per candidate and re-verified here)",
        },
        "gate5_anchor_targets_finite": {
            "pass": bool(g5),
            "note": "every anchor target point is an original finite "
                    "observation of the corrupted window; no materialised "
                    "NaN is ever a target",
        },
    }
    verdict = "PASS" if all(g["pass"] for g in gates.values()) else "FAIL"

    evidence_coverage = {
        "n_candidates": len(records),
        "n_prequential_supported": sum(r["prequential_supported"]
                                       for r in records),
        "n_conformity_supported": sum(r["support_conformity_supported"]
                                      for r in records),
        "n_either_supported": sum(
            r["prequential_supported"] or r["support_conformity_supported"]
            for r in records),
        "share_either_supported": _share(
            records, lambda r: r["prequential_supported"]
            or r["support_conformity_supported"]),
    }

    # Both §2.3 anchor readings, reported side by side (main-agent decision,
    # 2026-09: multi-horizon is the adopted rule; the strict Phase-0 reading
    # is kept for the record). Multi-horizon numbers ARE the per-candidate
    # records above (select_anchors now emits one anchor per feasible
    # horizon per run, capped at 3). The legacy reading is recomputed from
    # the stored run capacities: one anchor per run at the largest feasible
    # horizon, capped at 3.
    def _legacy_n(rec):
        return min(acv.MAX_ANCHORS,
                   sum(1 for c in rec["run_capacities"]
                       if c["feasible_horizons"]))

    def _reading(n_of, rule):
        return {
            "rule": rule,
            "share_ge1": _share(eligible, lambda r: n_of(r) >= 1),
            "share_ge2": _share(eligible, lambda r: n_of(r) >= 2),
            "share_ge3": _share(eligible, lambda r: n_of(r) >= 3),
            "per_family": {
                f: {"n": sum(1 for r in eligible if r["family"] == f),
                    "share_ge1": _share(
                        [r for r in eligible if r["family"] == f],
                        lambda r: n_of(r) >= 1),
                    "share_ge2": _share(
                        [r for r in eligible if r["family"] == f],
                        lambda r: n_of(r) >= 2)}
                for f in FAMILIES},
        }

    anchor_readings = {
        "adopted": "multi_horizon",
        "multi_horizon": _reading(
            lambda r: r["n_anchors"],
            "n_anchors = min(3, sum of feasible horizons over runs)"),
        "legacy_per_run": _reading(
            _legacy_n,
            "n_anchors = min(3, n_runs with any feasible horizon, largest "
            "horizon each)"),
        "note": "Phase 0 froze legacy_per_run; the main agent adopted the "
                "multi-horizon reading of §2.3 (2026-09). Gate 2 (>=85% with "
                ">=1 anchor) FAILS under both readings (76.3%): the "
                "bottleneck is DENOISE whole-window rewrites and RESEGMENT "
                "tail cuts -- the prequential applicability boundary, "
                "pre-registered as non-stopping (§4).",
    }

    summary = {
        "phase": "v3.5 Phase 0 ACV support audit (structural, no TSFM)",
        "preregistration": "docs/v3_5_acv_preregistration.md §2, §4",
        "anchor_rule": {
            "horizons": list(acv.HORIZONS),
            "max_anchors": acv.MAX_ANCHORS,
            "horizon_choice": "multi-horizon (adopted): one anchor per "
                              "feasible horizon per support run, tried in "
                              "order 8, 16, 32; legacy Phase-0 reading "
                              "(largest feasible per run) reported under "
                              "anchor_readings.legacy_per_run",
            "cap_rule": "sha256(sample_uid|acv-anchor|run_lo|run_hi|horizon) "
                        "ordering; deterministic in (uid, support) only",
            "eligibility": "finite in corrupted series AND outside changed "
                           "support AND inside retained span (RESEGMENT keeps "
                           "[lo,hi); all others keep the whole window)",
        },
        "keep_handling": {
            "keep_in_candidate_table": False,
            "rule": "KEEP is implicit and always legal; empty support, no "
                    "anchors of its own, prequential_supported=0, "
                    "support_conformity_supported=0; it borrows other "
                    "candidates' anchors as the baseline arm (§2.4 shared "
                    "target/anchor/context) and its tournament score is "
                    "fixed at 0 (§7).",
        },
        "conformity_criterion": {
            "min_context_points": acv.MIN_CONFORMITY_CONTEXT,
            "rule": "support non-empty AND at least MIN_CONFORMITY_CONTEXT "
                    "finite, untouched, retained context points exist",
        },
        "reconstruction": {
            "method": "build_calibration.build(n=1600, seed=101, "
                      "source='mixed') rebuilt the frozen corpus; windows "
                      "matched to candidates by corrupted_hash and "
                      "re-verified against the p0 manifest",
            "n_windows_rebuilt": len(windows),
            "n_windows_matched": len(uid_series),
            "n_unmatched_uids": len(unmatched_uids),
            "n_hash_mismatches": n_hash_mismatch,
            "manifest_sha256_of_file": hashlib.sha256(
                Path(args.manifest).read_bytes()).hexdigest(),
        },
        "population": {
            "n_candidates": len(records),
            "n_windows": len(win),
            "family_counts": dict(Counter(r["family"] for r in records)),
            "rung_counts": dict(Counter(f"{r['family']}/{r['rung']}"
                                        for r in records)),
            "source_counts": dict(Counter(r["dataset"] for r in records)),
            "geometry_counts": dict(Counter(r["geometry"] for r in records)),
            "n_eligible_nonempty_support": len(eligible),
        },
        "coverage": {
            "all_candidates": _coverage_block(records),
            "eligible": cov,
            "per_family": per_family,
            "eligible_per_family": eligible_by_family,
            "per_source": per_source,
            "per_geometry": per_geometry,
        },
        "window_structure": {
            "candidates_per_window": {str(k): v for k, v in
                                      sorted(cand_per_win.items())},
            "distinct_families_per_window": {str(k): v for k, v in
                                             sorted(ops_per_win.items())},
            "tournament_by_stratum": tournament_by_stratum,
        },
        "anchor_failure": {
            "n_eligible_no_anchor": len(no_anchor),
            "share_of_eligible": len(no_anchor) / max(len(eligible), 1),
            "reasons": dict(failure_reasons),
            "by_family": dict(end_fail_by_family),
            "note": "support_reaches_window_end = support extends to the "
                    "window tail leaving < min(horizons) real observations; "
                    "fragmented_tail = eligible points exist after the "
                    "support but no contiguous block reaches horizon 8",
        },
        "evidence_coverage": evidence_coverage,
        "anchor_readings": anchor_readings,
        "prequential_applicability_boundary": _boundary(records),
        "gates": gates,
        "verdict": verdict,
        "code_hashes": _code_hashes(),
        "elapsed_seconds": time.time() - t0,
    }
    Path(args.out).write_text(json.dumps(summary, indent=1, default=float),
                              encoding="utf-8")
    if args.records_out:
        with open(args.records_out, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, sort_keys=True, default=float) + "\n")

    print(json.dumps({k: v["pass"] for k, v in gates.items()}, indent=1))
    print("verdict:", verdict)
    print(f"___V35_ACV_SUPPORT_AUDIT_DONE___ wrote {args.out}", flush=True)


def _row_key(row) -> str:
    return (row["family"], row["rung"], _params_key(row["params"]))


def _boundary(records) -> dict:
    """Which family/source/geometry slices are structurally excluded from
    prequential verification (no valid anchor), recorded per §4: coverage
    below the gates does not stop the pipeline, but the boundary is written
    down before any result is seen."""
    out = {}
    for dim, keyfn in (("family", lambda r: r["family"]),
                       ("source", lambda r: r["dataset"]),
                       ("geometry", lambda r: r["geometry"]),
                       ("family_x_geometry",
                        lambda r: f"{r['family']}|{r['geometry']}")):
        slices = defaultdict(list)
        for r in records:
            if r["support_n"] > 0:
                slices[keyfn(r)].append(r)
        out[dim] = {
            k: {
                "n_eligible": len(v),
                "share_no_anchor": _share(v, lambda r: r["n_anchors"] == 0),
                "excluded": _share(v, lambda r: r["n_anchors"] == 0) >= 0.5,
            } for k, v in sorted(slices.items())}
    return out


def _code_hashes() -> dict:
    out = {}
    for rel in ("experiments/v35_acv_support_audit.py",
                "experiments/v35_acv_common.py",
                "src/introact_ts/actions.py",
                "src/introact_ts/probe.py",
                "experiments/v33_labels.py"):
        p = ROOT / rel
        if p.exists():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


if __name__ == "__main__":
    main()
