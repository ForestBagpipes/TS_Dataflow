"""Compute action-family oracle headroom with canonical NMSE.

Reuses the candidate list from `results/family_scores.jsonl` (routed by the
existing proposer) but recomputes damage / repair labels with the canonical
uncentered finite-mask NMSE. Output records carry the full provenance contract
fields so the file can be linked back to the frozen corpus manifest.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from build_calibration import build as build_calibration  # noqa: E402
from metrics_common import canonical_nmse, damage, repair_rmsd, ref_var  # noqa: E402
from introact_ts.actions import Action, apply_action  # noqa: E402
from introact_ts.policy import LADDER  # noqa: E402

#: Action family -> rung -> params mapping, mirrored from policy.LADDER.
#: Only rungs present in family_scores.jsonl are needed.


def _params_for(family: str, rung: str) -> dict:
    action = Action(family)
    return dict(LADDER.get(action, {}).get(rung, {}))


def _hash_array(a: np.ndarray) -> str:
    x = np.asarray(a, dtype=np.float64).copy()
    x[~np.isfinite(x)] = np.nan
    return hashlib.sha256(np.round(x, 6).tobytes()).hexdigest()


def sample_uid(window) -> str:
    clean = window.clean_series
    corrupted = window.series
    clean_hash = _hash_array(clean) if clean is not None else "no_clean"
    corrupted_hash = _hash_array(corrupted)
    true_kind = window.contamination or "null"
    return f"{window.dataset}:{window.stratum}:{true_kind}:{clean_hash}:{corrupted_hash}"


def _jsonify(obj):
    """Convert numpy scalars/arrays to JSON-safe Python types."""
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    return obj


def evaluate_candidate(window, family, rung):
    """Apply one candidate and return true labels under canonical NMSE."""
    x = np.asarray(window.series, dtype=np.float64)
    c = np.asarray(window.clean_series, dtype=np.float64)
    action = Action(family)
    params = _params_for(family, rung)
    outcome = apply_action(x, action, **params)
    if not outcome.applicable:
        return {"applicable": False, "note": outcome.note}

    y = np.asarray(outcome.series, dtype=np.float64)
    lo = int(outcome.params.get("lo", 0)) if action is Action.RESEGMENT else 0
    hi = lo + len(y)
    rv = ref_var(c)
    before = canonical_nmse(x, c, rv)
    after = canonical_nmse(y, c[lo:hi], rv)
    worse = 1.0 if after > before + 1e-9 else 0.0
    discard = 1.0 - (hi - lo) / len(x)
    loss = damage(worse, discard)
    repair_gain = before - after
    beneficial = 1.0 if repair_gain > 1e-9 else 0.0
    safe = 1.0 if loss <= 0.03 else 0.0
    beneficial_and_safe = 1.0 if beneficial and safe else 0.0
    rmsd = repair_rmsd(y, c[lo:hi])

    return _jsonify({
        "applicable": True,
        "before_nmse": float(before),
        "after_nmse": float(after),
        "worse_binary": float(worse),
        "discard_share": float(discard),
        "true_loss": float(loss),
        "true_repair_gain": float(repair_gain),
        "beneficial": float(beneficial),
        "safe": float(safe),
        "beneficial_and_safe": float(beneficial_and_safe),
        "repair_rmsd": float(rmsd),
        "touched": outcome.touched,
        "cost": float(outcome.cost),
        "params": dict(outcome.params),
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default=str(ROOT / "results" / "family_scores.jsonl"))
    ap.add_argument("--manifest", default=str(ROOT / "results" / "p0_corpus_manifest_a.json"))
    ap.add_argument("--out", default=str(ROOT / "results" / "oracle_headroom.jsonl"))
    args = ap.parse_args()

    manifest_data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    manifest_hash = hashlib.sha256(
        Path(args.manifest).read_bytes()).hexdigest()
    manifest = {r["window_id"]: r for r in manifest_data["records"]}

    windows, _ = build_calibration(n=1600, seed=101, source="mixed", verbose=False)
    byid = {w.window_id: w for w in windows}

    # Code hash: the scripts that matter for this experiment.
    code_files = [
        "experiments/oracle_headroom.py",
        "experiments/metrics_common.py",
        "experiments/build_calibration.py",
        "src/introact_ts/actions.py",
        "src/introact_ts/policy.py",
    ]
    code_hashes = {}
    for rel in code_files:
        p = ROOT / rel
        if p.exists():
            code_hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    config = {
        "scores": str(args.scores),
        "manifest": str(args.manifest),
        "n": 1600, "seed": 101, "source": "mixed",
    }
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True).encode()).hexdigest()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as out_f:
        with Path(args.scores).open(encoding="utf-8") as in_f:
            for line in in_f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                wid = int(rec["window_id"])
                w = byid.get(wid)
                m = manifest.get(wid)
                if w is None or m is None:
                    continue
                for cand in rec["candidates"]:
                    family = cand["family"]
                    rung = cand.get("rung", "other")
                    labels = evaluate_candidate(w, family, rung)
                    if not labels["applicable"]:
                        continue
                    row = {
                        "window_id": wid,
                        "sample_uid": sample_uid(w),
                        "dataset": w.dataset,
                        "stratum": w.stratum,
                        "true_kind": w.contamination or "null",
                        "corrupted_hash": _hash_array(w.series),
                        "clean_hash": _hash_array(w.clean_series) if w.clean_series is not None else None,
                        "manifest_hash": manifest_hash,
                        "code_hashes": code_hashes,
                        "config_hash": config_hash,
                        "family": family,
                        "rung": rung,
                        **labels,
                    }
                    out_f.write(json.dumps(row) + "\n")
                out_f.flush()

    print(f"___ORACLE_HEADROOM_DONE___ wrote {args.out}")


if __name__ == "__main__":
    main()
