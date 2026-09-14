"""v3.8 Phase 0 Part B: IMPUTE candidate mask-semantics audit.

Pre-registered in ``docs/v3_8_fact_preregistration.md`` §2-§3. CPU-only,
API 0, n_jobs <= 16. Read-only against every frozen artifact.

The frozen seed-101 calibration corpus is rebuilt from raw data via
``build_calibration.build(n=1600, seed=101, source='mixed')`` (1599 windows)
and verified against ``results/p0_corpus_manifest_a.json`` and against the
candidate table's hashes before any audit number is computed -- the same
rebuild-and-verify discipline as ``experiments/v34_shadow_certificate.py``.

Layering (mutually exclusive, window-level, from the RAW corrupted series):

  actual_nan_only       window has true NaN (~isfinite) and no finite flatline
  finite_flatline_only  no NaN, but a finite flatline run exists
  mixed                 both
  neither               neither

Finite flatline = a run of exactly-equal consecutive FINITE values
(|diff| < 1e-12, the same equality test as ``actions.missing_mask``,
src/introact_ts/actions.py:101) of length >= FLATLINE_K. k = 16 is fixed here
before any result is seen, from two reference points: the production detector
that actually routes these windows into IMPUTE candidates flags frozen runs
of length >= MIN_FLATLINE_RUN = 16 (src/introact_ts/actions.py:25, used by
missing_mask at lines 82-119 and by op_impute at lines 262-329), and the
corpus injector writes constant runs of length randint(max(24, T//20),
max(32, T//10)) = 24..50 at T=512 (experiments/corpus.py:118-122 and
200-205), so every injected flatline clears k=16 with margin.

Masks are ALWAYS computed on the raw corrupted series. The probe-materialised
series (``introact_ts.probe.materialize_for_probe``, src/introact_ts/
probe.py:93-122) forward-fills NaNs and is used here only to DEMONSTRATE the
erasure: per candidate we record the NaN count after materialisation and
whether the candidate mask recomputed on the materialised series differs
from the one on the raw series.

Outputs:
  results/v38_impute_mask_audit.json     layered report + four answers
  results/v38_impute_mask_records.jsonl  one record per IMPUTE candidate
  results/v38_phase0_manifest.json       Phase-0 integrity gates

Usage:
    python experiments/v38_impute_mask_audit.py --n-jobs 16 \
        --digest-a /tmp/v38_digest_a.json --digest-b /tmp/v38_digest_b.json
    python experiments/v38_impute_mask_audit.py --mask-digest /tmp/v38_digest_a.json
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
from introact_ts.actions import (  # noqa: E402
    Action, apply_action, missing_mask, _mask_runs,
)
from introact_ts.probe import materialize_for_probe  # noqa: E402
from introact_ts.contextual_shield import EPISODE_FAMILY_ORDER  # noqa: E402

ROWS_PATH = ROOT / "results" / "v33_training_data.jsonl"
MANIFEST_PATH = ROOT / "results" / "p0_corpus_manifest_a.json"
V36_PROBE_PATH = ROOT / "results" / "v36_pair_probe.json"
V33_HARMFUL_PATH = ROOT / "results" / "v33_clean_rerun_harmful.json"
REPLAY_PATH = ROOT / "results" / "v38_oracle_replay.json"
OUT_AUDIT = ROOT / "results" / "v38_impute_mask_audit.json"
OUT_RECORDS = ROOT / "results" / "v38_impute_mask_records.jsonl"
OUT_MANIFEST = ROOT / "results" / "v38_phase0_manifest.json"

#: See the module docstring for the derivation of k.
FLATLINE_K = 16
#: Equality tolerance for "consecutive equal values"; identical to
#: actions.missing_mask (src/introact_ts/actions.py:101).
FLATLINE_EPS = 1e-12
#: Project standing harm level (CHR threshold).
HARM_LOSS = 0.03

LAYERS = ("actual_nan_only", "finite_flatline_only", "mixed", "neither")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pkey(params):
    return json.dumps(params, sort_keys=True)


# -- raw mask primitives (unit-tested locally) ------------------------------------


def raw_nan_mask(series) -> np.ndarray:
    """True missing mask: non-finite points of the RAW corrupted series."""
    return ~np.isfinite(np.asarray(series, dtype=np.float64))


def finite_flatline_mask(series, k=FLATLINE_K, eps=FLATLINE_EPS) -> np.ndarray:
    """Points inside constant-value runs of length >= k, finite values only.

    A run of exactly-equal diffs over diff-indices [a, b) corresponds to the
    constant value run [a, b+1) of length b - a + 1 -- the same convention as
    ``actions.missing_mask`` (src/introact_ts/actions.py:108-118).
    """
    x = np.asarray(series, dtype=np.float64)
    out = np.zeros(len(x), dtype=bool)
    if len(x) < 2:
        return out
    d = np.diff(x)
    frozen = np.isfinite(d) & (np.abs(d) < eps)
    for lo, hi in _mask_runs(frozen):
        if hi - lo + 1 >= k:
            out[lo:hi + 1] = True
    return out


def window_layer(nan_mask, flat_mask) -> str:
    """Mutually exclusive and exhaustive window layer."""
    has_nan = bool(np.any(nan_mask))
    has_flat = bool(np.any(flat_mask))
    if has_nan and has_flat:
        return "mixed"
    if has_nan:
        return "actual_nan_only"
    if has_flat:
        return "finite_flatline_only"
    return "neither"


def gap_runs(nan_mask) -> list:
    """Lengths of the contiguous NaN runs, in order."""
    return [hi - lo for lo, hi in _mask_runs(np.asarray(nan_mask, dtype=bool))]


def anchor_geometry(series, nan_mask=None) -> list:
    """Per NaN run: position, length, and whether each side ends on a finite
    anchor (False at the window boundary -- the run is maximal, so an in-range
    neighbour is finite by construction)."""
    x = np.asarray(series, dtype=np.float64)
    nm = raw_nan_mask(x) if nan_mask is None else np.asarray(nan_mask, bool)
    T = len(x)
    out = []
    for lo, hi in _mask_runs(nm):
        out.append({
            "lo": int(lo), "hi": int(hi), "length": int(hi - lo),
            "left_anchor": bool(lo > 0 and np.isfinite(x[lo - 1])),
            "right_anchor": bool(hi < T and np.isfinite(x[hi])),
        })
    return out


def mask_origin(touched, nan_mask, flat_mask) -> str:
    """Composition of a candidate's touched mask against the raw layers."""
    t = np.asarray(touched, dtype=bool)
    if not t.any():
        return "empty"
    parts = []
    if np.any(t & nan_mask):
        parts.append("raw_nan")
    if np.any(t & flat_mask):
        parts.append("finite_flatline")
    if np.any(t & ~nan_mask & ~flat_mask):
        parts.append("other_finite")
    return "+".join(parts)


def mask_hash(mask) -> str:
    return hashlib.sha256(np.asarray(mask, dtype=bool).tobytes()).hexdigest()


def window_mask_digest_record(uid, series) -> dict:
    """The raw-mask fingerprint of one window (two-process determinism gate)."""
    nm = raw_nan_mask(series)
    fm = finite_flatline_mask(series)
    return {"sample_uid": uid,
            "raw_nan_mask_hash": mask_hash(nm),
            "finite_flatline_mask_hash": mask_hash(fm),
            "raw_nan_fraction": float(nm.mean())}


def digest_of_windows(uid_series: list) -> dict:
    """Sorted digest table + its sha256; pure function of the input list."""
    recs = sorted((window_mask_digest_record(uid, s) for uid, s in uid_series),
                  key=lambda r: r["sample_uid"])
    blob = json.dumps(recs, sort_keys=True).encode("utf-8")
    return {"n_windows": len(recs), "sha256": hashlib.sha256(blob).hexdigest(),
            "records": recs}


# -- corpus rebuild + verification ---------------------------------------------------


def rebuild_corpus(n=1600, seed=101, source="mixed"):
    from build_calibration import build as build_calibration
    from v3_training_data import sample_uid
    windows, dropped = build_calibration(n=n, seed=seed, source=source,
                                         verbose=False)
    out = []
    for w in windows:
        series = np.asarray(w.series, dtype=np.float64)
        out.append({
            "window": w,
            "series": series,
            "sample_uid": sample_uid(w),
            "corrupted_hash": hash_array(series),
            "clean_hash": (hash_array(np.asarray(w.clean_series,
                                                 dtype=np.float64))
                           if w.clean_series is not None else "no_clean"),
        })
    return out, dropped


def verify_against_manifest(recs, manifest):
    """Gate: the rebuilt 1599 sample_uids and hashes equal the p0 manifest."""
    m_by_uid = {r["sample_uid"]: r for r in manifest["records"]}
    r_by_uid = {r["sample_uid"]: r for r in recs}
    uids_match = set(m_by_uid) == set(r_by_uid)
    hash_mismatch = []
    for uid in sorted(set(m_by_uid) & set(r_by_uid)):
        m, r = m_by_uid[uid], r_by_uid[uid]
        if (m["corrupted_hash"] != r["corrupted_hash"]
                or m["clean_hash"] != r["clean_hash"]):
            hash_mismatch.append(uid)
    return {"n_rebuilt": len(recs), "n_manifest": len(manifest["records"]),
            "uids_match": bool(uids_match),
            "n_hash_mismatch": len(hash_mismatch),
            "hash_mismatch_uids": hash_mismatch[:20],
            "pass": bool(uids_match and not hash_mismatch
                         and len(recs) == len(manifest["records"]))}


# -- per-window candidate processing (multiprocessing worker) -------------------------


def _process_window(task):
    """All candidates of one window on its raw corrupted series."""
    uid, series, rows = task
    x = np.asarray(series, dtype=np.float64)
    nm = raw_nan_mask(x)
    fm = finite_flatline_mask(x)
    layer = window_layer(nm, fm)
    gaps = gap_runs(nm)
    anchors = anchor_geometry(x, nm)
    mat = materialize_for_probe(x)
    mat_nan_n = int(raw_nan_mask(mat).sum())
    recs = []
    for row in rows:
        fam = row["family"]
        out = apply_action(x, Action[fam], **row["params"])
        out_hash = hash_array(out.series) if out.applicable else None
        rec = {
            "sample_uid": uid,
            "window_id": row["window_id"],
            "dataset": row["dataset"],
            "stratum": row["stratum"],
            "true_kind": row["true_kind"],
            "family": fam,
            "rung": row["rung"],
            "params": row["params"],
            "params_key": _pkey(row["params"]),
            "corrupted_hash": row["corrupted_hash"],
            "layer": layer,
            "raw_nan_mask_hash": mask_hash(nm),
            "raw_nan_fraction": float(nm.mean()),
            "raw_nan_n": int(nm.sum()),
            "finite_flatline_mask_hash": mask_hash(fm),
            "finite_flatline_n": int(fm.sum()),
            "gap_runs": gaps,
            "anchor_geometry": anchors,
            "materialized_nan_n": mat_nan_n,
            "table_missing_fraction": row.get("missing_fraction"),
            "output_hash_table": row.get("output_hash"),
            "output_hash_recomputed": out_hash,
            "output_hash_match": bool(out_hash == row.get("output_hash")),
            "eval_labels": {
                "beneficial": bool(row["beneficial"]),
                "safe": bool(row["safe"]),
                "beneficial_and_safe": bool(row["beneficial_and_safe"]),
                "harmful": bool(row["harmful"]),
                "true_loss": float(row["true_loss"]),
                "true_repair_gain": float(row["true_repair_gain"]),
            },
        }
        if fam == "IMPUTE":
            touched = missing_mask(x, min_run=int(row["params"]["min_run"]))
            touched_mat = missing_mask(mat,
                                       min_run=int(row["params"]["min_run"]))
            rec.update({
                "mask_origin": mask_origin(touched, nm, fm),
                "touched_n": int(touched.sum()),
                "touched_raw_nan_n": int((touched & nm).sum()),
                "touched_finite_flatline_n": int((touched & fm).sum()),
                "touched_other_finite_n":
                    int((touched & ~nm & ~fm).sum()),
                "touched_mask_hash_raw": mask_hash(touched),
                "touched_mask_hash_materialized": mask_hash(touched_mat),
                "touched_mask_differs_on_materialized":
                    bool(not np.array_equal(touched, touched_mat)),
                "raw_nan_erased_on_materialized":
                    bool(nm.any() and not np.any(touched_mat & nm)
                         and mat_nan_n == 0),
            })
        recs.append(rec)
    return recs


# -- aggregations -----------------------------------------------------------------


def _rate(rows, key):
    return float(np.mean([r["eval_labels"][key] for r in rows])) if rows else None


def _layer_oracle(win_recs, all_rows_by_uid):
    """Candidate oracle restricted to this layer's IMPUTE candidates.

    Denominator: the layer's contaminated windows that carry >= 1 IMPUTE
    candidate. Pick rule identical to the v3.3 unrestricted oracle
    (max true_repair_gain among beneficial_and_safe), but IMPUTE-only.
    """
    cont = [uid for uid in win_recs
            if win_recs[uid][0]["stratum"] == "contaminated"]
    if not cont:
        return {"n_contaminated_windows": 0, "bcov": None, "gain": None,
                "n_oracle_commits": 0}
    gains, improved = [], []
    for uid in cont:
        bs = [r for r in all_rows_by_uid[uid]
              if r["eval_labels"]["beneficial_and_safe"]]
        if bs:
            best = max(bs, key=lambda r: r["eval_labels"]["true_repair_gain"])
            gains.append(best["eval_labels"]["true_repair_gain"])
            improved.append(1.0)
        else:
            gains.append(0.0)
            improved.append(0.0)
    return {"n_contaminated_windows": len(cont),
            "bcov": float(np.mean(improved)),
            "gain": float(np.mean(gains)),
            "n_oracle_commits": int(sum(improved))}


def aggregate_layers(records):
    by_layer = defaultdict(list)
    for r in records:
        by_layer[r["layer"]].append(r)
    out = {}
    for layer in LAYERS:
        rows = by_layer.get(layer, [])
        win = {}
        for r in rows:
            win.setdefault(r["sample_uid"], []).append(r)
        gains = [r["eval_labels"]["true_repair_gain"] for r in rows]
        losses = [r["eval_labels"]["true_loss"] for r in rows]
        out[layer] = {
            "n_candidates": len(rows),
            "n_unique_windows": len(win),
            "by_source": dict(Counter(r["dataset"] for r in rows)),
            "by_true_corruption": dict(Counter(r["true_kind"] for r in rows)),
            "by_rung": dict(Counter(r["rung"] for r in rows)),
            "by_operator_mode": dict(Counter(r["params_key"] for r in rows)),
            "by_mask_origin": dict(Counter(r["mask_origin"] for r in rows)),
            "bs_rate": _rate(rows, "beneficial_and_safe"),
            "harmful_rate": _rate(rows, "harmful"),
            "mean_gain": float(np.mean(gains)) if gains else None,
            "median_gain": float(np.median(gains)) if gains else None,
            "mean_loss": float(np.mean(losses)) if losses else None,
            "median_loss": float(np.median(losses)) if losses else None,
            "impute_only_candidate_oracle": _layer_oracle(win, win),
        }
    return out


def locate_harmful(harmful_commits, rec_index):
    """Join a harmful-commit ledger to the audit records; report layers."""
    out = []
    for c in harmful_commits:
        k = (c["sample_uid"], c["rung"], _pkey(c["params"]))
        rec = rec_index.get(k)
        entry = {
            "sample_uid": c["sample_uid"],
            "dataset": c["dataset"],
            "stratum": c["stratum"],
            "true_kind": c["true_kind"],
            "rung": c["rung"],
            "params_key": _pkey(c["params"]),
            "true_loss": float(c["true_loss"]),
            "true_repair_gain": float(c["true_repair_gain"]),
            "matched_audit_record": rec is not None,
        }
        if rec is not None:
            entry.update({
                "layer": rec["layer"],
                "mask_origin": rec["mask_origin"],
                "raw_nan_n": rec["raw_nan_n"],
                "finite_flatline_n": rec["finite_flatline_n"],
                "touched_n": rec["touched_n"],
                "touched_finite_flatline_n": rec["touched_finite_flatline_n"],
                "touched_other_finite_n": rec["touched_other_finite_n"],
                "gap_runs": rec["gap_runs"],
                "anchor_geometry": rec["anchor_geometry"],
            })
        out.append(entry)
    return out


def unrestricted_oracle_picks(rows):
    """Recompute the v3.3 unrestricted oracle picks from the candidate table
    (same rule as v33_compare_arms._decisions 'oracle': per window, max
    true_repair_gain among beneficial_and_safe, RESEGMENT closed)."""
    by_uid = defaultdict(list)
    for r in rows:
        by_uid[r["sample_uid"]].append(r)
    picks = {}
    for uid, rs in by_uid.items():
        bs = [r for r in rs
              if r["beneficial_and_safe"] and r["family"] in EPISODE_FAMILY_ORDER]
        picks[uid] = (max(bs, key=lambda r: r["true_repair_gain"])
                      if bs else None)
    return picks


def oracle_gain_decomposition(picks, rec_index, uid_layer, real_uids):
    """Question 3: where the unrestricted oracle's gain comes from."""
    by_family = defaultdict(lambda: [0, 0.0])
    by_source = defaultdict(lambda: [0, 0.0])
    by_layer = defaultdict(lambda: [0, 0.0])
    by_origin = defaultdict(lambda: [0, 0.0])
    total = 0.0
    n = 0
    for uid in sorted(real_uids):
        p = picks.get(uid)
        if p is None:
            continue
        g = float(p["true_repair_gain"])
        total += g
        n += 1
        by_family[p["family"]][0] += 1
        by_family[p["family"]][1] += g
        by_source[p["dataset"]][0] += 1
        by_source[p["dataset"]][1] += g
        layer = uid_layer.get(uid, "no_impute_candidate")
        by_layer[layer][0] += 1
        by_layer[layer][1] += g
        if p["family"] == "IMPUTE":
            k = (uid, p["rung"], _pkey(p["params"]))
            rec = rec_index.get(k)
            origin = rec["mask_origin"] if rec else "unmatched"
            by_origin[origin][0] += 1
            by_origin[origin][1] += g

    def _fin(d):
        return {k: {"n_commits": v[0], "gain_mass": v[1],
                    "gain_share": (v[1] / total if total else None)}
                for k, v in sorted(d.items())}

    return {"n_oracle_commits": n, "total_gain_mass": total,
            "by_family": _fin(by_family), "by_source": _fin(by_source),
            "by_window_layer": _fin(by_layer),
            "impute_commits_by_mask_origin": _fin(by_origin)}


# -- digest-only mode (two-process determinism gate) ----------------------------------


def run_mask_digest(out_path):
    t0 = time.time()
    recs, dropped = rebuild_corpus()
    digest = digest_of_windows([(r["sample_uid"], r["series"]) for r in recs])
    payload = {"n_windows": digest["n_windows"], "sha256": digest["sha256"],
               "records": digest["records"],
               "runtime_sec": time.time() - t0}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, sort_keys=True)
    print(f"[mask-digest] n={digest['n_windows']} "
          f"sha256={digest['sha256']} -> {out_path}", flush=True)
    print("___V38_MASK_DIGEST_DONE___", flush=True)
    return 0


# -- main -------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=16)
    ap.add_argument("--mask-digest", default=None,
                    help="digest-only mode: write per-window raw-mask digest "
                         "to this path and exit")
    ap.add_argument("--digest-a", default=None)
    ap.add_argument("--digest-b", default=None)
    args = ap.parse_args()

    if args.mask_digest:
        return run_mask_digest(args.mask_digest)

    t0 = time.time()

    # Gate 0: Part A replay must have passed before any Part B conclusion.
    replay_gate = {"pass": False}
    if REPLAY_PATH.exists():
        rep = json.load(REPLAY_PATH.open(encoding="utf-8"))
        replay_gate = {
            "pass": bool(rep.get("all_replays_pass")),
            "r1_pass": rep["r1_v33_unrestricted_oracle"]["pass"],
            "r2_pass": rep["r2_v37_constrained_oracles"]["pass"],
            "r3_pass": rep["r3_pics_incumbent"]["pass"],
            "replay_file": rep.get("phase"),
        }
    else:
        replay_gate["fatal"] = f"{REPLAY_PATH.name} missing; run Part A first"
    print(f"[gate replay] pass={replay_gate['pass']}", flush=True)

    # Rebuild + verify the raw corpus.
    t1 = time.time()
    recs, dropped = rebuild_corpus()
    print(f"[rebuild] {len(recs)} windows in {time.time() - t1:.1f}s "
          f"(dropped {dropped})", flush=True)
    manifest = json.load(MANIFEST_PATH.open(encoding="utf-8"))
    uid_gate = verify_against_manifest(recs, manifest)
    print(f"[gate uids] pass={uid_gate['pass']} "
          f"rebuilt={uid_gate['n_rebuilt']} manifest={uid_gate['n_manifest']}",
          flush=True)

    rows = [json.loads(l) for l in ROWS_PATH.open(encoding="utf-8")]
    impute = [r for r in rows if r["family"] == "IMPUTE"]
    non_impute = [r for r in rows if r["family"] != "IMPUTE"]
    print(f"{len(rows)} candidates: {len(impute)} IMPUTE, "
          f"{len(non_impute)} non-IMPUTE", flush=True)

    # Candidate table <-> rebuilt windows join, with hash verification.
    by_hash = defaultdict(list)
    for r in recs:
        by_hash[r["corrupted_hash"]].append(r)
    uid_series, join_problems = {}, []
    for row in rows:
        uid = row["sample_uid"]
        if uid in uid_series:
            continue
        cands = by_hash.get(row["corrupted_hash"], [])
        ok = [c for c in cands if c["sample_uid"] == uid]
        if len(ok) != 1:
            join_problems.append(uid)
            continue
        uid_series[uid] = ok[0]["series"]
    join_ok = not join_problems
    print(f"[join] matched {len(uid_series)} windows, "
          f"problems {len(join_problems)}", flush=True)

    # Process every candidate (IMPUTE audit + non-IMPUTE drift check).
    by_uid_rows = defaultdict(list)
    for row in rows:
        by_uid_rows[row["sample_uid"]].append(row)
    work = [(uid, uid_series[uid], by_uid_rows[uid])
            for uid in sorted(by_uid_rows) if uid in uid_series]
    t2 = time.time()
    if args.n_jobs > 1 and len(work) > 1:
        with ProcessPoolExecutor(max_workers=args.n_jobs) as ex:
            per_uid = list(ex.map(_process_window, work, chunksize=8))
    else:
        per_uid = [_process_window(w) for w in work]
    all_recs = [rec for recs_ in per_uid for rec in recs_]
    print(f"[process] {len(all_recs)} candidate records in "
          f"{time.time() - t2:.1f}s (n_jobs={args.n_jobs})", flush=True)

    # Gate: non-IMPUTE output hashes must not drift.
    drift = [r for r in all_recs
             if r["family"] != "IMPUTE" and not r["output_hash_match"]]
    impute_drift = [r for r in all_recs
                    if r["family"] == "IMPUTE" and not r["output_hash_match"]]
    drift_gate = {"n_non_impute_checked": len(non_impute),
                  "n_drift": len(drift),
                  "drift_examples": [
                      {"sample_uid": r["sample_uid"], "family": r["family"],
                       "rung": r["rung"], "params_key": r["params_key"]}
                      for r in drift[:20]],
                  "n_impute_drift": len(impute_drift),
                  "impute_drift_examples": [
                      {"sample_uid": r["sample_uid"], "rung": r["rung"],
                       "params_key": r["params_key"]}
                      for r in impute_drift[:20]],
                  "pass": bool(not drift and not impute_drift)}
    print(f"[gate output-hash] non-IMPUTE drift {len(drift)}, "
          f"IMPUTE drift {len(impute_drift)}, pass={drift_gate['pass']}",
          flush=True)

    # Gate: two-process raw-mask determinism.
    # same coverage as digest-only mode: every rebuilt window, not just the
    # ones carrying candidates
    inproc = digest_of_windows([(r["sample_uid"], r["series"]) for r in recs])
    det_gate = {"in_process_sha256": inproc["sha256"],
                "in_process_n_windows": inproc["n_windows"]}
    det_gate["pass"] = False
    if args.digest_a and args.digest_b:
        da = json.load(open(args.digest_a, encoding="utf-8"))
        db = json.load(open(args.digest_b, encoding="utf-8"))
        same_ab = da["records"] == db["records"]
        same_ai = da["records"] == inproc["records"]
        det_gate.update({
            "process_a_sha256": da["sha256"], "process_b_sha256": db["sha256"],
            "a_equals_b": bool(same_ab),
            "a_equals_in_process": bool(same_ai),
            "pass": bool(same_ab and same_ai
                         and da["sha256"] == db["sha256"]
                         == inproc["sha256"]),
        })
    else:
        det_gate["note"] = ("digest files not supplied; pass stays False "
                            "until two independent process digests are "
                            "compared")
    print(f"[gate determinism] pass={det_gate['pass']}", flush=True)

    # IMPUTE records file, one line per candidate.
    impute_recs = [r for r in all_recs if r["family"] == "IMPUTE"]
    impute_recs.sort(key=lambda r: (r["sample_uid"], r["params_key"]))
    with OUT_RECORDS.open("w", encoding="utf-8") as f:
        for r in impute_recs:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    print(f"[records] {len(impute_recs)} IMPUTE records -> "
          f"{OUT_RECORDS.name}", flush=True)

    rec_index = {(r["sample_uid"], r["rung"], r["params_key"]): r
                 for r in impute_recs}
    uid_layer = {r["sample_uid"]: r["layer"] for r in impute_recs}

    layers = aggregate_layers(impute_recs)

    # Materialisation-erasure evidence.
    erasure = {
        "n_candidates_with_raw_nan": sum(r["raw_nan_n"] > 0
                                         for r in impute_recs),
        "n_candidates_materialized_has_zero_nan":
            sum(r["materialized_nan_n"] == 0 for r in impute_recs),
        "n_touched_mask_differs_on_materialized":
            sum(r["touched_mask_differs_on_materialized"]
                for r in impute_recs),
        "n_raw_nan_erased_on_materialized":
            sum(r["raw_nan_erased_on_materialized"] for r in impute_recs),
        "note": "masks in this audit always come from the raw corrupted "
                "series; materialize_for_probe forward-fills NaN "
                "(src/introact_ts/probe.py:93-122), which is exactly why the "
                "materialised series is never used for mask semantics",
    }

    # Q2: v3.6 harmful IMPUTE (23) layer placement.
    v36_probe = json.load(V36_PROBE_PATH.open(encoding="utf-8"))
    v36_ledger = [c for c in v36_probe["attribution"]["harmful_commit_ledger"]
                  if c["family"] == "IMPUTE"]
    v36_located = locate_harmful(v36_ledger, rec_index)

    # Q4: PICS harmful IMPUTE (27) layer placement.
    v33_harmful = json.load(V33_HARMFUL_PATH.open(encoding="utf-8"))
    pics_ledger = [c for c in v33_harmful["PICS_joint_relabel"]
                   ["harmful_commits"] if c["family"] == "IMPUTE"]
    pics_located = locate_harmful(pics_ledger, rec_index)

    # Q3: unrestricted oracle gain decomposition.
    picks = unrestricted_oracle_picks(rows)
    real_uids = {r["sample_uid"] for r in rows
                 if not r["dataset"].startswith("ood:")}
    decomp = oracle_gain_decomposition(picks, rec_index, uid_layer, real_uids)
    # cross-check against the Part A replay picks, when available
    oracle_xcheck = {"pass": None}
    if REPLAY_PATH.exists():
        rep = json.load(REPLAY_PATH.open(encoding="utf-8"))
        mismatch = []
        align = rep.get("alignment") or []
        for entry in align:
            uid = entry["sample_uid"]
            p = picks.get(uid)
            got = None if p is None else (
                p["family"], p["rung"], _pkey(p["params"]))
            ref = entry["oracle_unrestricted"]
            refk = None if ref is None else (
                ref["family"], ref["rung"], ref["params_key"])
            if got != refk:
                mismatch.append(uid)
        oracle_xcheck = {"pass": not mismatch, "n_mismatch": len(mismatch),
                         "mismatch_uids": mismatch[:20],
                         "note": "Part B recomputed picks vs Part A replay "
                                 "picks, per sample_uid"}

    # The four pre-registered answers.
    n_layer = {l: layers[l]["n_candidates"] for l in LAYERS}
    touched_nan = sum(r["touched_raw_nan_n"] > 0 for r in impute_recs)
    touched_flat = sum(r["touched_finite_flatline_n"] > 0 for r in impute_recs)
    q1 = {
        "question": "missing_mask/op_impute candidates: actual NaN vs finite "
                    "flatline",
        "code_refs": {
            "missing_mask": "src/introact_ts/actions.py:82-119 (NaN at line "
                            "99; frozen-run detection at 100-119)",
            "MIN_FLATLINE_RUN": "src/introact_ts/actions.py:25 (=16)",
            "op_impute": "src/introact_ts/actions.py:262-329 (mask at line "
                         "280, linear fill at 290-291, seasonal at 293-314)",
            "flatline_injection": "experiments/corpus.py:118-122 "
                                  "(length 24..50 at T=512)",
        },
        "candidates_by_window_layer": n_layer,
        "n_candidates_touched_mask_contains_raw_nan": touched_nan,
        "n_candidates_touched_mask_contains_finite_flatline": touched_flat,
        "mask_origin_distribution": dict(
            Counter(r["mask_origin"] for r in impute_recs)),
    }
    q2 = {
        "question": "v3.6's 23 harmful IMPUTE commits: layer placement",
        "source": "results/v36_pair_probe.json "
                  "attribution.harmful_commit_ledger (family == IMPUTE); "
                  "ledger written by experiments/v36_pair_ranker_probe.py "
                  "main (decision arm PAIR_episode_relative/hgb)",
        "n_ledger": len(v36_ledger),
        "layer_distribution": dict(Counter(
            e.get("layer", "unmatched") for e in v36_located)),
        "mask_origin_distribution": dict(Counter(
            e.get("mask_origin", "unmatched") for e in v36_located)),
        "entries": v36_located,
    }
    q3 = {
        "question": "where the unrestricted oracle's gain comes from",
        "oracle_rule": "per window max true_repair_gain among "
                       "beneficial_and_safe, family in EPISODE_FAMILY_ORDER "
                       "(v33_compare_arms._decisions, 'oracle' branch)",
        "decomposition": decomp,
        "crosscheck_vs_partA_replay": oracle_xcheck,
    }
    pics_mask_mixed = sum(
        1 for e in pics_located
        if e.get("mask_origin") and ("finite_flatline" in e["mask_origin"]
                                     or "other_finite" in e["mask_origin"]))
    pics_no_nan = sum(1 for e in pics_located
                      if e.get("raw_nan_n") == 0)
    q4 = {
        "question": "are PICS harmful IMPUTE commits mainly caused by mask "
                    "semantics mixing",
        "source": "results/v33_clean_rerun_harmful.json "
                  "PICS_joint_relabel.harmful_commits (family == IMPUTE, "
                  "27 commits)",
        "n_ledger": len(pics_ledger),
        "layer_distribution": dict(Counter(
            e.get("layer", "unmatched") for e in pics_located)),
        "mask_origin_distribution": dict(Counter(
            e.get("mask_origin", "unmatched") for e in pics_located)),
        "n_touched_mask_includes_finite_or_other": pics_mask_mixed,
        "n_window_without_any_raw_nan": pics_no_nan,
        "entries": pics_located,
    }
    q4["interpretation"] = (
        f"{pics_mask_mixed}/{len(pics_located)} PICS harmful IMPUTE commits "
        f"have a touched mask that reaches beyond raw NaN (finite flatline "
        f"or other finite points), and {pics_no_nan}/{len(pics_located)} sit "
        f"in windows with no raw NaN at all; see layer_distribution for the "
        f"mutually exclusive placement.")

    audit = {
        "phase": "v3.8 Phase 0 Part B: IMPUTE candidate mask-semantics audit",
        "preregistration": "docs/v3_8_fact_preregistration.md §2-§3",
        "definitions": {
            "flatline_k": FLATLINE_K,
            "flatline_eps": FLATLINE_EPS,
            "flatline_k_derivation": (
                "k=16 matches MIN_FLATLINE_RUN (src/introact_ts/"
                "actions.py:25), the sensitivity at which the production "
                "IMPUTE mask actually operates; injected corpus flatlines are "
                "24..50 long (experiments/corpus.py:118-122), so all of them "
                "clear k with margin"),
            "layers": "mutually exclusive, window-level, from the RAW "
                      "corrupted series: actual_nan_only / "
                      "finite_flatline_only / mixed / neither",
            "harmful": f"true_loss > {HARM_LOSS}",
            "mask_origin": "composition of the candidate's missing_mask "
                           "(recomputed on the raw series at the candidate's "
                           "own min_run) against raw_nan / finite_flatline / "
                           "other_finite points",
        },
        "reconstruction": {
            "method": "build_calibration.build(n=1600, seed=101, "
                      "source='mixed'); windows matched to candidates by "
                      "corrupted_hash AND sample_uid",
            "n_windows_rebuilt": len(recs),
            "n_candidate_windows_matched": len(uid_series),
            "join_problems": join_problems[:20],
            "manifest_gate": uid_gate,
        },
        "materialization_erasure_evidence": erasure,
        "n_impute_candidates": len(impute_recs),
        "layers": layers,
        "answers": {"q1": q1, "q2": q2, "q3": q3, "q4": q4},
        "input_hashes": {
            "v33_training_data": _sha256(ROWS_PATH),
            "p0_corpus_manifest_a": _sha256(MANIFEST_PATH),
            "v36_pair_probe": _sha256(V36_PROBE_PATH),
            "v33_clean_rerun_harmful": _sha256(V33_HARMFUL_PATH),
        },
        "code_hashes": {
            "experiments/v38_impute_mask_audit.py": _sha256(
                Path(__file__).resolve()),
            "src/introact_ts/actions.py": _sha256(
                ROOT / "src" / "introact_ts" / "actions.py"),
            "src/introact_ts/probe.py": _sha256(
                ROOT / "src" / "introact_ts" / "probe.py"),
            "experiments/corpus.py": _sha256(ROOT / "experiments"
                                             / "corpus.py"),
            "experiments/build_calibration.py": _sha256(
                ROOT / "experiments" / "build_calibration.py"),
        },
        "runtime_sec": time.time() - t0,
    }
    with OUT_AUDIT.open("w", encoding="utf-8") as f:
        json.dump(audit, f, indent=1, ensure_ascii=False, default=str)

    gates = {
        "replay_all_exact_1e-9": replay_gate,
        "corpus_1599_uids_and_hashes_match_manifest": uid_gate,
        "non_impute_output_hash_no_drift": drift_gate,
        "raw_mask_two_process_hash_identical": det_gate,
    }
    all_pass = all(g.get("pass") for g in gates.values())
    manifest_out = {
        "phase": "v3.8 Phase 0 integrity manifest",
        "preregistration": "docs/v3_8_fact_preregistration.md §3 "
                           "(Phase-0 完整性门)",
        "gates": gates,
        "candidate_table_join_ok": bool(join_ok),
        "all_pass": bool(all_pass),
        "output_sha256": {
            "results/v38_oracle_replay.json": (_sha256(REPLAY_PATH)
                                               if REPLAY_PATH.exists()
                                               else None),
            "results/v38_impute_mask_audit.json": _sha256(OUT_AUDIT),
            "results/v38_impute_mask_records.jsonl": _sha256(OUT_RECORDS),
        },
        "runtime_sec": time.time() - t0,
    }
    with OUT_MANIFEST.open("w", encoding="utf-8") as f:
        json.dump(manifest_out, f, indent=1, ensure_ascii=False, default=str)
    print(f"[manifest] all_pass={all_pass} -> {OUT_MANIFEST.name}",
          flush=True)
    print(f"[done] runtime={time.time() - t0:.1f}s", flush=True)
    print("___V38_IMPUTE_MASK_AUDIT_DONE___", flush=True)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
