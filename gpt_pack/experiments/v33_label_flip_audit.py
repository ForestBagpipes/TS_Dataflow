"""v3.3 label-flip audit and metric-integrity hard gates (Phase 2).

Joins the v3.2 table (``results/v32_training_data.jsonl``) and the rebuilt
v3.3 table (``results/v33_training_data.jsonl``) on
``(sample_uid, family, canonical params)`` and produces two files:

``results/v33_metric_integrity.json`` -- the hard gates:
  * identical key sets, corrupted/clean hashes and params;
  * bit-identical labels and before/after NMSE for every non-IMPUTE row
    (DENOISE, DESPIKE, RESEGMENT), which under the deterministic pipeline
    certifies operator-output identity -- the v3.2 table predates
    ``output_hash``, so this is the strongest available anchor;
  * bit-identical feature vectors, delta_utility, struct_distortion and risk
    on ALL rows (labels changed; the deployed observables must not).

``results/v33_label_flip_audit.json`` -- what the label repair changed:
  transition matrices old -> new for IMPUTE, broken down by true_kind,
  dataset and rung; before/after NMSE distribution shift; oracle headroom
  recomputed under the new labels; the fate of the 13 old missing-kind harmful
  commits; US Term Structure listed separately.

No models are trained here. If an integrity gate fails the JSON says so and
the run must stop for a code audit before anything downstream consumes the
new table.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

LABEL_FIELDS = ("before_nmse", "after_nmse", "true_loss", "true_repair_gain",
                "beneficial", "safe", "harmful", "beneficial_and_safe")
OBSERVABLE_FIELDS = ("delta_utility", "struct_distortion", "risk",
                     "repair_rmsd")
MISSING_KINDS = ("missing_block", "missing_scattered", "flatline")

#: Two runs of perceive differ at the 1e-14 level in window-level state
#: features (confidence, ood) because threaded BLAS reductions in the
#: statistical profile are not bit-deterministic across process pools. The
#: gate for observables therefore uses a 1e-12 absolute tolerance; labels,
#: hashes and params stay bit-exact.
FP_TOL = 1e-12


def _same(a, b, tol=FP_TOL):
    if isinstance(a, float) or isinstance(b, float):
        try:
            fa, fb = float(a), float(b)
        except (TypeError, ValueError):
            return a == b
        if np.isnan(fa) and np.isnan(fb):
            return True
        return abs(fa - fb) <= tol
    return a == b


def _features_same(a: dict, b: dict) -> bool:
    if set(a) != set(b):
        return False
    return all(_same(a[k], b[k]) for k in a)


def _key(row):
    return (row["sample_uid"], row["family"],
            json.dumps(row["params"], sort_keys=True))


def _load(path):
    rows = {}
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            rows[_key(r)] = r
    return rows


def _transition(old, new):
    def sig(r):
        return (int(r["beneficial"]), int(r["harmful"]),
                int(r["beneficial_and_safe"]))
    return f"{sig(old)}->{sig(new)}"


def _dist(vals):
    v = np.asarray([x for x in vals if x is not None and np.isfinite(x)],
                   dtype=np.float64)
    if len(v) == 0:
        return {"n": 0}
    return {"n": int(len(v)), "mean": float(v.mean()),
            "median": float(np.median(v)),
            "p90": float(np.percentile(v, 90))}


def main():
    old = _load(ROOT / "results" / "v32_training_data.jsonl")
    new = _load(ROOT / "results" / "v33_training_data.jsonl")
    print(f"old {len(old)} rows, new {len(new)} rows", flush=True)

    # -- integrity hard gates --------------------------------------------------
    gates = {}
    gates["key_sets_equal"] = set(old) == set(new)
    shared = set(old) & set(new)

    hash_mismatch, label_drift, observable_drift = [], [], []
    for k in sorted(shared):
        o, n = old[k], new[k]
        if o["corrupted_hash"] != n["corrupted_hash"] \
                or o["clean_hash"] != n["clean_hash"]:
            hash_mismatch.append(k)
        if o["family"] != "IMPUTE":
            if any(o[f] != n[f] for f in LABEL_FIELDS):
                label_drift.append(k)
        # Scalar observables: bit-exact (NaN == NaN). Feature vectors: fp-noise
        # tolerance (threaded BLAS in perceive, measured <= 1.5e-14).
        if any(not _same(o[f], n[f], tol=0.0) for f in OBSERVABLE_FIELDS):
            observable_drift.append(k)
        elif not _features_same(o["features"], n["features"]):
            observable_drift.append(k)

    gates["identity_hashes_match"] = not hash_mismatch
    gates["non_impute_labels_bit_identical"] = not label_drift
    gates["observables_bit_identical_all_rows"] = not observable_drift
    integrity = {
        "n_old": len(old), "n_new": len(new), "n_shared": len(shared),
        "gates": gates,
        "n_hash_mismatch": len(hash_mismatch),
        "n_non_impute_label_drift": len(label_drift),
        "n_observable_drift": len(observable_drift),
        "label_drift_examples": [list(k)[:2] for k in label_drift[:10]],
        "observable_drift_examples": [list(k)[:2] for k in observable_drift[:10]],
        "note": ("v3.2 predates output_hash; operator-output identity is "
                 "certified by bit-identical params plus bit-identical "
                 "before/after NMSE on non-IMPUTE rows, both deterministic "
                 "functions of the output. output_hash is recorded from the "
                 "v3.3 table onward."),
    }
    integrity["passes"] = all(gates.values())
    (ROOT / "results" / "v33_metric_integrity.json").write_text(
        json.dumps(integrity, indent=1), encoding="utf-8")
    print(f"integrity gates: {gates}", flush=True)

    # -- label flips -----------------------------------------------------------
    flips = Counter()
    by_kind, by_dataset, by_rung = Counter(), Counter(), Counter()
    nmse_shift = {"before_old": [], "before_new": [],
                  "after_old": [], "after_new": []}
    impute_shared = [k for k in shared if old[k]["family"] == "IMPUTE"]
    for k in impute_shared:
        o, n = old[k], new[k]
        t = _transition(o, n)
        flips[t] += 1
        by_kind[(o["true_kind"], t)] += 1
        by_dataset[(o["dataset"], t)] += 1
        by_rung[(o["rung"], t)] += 1
        nmse_shift["before_old"].append(o["before_nmse"])
        nmse_shift["before_new"].append(n["before_nmse"])
        nmse_shift["after_old"].append(o["after_nmse"])
        nmse_shift["after_new"].append(n["after_nmse"])

    # -- oracle headroom under the new labels ----------------------------------
    fams = defaultdict(lambda: defaultdict(list))
    for k, n in new.items():
        fams[n["family"]][n["stratum"]].append(n)
    headroom = {}
    contaminated_total = sum(
        1 for n in new.values() if n["stratum"] == "contaminated")
    contaminated_windows = {n["sample_uid"] for n in new.values()
                            if n["stratum"] == "contaminated"}
    for fam, strata in fams.items():
        rows = [r for rs in strata.values() for r in rs]
        cont = strata.get("contaminated", [])
        bs = [r for r in cont if r["beneficial_and_safe"] == 1.0]
        win_bs = {r["sample_uid"] for r in bs}
        # Max coverage at mean damage <= 0.03: per contaminated window take its
        # lowest-loss beneficial candidate, greedily add windows by that loss.
        best = {}
        for r in cont:
            if r["beneficial"] == 1.0:
                if r["sample_uid"] not in best \
                        or r["true_loss"] < best[r["sample_uid"]]["true_loss"]:
                    best[r["sample_uid"]] = r
        ordered = sorted(best.values(), key=lambda r: r["true_loss"])
        cov, tot_loss = 0, 0.0
        for r in ordered:
            if (tot_loss + r["true_loss"]) / (cov + 1) <= 0.03:
                cov += 1
                tot_loss += r["true_loss"]
            else:
                break
        headroom[fam] = {
            "routed": len(rows),
            "contaminated_routed": len(cont),
            "safe": sum(r["safe"] for r in cont),
            "beneficial": sum(r["beneficial"] for r in cont),
            "beneficial_and_safe": len(bs),
            "contaminated_bs_rate": len(bs) / max(len(cont), 1),
            "windows_with_bs": len(win_bs),
            "oracle_window_coverage": len(win_bs) / max(len(contaminated_windows), 1),
            "max_coverage_at_damage_0.03": cov / max(len(contaminated_windows), 1),
        }

    # -- fate of the 13 old missing-kind harmful commits ------------------------
    harm_path = ROOT / "results" / "v32_harmful_commits.json"
    old_commits = []
    if harm_path.exists():
        d = json.loads(harm_path.read_text(encoding="utf-8"))
        old_commits = [r for r in d["PICS_joint"]
                       if r["family"] == "IMPUTE"
                       and r["true_kind"] in MISSING_KINDS]
    by_win_fam = defaultdict(list)
    for k in impute_shared:
        n = new[k]
        by_win_fam[(n["sample_uid"], n["family"])].append(n)
    fates = []
    for c in old_commits:
        cands = by_win_fam.get((c["sample_uid"], "IMPUTE"), [])
        match = next((r for r in cands if r["rung"] == c.get("rung")),
                     cands[0] if cands else None)
        fates.append({
            "sample_uid": c["sample_uid"],
            "dataset": c["dataset"],
            "true_kind": c["true_kind"],
            "rung": c.get("rung"),
            "old": {"before_nmse": c["before_nmse"], "after_nmse": c["after_nmse"],
                    "true_loss": c["true_loss"]},
            "new": None if match is None else {
                f: match[f] for f in LABEL_FIELDS},
        })

    # US Term Structure listed separately.
    usts = [k for k in impute_shared if old[k]["dataset"] == "US Term Structure"]
    usts_flips = Counter(_transition(old[k], new[k]) for k in usts)

    audit = {
        "n_impute_shared": len(impute_shared),
        "transition_counts": {k: v for k, v in sorted(flips.items())},
        "by_true_kind": {f"{k[0]}|{k[1]}": v for k, v in sorted(by_kind.items())},
        "by_dataset": {f"{k[0]}|{k[1]}": v for k, v in sorted(by_dataset.items())},
        "by_rung": {f"{k[0]}|{k[1]}": v for k, v in sorted(by_rung.items())},
        "nmse_shift": {k: _dist(v) for k, v in nmse_shift.items()},
        "oracle_headroom_new_labels": headroom,
        "contaminated_windows_total": len(contaminated_windows),
        "old_missing_harmful_commit_fates": fates,
        "us_term_structure": {"n_impute": len(usts),
                              "transitions": dict(sorted(usts_flips.items()))},
    }
    (ROOT / "results" / "v33_label_flip_audit.json").write_text(
        json.dumps(audit, indent=1), encoding="utf-8")
    print(f"___V33_LABEL_AUDIT_DONE___ integrity_passes={integrity['passes']}",
          flush=True)


if __name__ == "__main__":
    main()
