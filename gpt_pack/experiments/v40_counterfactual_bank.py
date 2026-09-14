"""v4.0 COUNTERACT-TS Phase 0/1: integrity, budget carry-over, and the
Counterfactual Action Bank pilot.

Pre-registered in ``docs/v4_0_counteract_preregistration.md`` §2-§3. All
computation runs on the server; API 0. Read-only against every frozen v3.x
artifact.

Red-line discipline (§2), enforced structurally:

- candidate stages (``parents``/``candidates``/``tsicl``/``fetch-data``) never
  call ``compute_action_labels`` and never write label fields; ``freeze``
  digests every candidate output hash before ``evaluate`` may join labels;
- labels live only under the ``labels`` key of the final records
  (``EVAL_NAMESPACE``); true_kind/clean/source_id never appear as model-input
  fields (see ``MODEL_INPUT_FIELDS`` in ``experiments/v40_action_critic.py``);
- training windows are fresh draws from the sources, content-hash isolated
  from the frozen 1599-window corpus and the 771-window evaluation frame;
  the concrete intersection assertions are written to
  ``results/v40_bank_isolation.json`` by the ``parents`` stage.

Training-distribution note (pre-registered extension): the bank's
``missing_block`` injector covers 5%-50% of the window, while the frozen
evaluation corpus injector writes 25-63/512 (~5%-12%). The extension to 50%
is intentional -- the bank must teach the critic about gaps far longer than
anything the evaluation corpus contains -- and is recorded in the bank
manifest. Nothing about the frozen evaluation path changes.

Stages:
    python experiments/v40_counterfactual_bank.py fetch-data
    python experiments/v40_counterfactual_bank.py integrity
    python experiments/v40_counterfactual_bank.py budget
    python experiments/v40_counterfactual_bank.py manifest
    python experiments/v40_counterfactual_bank.py parents
    python experiments/v40_counterfactual_bank.py candidates
    python experiments/v40_counterfactual_bank.py tsicl        # GPU env
    python experiments/v40_counterfactual_bank.py freeze
    python experiments/v40_counterfactual_bank.py evaluate
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import _spread  # noqa: E402
from v33_labels import compute_action_labels, hash_array  # noqa: E402
from v38_impute_mask_audit import (  # noqa: E402
    rebuild_corpus, verify_against_manifest, raw_nan_mask, mask_hash,
)
import v38_explicit_impute_probe as v38p  # noqa: E402
from introact_ts.actions import (  # noqa: E402
    Action, apply_action, missing_mask, _mask_runs,
)
from introact_ts.probe import materialize_for_probe  # noqa: E402

# -- frozen inputs (Phase 0 integrity) ----------------------------------------

ROWS_PATH = ROOT / "results" / "v33_training_data.jsonl"
MANIFEST_PATH = ROOT / "results" / "p0_corpus_manifest_a.json"
FROZEN_V33 = ROOT / "results" / "v33_clean_rerun.json"
REPLAY_V38 = ROOT / "results" / "v38_oracle_replay.json"
MASK_RECORDS = ROOT / "results" / "v38_impute_mask_records.jsonl"
EXPLICIT_RECORDS = ROOT / "results" / "v38_explicit_impute_records.jsonl"
EXPLICIT_PROBE = ROOT / "results" / "v38_explicit_impute_probe.json"
V39_REPLAY = ROOT / "results" / "v39_phase0_replay.json"
V39_RECORDS = ROOT / "results" / "v39_phase0_records.jsonl"
V39_BUDGET = ROOT / "results" / "v39_target_budget.json"
V39_P0_MANIFEST = ROOT / "results" / "v39_phase0_manifest.json"
V39_CANDIDATES = ROOT / "results" / "v39_longgap_candidates.jsonl"
V39_CAND_FREEZE = ROOT / "results" / "v39_longgap_candidates_freeze.json"
V39_PROBE = ROOT / "results" / "v39_longgap_probe.json"
V39_ORACLE = ROOT / "results" / "v39_longgap_oracle.json"
V39_MODEL_MANIFEST = ROOT / "results" / "v39_model_manifest.json"

#: The one pre-registered rescue (§4, §11.3 F11) scales the pilot to ~20k
#: episodes. It is opt-in through the environment so the frozen Phase 1
#: constants, outputs and hashes are untouched: with V40_BANK_SCALE set,
#: every count is multiplied and every output path gains a `rescue_` stem.
#: Nothing about the mechanism set, the severity ranges or the action set
#: changes -- re-tuning those after seeing the frozen-89 result is what §1.4
#: forbids.
BANK_SCALE = int(os.environ.get("V40_BANK_SCALE", "1"))

#: Rescue outputs live beside the pilot's, never on top of them.
_STEM = "v40_" if BANK_SCALE == 1 else "v40_rescue_"

OUT_INTEGRITY = ROOT / "results" / "v40_integrity.json"
OUT_BUDGET = ROOT / "results" / "v40_target_budget.json"
OUT_BANK_MANIFEST = ROOT / "results" / f"{_STEM}counterfactual_bank_manifest.json"
OUT_REGISTRY = ROOT / "results" / "v40_data_registry.json"
OUT_PARENTS_NPZ = ROOT / "results" / f"{_STEM}bank_parents.npz"
OUT_PARENTS_META = ROOT / "results" / f"{_STEM}bank_parents.jsonl"
OUT_ISOLATION = ROOT / "results" / f"{_STEM}bank_isolation.json"
OUT_PLAN = ROOT / "results" / f"{_STEM}bank_plan.json"
OUT_TSICL_WORKLIST = ROOT / "results" / f"{_STEM}bank_tsicl_worklist.json"
OUT_CANDIDATES = ROOT / "results" / f"{_STEM}bank_candidates.jsonl"
OUT_FREEZE = ROOT / "results" / f"{_STEM}bank_freeze.json"
OUT_BANK_RECORDS = ROOT / "results" / f"{_STEM}bank_records.jsonl"
OUT_REPORT = ROOT / "results" / f"{_STEM}bank_report.json"

TSICL_CKPT = ROOT / "third_party" / "checkpoints" / "tsicl" / "tsicl-v1.ckpt"
#: Frozen in v3.9 (results/v39_model_manifest.json); duplicated here so this
#: module does not import the v3.9 probe.
TSICL_CKPT_SHA256 = (
    "a67ae9f694c2a83cfc8e7ec41745ff4f41a4a76ee2b17172ec3430d8d29da431")

# -- bank design constants (frozen in the bank manifest) ----------------------

WINDOW_LEN = 512
BANK_SEED = 20260903
HARM_LOSS = 0.03
GAIN_EPS = 1e-9

MECHANISMS = ("missing_scattered", "missing_block", "spike", "noise",
              "flatline", "duplicate", "level_shift")
SEVERITIES = ("low", "mid", "high")

#: Per-mechanism severity parameter ranges (frozen). Fractions are of the
#: window length T=512 unless noted. missing_block reaches 50% of T -- the
#: intentional training-distribution extension recorded in the manifest.
SEVERITY_RANGES = {
    # fraction of points set to NaN
    "missing_scattered": {"low": (0.01, 0.02), "mid": (0.03, 0.05),
                          "high": (0.06, 0.10)},
    # single block length as a fraction of T
    "missing_block": {"low": (0.05, 0.12), "mid": (0.15, 0.30),
                      "high": (0.35, 0.50)},
    # (n_min, n_max, magnitude_min, magnitude_max) in spread units
    "spike": {"low": (2, 4, 3.0, 5.0), "mid": (5, 8, 4.0, 8.0),
              "high": (9, 14, 6.0, 10.0)},
    # additive gaussian noise level in spread units
    "noise": {"low": (0.2, 0.4), "mid": (0.5, 0.9), "high": (1.0, 1.5)},
    # frozen run length as a fraction of T
    "flatline": {"low": (0.03, 0.06), "mid": (0.08, 0.14),
                 "high": (0.16, 0.25)},
    # duplicated span length as a fraction of T
    "duplicate": {"low": (0.05, 0.10), "mid": (0.12, 0.20),
                  "high": (0.22, 0.33)},
    # level offset in spread units
    "level_shift": {"low": (1.5, 2.5), "mid": (2.5, 4.0),
                    "high": (4.0, 6.0)},
}

#: Episode counts (pilot, pre-registered 4,000-6,000): 7 mechanisms x 3
#: severities x 150, plus 630 mixed (15.0% of the total, inside the
#: pre-registered 10%-20% band), plus 420 clean controls (10.0%, the
#: protected class of the bank).
N_PER_CELL = 150
N_MIXED = 630
N_CLEAN = 420
N_TOTAL = 7 * 3 * N_PER_CELL + N_MIXED + N_CLEAN  # 4200
MAX_EPISODES_PER_PARENT = 2

if BANK_SCALE != 1:
    N_PER_CELL *= BANK_SCALE
    N_MIXED *= BANK_SCALE
    N_CLEAN *= BANK_SCALE
    N_TOTAL = 7 * 3 * N_PER_CELL + N_MIXED + N_CLEAN
    # More episodes per parent keeps the per-source window demand reachable:
    # the financial columns are short and the within-run dedup would other-
    # wise exhaust their usable start positions.
    MAX_EPISODES_PER_PARENT = 4

#: Action set (§3). family -> action names.
ACTIONS = ("keep", "fact_short", "tsicl_long", "impute_seasonal",
           "impute_linear_default", "impute_linear_conservative",
           "despike", "denoise")
ACTION_FAMILY = {
    "keep": "KEEP",
    "fact_short": "FACT_SHORT",
    "tsicl_long": "TSICL_LONG",
    "impute_seasonal": "IMPUTE",
    "impute_linear_default": "IMPUTE",
    "impute_linear_conservative": "IMPUTE",
    "despike": "DESPIKE",
    "denoise": "DENOISE",
}
#: Label-family argument handed to the frozen compute_action_labels path.
LABEL_FAMILY = {
    "keep": "KEEP",
    "fact_short": "IMPUTE",
    "tsicl_long": "IMPUTE",
    "impute_seasonal": "IMPUTE",
    "impute_linear_default": "IMPUTE",
    "impute_linear_conservative": "IMPUTE",
    "despike": "DESPIKE",
    "denoise": "DENOISE",
}
FACT_SHORT_MAX_GAP = 3
#: TSICL_LONG is semantically a long-gap filler: it is generated only when a
#: raw-NaN run of length >= TSICL_MIN_RUN exists (shorter runs are
#: FACT_SHORT/IMPUTE territory).
TSICL_MIN_RUN = 4
IMPUTE_PARAMS = {
    "impute_seasonal": {"method": "seasonal", "min_run": 8},
    "impute_linear_default": {"method": "linear", "min_run": 16},
    "impute_linear_conservative": {"method": "linear", "min_run": 32},
}

#: Six development sources (LODO-isolated) plus two new public sources
#: (training-only; registered in results/v40_data_registry.json).
DEV_SOURCES = ("ETTh1", "ETTh2", "ETTm1", "Crypto", "US Term Structure",
               "Oil Price")
PUBLIC_SOURCES = ("pub:electricity", "pub:traffic")
PUBLIC_FILES = {"pub:electricity": "electricity.txt.gz",
                "pub:traffic": "traffic.txt.gz"}
PUBLIC_DOWNLOADS = {
    "pub:electricity": {
        "url": ("https://raw.githubusercontent.com/laiguokun/"
                "multivariate-time-series-data/master/electricity/"
                "electricity.txt.gz"),
        "origin": ("UCI ElectricityLoadDiagrams20112014 (2011-2014, hourly, "
                   "321 clients)"),
        "license": ("CC BY 4.0 at the UCI origin; redistributed via the "
                    "laiguokun/multivariate-time-series-data GitHub mirror "
                    "(repository carries no explicit license)"),
    },
    "pub:traffic": {
        "url": ("https://raw.githubusercontent.com/laiguokun/"
                "multivariate-time-series-data/master/traffic/"
                "traffic.txt.gz"),
        "origin": ("Caltrans PeMS traffic occupancy (San Francisco Bay Area "
                   "freeways, 5-minute, 862 sensors)"),
        "license": ("Caltrans PeMS public data; redistributed via the "
                    "laiguokun/multivariate-time-series-data GitHub mirror "
                    "(repository carries no explicit license)"),
    },
}
GITHUB_API_COMMIT = ("https://api.github.com/repos/laiguokun/"
                     "multivariate-time-series-data/commits/master")
FETCH_TIME_BUDGET_SEC = 600

#: Field namespaces. Candidate-namespace fields are frozen before labels are
#: joined; evaluation-namespace fields exist only after ``evaluate``.
REQUIRED_RECORD_FIELDS = (
    "episode_uid", "clean_parent_uid", "source", "corruption", "severity",
    "family", "action", "candidate_hash", "input_hash", "mask_hash",
    "before_nmse", "after_nmse", "gain", "true_loss", "harmful",
    "beneficial_and_safe", "protected", "provenance",
)
EVAL_NAMESPACE = frozenset({
    "before_nmse", "after_nmse", "gain", "true_loss", "harmful",
    "beneficial_and_safe", "labels",
})
CANDIDATE_FORBIDDEN_KEYS = EVAL_NAMESPACE | frozenset({
    "true_kind", "clean", "clean_series", "clean_hash", "sample_uid",
})


# -- pure helpers (unit-tested locally) ---------------------------------------


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _first16_md5(series) -> str:
    """Position-collision key: identical starts share their first 16 values
    (same convention as build_calibration.ident, minus the dataset key)."""
    a = np.asarray(series, dtype=np.float64)[:16]
    return hashlib.md5(np.round(a, 6).tobytes()).hexdigest()


def episode_seed(idx: int) -> int:
    return (BANK_SEED * 1000003 + idx * 7919) % (2**31 - 1)


def parent_uid(source: str, channel: str, start: int, series) -> str:
    sha = hash_array(np.asarray(series, dtype=np.float64))
    return f"v40parent:{source}:{channel}:{start}:{sha[:12]}"


def episode_uid(idx: int, corruption: str, severity: str) -> str:
    return f"v40ep-{idx:05d}:{corruption}:{severity}"


def parent_split(uid: str) -> str:
    """Deterministic 80/10/10 train/val/test split by parent uid hash."""
    b = hashlib.sha256(uid.encode()).digest()[0]
    if b < 204:
        return "train"
    if b < 230:
        return "val"
    return "test"


def episode_plan(seed=BANK_SEED):
    """The frozen pilot plan: 3150 single-mechanism + 630 mixed + 420 clean.

    Mixed components are drawn at plan time and stored, so candidate
    generation is exactly reproducible from the plan file alone.
    """
    plan = []
    for mech in MECHANISMS:
        for sev in SEVERITIES:
            for _ in range(N_PER_CELL):
                plan.append({"corruption": mech, "severity": sev,
                             "components": None})
    rng = np.random.RandomState(seed ^ 0x5EED)
    for _ in range(N_MIXED):
        i, j = rng.choice(len(MECHANISMS), size=2, replace=False)
        comps = [[MECHANISMS[i], SEVERITIES[int(rng.randint(3))]],
                 [MECHANISMS[j], SEVERITIES[int(rng.randint(3))]]]
        plan.append({"corruption": "mixed", "severity": "mixed",
                     "components": comps})
    for _ in range(N_CLEAN):
        plan.append({"corruption": "none", "severity": "none",
                     "components": None})
    rng.shuffle(plan)
    for idx, e in enumerate(plan):
        e["idx"] = idx
        e["seed"] = episode_seed(idx)
        e["parent_idx"] = idx // MAX_EPISODES_PER_PARENT
    return plan


def nan_run_lengths(x) -> list:
    return [hi - lo for lo, hi in _mask_runs(raw_nan_mask(x))]


def action_gate(x, action: str) -> tuple:
    """Semantic applicability gate. Returns (gated_in, reason)."""
    x = np.asarray(x, dtype=np.float64)
    runs = nan_run_lengths(x)
    has_nan = bool(runs)
    if action == "keep":
        return True, "always"
    if action == "fact_short":
        ok = any(1 <= r <= FACT_SHORT_MAX_GAP for r in runs)
        return ok, ("raw-NaN run of length 1-3 present" if ok
                    else "no raw-NaN run of length 1-3")
    if action == "tsicl_long":
        ok = any(r >= TSICL_MIN_RUN for r in runs)
        return ok, (f"raw-NaN run >= {TSICL_MIN_RUN} present" if ok
                    else f"no raw-NaN run >= {TSICL_MIN_RUN}")
    if action in IMPUTE_PARAMS:
        ok = has_nan or bool(missing_mask(x).any())
        return ok, ("missing_mask non-empty (NaN or frozen run)" if ok
                    else "nothing missing or frozen")
    if action == "despike":
        return True, "always attempted; the detector decides"
    if action == "denoise":
        ok = not has_nan
        return ok, ("fully finite window" if ok
                    else "operator requires a fully finite window")
    raise ValueError(f"unknown action {action}")


def inject_bank(series, mechanism: str, severity: str,
                rng: np.random.RandomState) -> tuple:
    """One bank contamination at one severity. Returns (corrupted, mask).

    Same operator family as ``corpus.inject`` with severity-stratified ranges;
    missing_block deliberately extends to 50% of T (see module docstring).
    """
    x = np.asarray(series, dtype=np.float64).copy()
    T = len(x)
    mask = np.zeros(T, dtype=bool)
    s = _spread(x)
    rng_range = SEVERITY_RANGES[mechanism][severity]

    if mechanism == "missing_scattered":
        lo_f, hi_f = rng_range
        n = max(1, int(round(T * rng.uniform(lo_f, hi_f))))
        idx = rng.choice(np.arange(T // 10, T - T // 10),
                         size=min(n, T - T // 5), replace=False)
        x[idx] = np.nan
        mask[idx] = True

    elif mechanism == "missing_block":
        lo_f, hi_f = rng_range
        length = int(round(T * rng.uniform(lo_f, hi_f)))
        length = int(np.clip(length, 8, T // 2))
        lo = int(rng.randint(T // 8, T - length - T // 8))
        x[lo:lo + length] = np.nan
        mask[lo:lo + length] = True

    elif mechanism == "spike":
        n_lo, n_hi, m_lo, m_hi = rng_range
        n = int(rng.randint(n_lo, n_hi + 1))
        idx = rng.choice(np.arange(T // 12, T - T // 12), size=n,
                         replace=False)
        signs = rng.choice([-1.0, 1.0], size=n)
        x[idx] = x[idx] + signs * rng.uniform(m_lo, m_hi, size=n) * s
        mask[idx] = True

    elif mechanism == "noise":
        level = rng.uniform(*rng_range) * s
        x = x + rng.randn(T) * level
        mask[:] = True

    elif mechanism == "flatline":
        lo_f, hi_f = rng_range
        length = int(round(T * rng.uniform(lo_f, hi_f)))
        length = int(np.clip(length, 16, T // 2))
        lo = int(rng.randint(T // 8, T - length - T // 8))
        x[lo:lo + length] = x[lo]
        mask[lo:lo + length] = True

    elif mechanism == "duplicate":
        lo_f, hi_f = rng_range
        length = int(round(T * rng.uniform(lo_f, hi_f)))
        length = int(np.clip(length, 16, T // 3))
        src = int(rng.randint(0, T - 2 * length))
        dst = int(rng.randint(src + length, T - length))
        x[dst:dst + length] = x[src:src + length]
        mask[dst:dst + length] = True

    elif mechanism == "level_shift":
        lo = int(rng.randint(T // 3, 2 * T // 3))
        x[lo:] = x[lo:] + rng.choice([-1.0, 1.0]) * rng.uniform(*rng_range) * s
        mask[lo:] = True

    else:
        raise ValueError(f"unknown mechanism: {mechanism}")
    return x, mask


def apply_episode_corruption(clean, entry) -> tuple:
    """Reproducible corruption of one parent per its plan entry.

    Returns (dirty, mask). ``none`` is the clean control: dirty == clean,
    mask empty, and the episode is the bank's protected class.
    """
    rng = np.random.RandomState(int(entry["seed"]))
    if entry["corruption"] == "none":
        x = np.asarray(clean, dtype=np.float64).copy()
        return x, np.zeros(len(x), dtype=bool)
    if entry["corruption"] == "mixed":
        x = np.asarray(clean, dtype=np.float64).copy()
        mask = np.zeros(len(x), dtype=bool)
        for mech, sev in entry["components"]:
            x, m = inject_bank(x, mech, sev, rng)
            mask |= m
        return x, mask
    return inject_bank(clean, entry["corruption"], entry["severity"], rng)


def run_cpu_action(x, action: str):
    """Execute one CPU action. Returns (y, touched, applicable, params)."""
    x = np.asarray(x, dtype=np.float64)
    if action == "keep":
        return x.copy(), np.zeros(len(x), dtype=bool), True, {}
    if action == "fact_short":
        res = v38p.impute_explicit_linear(x, max_gap=FACT_SHORT_MAX_GAP)
        return res["series"], res["touched"], bool(res["applicable"]), \
            {"method": "explicit_linear", "max_gap": FACT_SHORT_MAX_GAP,
             "n_filled": int(res["n_filled"])}
    if action in IMPUTE_PARAMS:
        out = apply_action(x, Action.IMPUTE, **IMPUTE_PARAMS[action])
        touched = (np.asarray(out.touched, dtype=bool)
                   if out.touched is not None
                   else np.zeros(len(x), dtype=bool))
        return out.series, touched, bool(out.applicable), \
            {**IMPUTE_PARAMS[action],
             "operator_n_filled": int(out.params.get("n_filled", 0))}
    if action == "despike":
        out = apply_action(x, Action.DESPIKE)
        touched = (np.asarray(out.touched, dtype=bool)
                   if out.touched is not None
                   else np.zeros(len(x), dtype=bool))
        return out.series, touched, bool(out.applicable), dict(out.params)
    if action == "denoise":
        out = apply_action(x, Action.DENOISE)
        touched = np.zeros(len(x), dtype=bool)  # whole-window operator
        return out.series, touched, bool(out.applicable), dict(out.params)
    raise ValueError(f"unknown cpu action {action}")


def rebuild_tsicl_output(x, fill_values):
    """KEEP-materialised base + stored fills at raw-NaN positions (v3.9
    candidate contract: only raw NaN may be written, drift exactly 0)."""
    x = np.asarray(x, dtype=np.float64)
    nm = raw_nan_mask(x)
    pos = np.flatnonzero(nm)
    fill = np.asarray(fill_values, dtype=np.float64)
    assert len(fill) == len(pos), "fill/NaN-position count mismatch"
    y = materialize_for_probe(x)
    y[pos] = fill
    obs = np.isfinite(x)
    assert np.array_equal(y[obs], x[obs]), "observed-support drift"
    touched = nm.copy()
    return y, touched


def validate_record(rec: dict, labeled: bool = True) -> list:
    """Schema check. Returns the list of violations (empty = valid)."""
    problems = []
    for k in REQUIRED_RECORD_FIELDS:
        if k not in rec:
            problems.append(f"missing field {k}")
    if not labeled:
        bad = CANDIDATE_FORBIDDEN_KEYS & set(rec)
        if bad:
            problems.append(f"candidate-namespace violation: {sorted(bad)}")
    if labeled and rec.get("applicable") and rec.get("labels") is None:
        problems.append("applicable record without joined labels")
    return problems


def digest_records(recs) -> str:
    """Deterministic digest over the candidate-namespace slim table."""
    slim = sorted(({"episode_uid": r["episode_uid"], "action": r["action"],
                    "supported": r["supported"], "applicable": r["applicable"],
                    "candidate_hash": r["candidate_hash"],
                    "input_hash": r["input_hash"],
                    "mask_hash": r["mask_hash"]} for r in recs),
                  key=lambda r: (r["episode_uid"], r["action"]))
    return hashlib.sha256(
        json.dumps(slim, sort_keys=True).encode()).hexdigest()


def isolation_report(parent_metas, manifest, eval_uids) -> dict:
    """Concrete UID-isolation assertions for the bank parents."""
    parent_uids = [m["clean_parent_uid"] for m in parent_metas]
    manifest_uids = {r["sample_uid"] for r in manifest["records"]}
    manifest_hashes = ({r["clean_hash"] for r in manifest["records"]}
                       | {r["corrupted_hash"] for r in manifest["records"]})
    parent_shas = [m["series_sha256"] for m in parent_metas]
    splits = defaultdict(set)
    for m in parent_metas:
        splits[m["split"]].add(m["clean_parent_uid"])
    split_pairs = {"train_val": splits["train"] & splits["val"],
                   "train_test": splits["train"] & splits["test"],
                   "val_test": splits["val"] & splits["test"]}
    rep = {
        "n_parents": len(parent_metas),
        "parent_uid_unique": len(set(parent_uids)) == len(parent_uids),
        "intersect_manifest_1599_uids":
            sorted(set(parent_uids) & manifest_uids),
        "intersect_eval_771_uids":
            sorted(set(parent_uids) & set(eval_uids)),
        "n_parent_series_hash_in_manifest":
            sum(1 for s in parent_shas if s in manifest_hashes),
        "split_disjoint_violations":
            {k: sorted(v) for k, v in split_pairs.items()},
    }
    rep["pass"] = bool(
        rep["parent_uid_unique"]
        and not rep["intersect_manifest_1599_uids"]
        and not rep["intersect_eval_771_uids"]
        and rep["n_parent_series_hash_in_manifest"] == 0
        and not any(rep["split_disjoint_violations"].values()))
    return rep


def carry_over_budget(v39: dict) -> dict:
    """Re-verify the frozen v3.9 budget numbers and carry them into v4.0.

    Raises AssertionError on any drift -- the budget is pre-registered, so a
    mismatch voids Phase 0 rather than being silently re-derived.
    """
    assert v39["baseline_arm"] == "D_fact_short_first"
    assert v39["new_beneficial_commits_needed_for_bcov"] == 15
    assert abs(v39["gain_deficit_sum"] - 5.6318868545896805) < 1e-9
    assert v39["max_new_harmful_commits_at_required_beneficial"] == -1
    assert v39["pme_headroom_edits"] == -1
    assert v39["baseline"]["prot_edit"] == 2
    assert v39["baseline"]["harmful"] == 15
    return {
        "phase": "v4.0 COUNTERACT-TS target budget (carried over from the "
                 "frozen v3.9 budget, docs/v4_0_counteract_preregistration.md "
                 "§2)",
        "carried_from": "results/v39_target_budget.json",
        "carried_from_sha256": _sha256(V39_BUDGET),
        "verified_v39_numbers": {
            "baseline_arm": v39["baseline_arm"],
            "baseline_improved": v39["baseline"]["improved"],
            "baseline_gain_sum": v39["baseline"]["gain_sum"],
            "baseline_committed": v39["baseline"]["committed"],
            "baseline_harmful": v39["baseline"]["harmful"],
            "baseline_prot_edit": v39["baseline"]["prot_edit"],
            "n_contaminated": v39["n_contaminated"],
            "n_frame": v39["n_frame"],
            "n_protected": v39["n_protected"],
        },
        "v40_targets": {
            "new_beneficial_and_safe_windows_min": 15,
            "gain_sum_increase_min": v39["gain_deficit_sum"],
            "net_protected_edits_removed_min": 1,
            "harmful_commits_must_decrease_below":
                v39["baseline"]["harmful"],
            "rationale": ("max_new_harmful_commits_at_required_beneficial = "
                          "-1 and pme_headroom_edits = -1: the CHR/pme "
                          "targets cannot be met by adding commits, so "
                          "COUNTERACT must also remove at least 1 protected "
                          "edit and reduce harmful commits relative to the "
                          "v3.9 D baseline"),
        },
        "targets_unchanged": v39["targets"],
    }


# -- Phase 0 stages -----------------------------------------------------------


def stage_integrity() -> int:
    t0 = time.time()
    checks = {}

    replay = json.load(V39_REPLAY.open(encoding="utf-8"))
    p0man = json.load(V39_P0_MANIFEST.open(encoding="utf-8"))
    freeze39 = json.load(V39_CAND_FREEZE.open(encoding="utf-8"))

    # 1. Every frozen input, hashed now, must equal the hash the v3.9 runs
    #    recorded when they consumed it.
    hash_checks = {}
    for name, got in replay["input_hashes"].items():
        path = ROOT / "results" / f"{name}.json"
        if not path.exists():
            path = ROOT / "results" / f"{name}.jsonl"
        now = _sha256(path)
        hash_checks[f"results/{path.name}"] = {
            "recorded_by_v39": got, "recomputed": now, "match": now == got}
    for rel, recorded in p0man["output_sha256"].items():
        now = _sha256(ROOT / rel)
        hash_checks[rel] = {"recorded_by_v39": recorded, "recomputed": now,
                            "match": now == recorded}
    cand_now = _sha256(V39_CANDIDATES)
    hash_checks["results/v39_longgap_candidates.jsonl"] = {
        "recorded_by_v39": freeze39["merged_sha256"], "recomputed": cand_now,
        "match": cand_now == freeze39["merged_sha256"]}
    for extra in (V39_PROBE, V39_ORACLE, V39_MODEL_MANIFEST, EXPLICIT_PROBE):
        hash_checks[f"results/{extra.name}"] = {
            "recorded_by_v39": None, "recomputed": _sha256(extra),
            "match": None}
    checks["input_hashes"] = hash_checks
    n_mismatch = sum(1 for c in hash_checks.values() if c["match"] is False)

    # 2. Frozen evaluation frame: 771 real windows; the 89 long-gap windows
    #    must be a subset.
    eval_uids = sorted({json.loads(l)["sample_uid"]
                        for l in ROWS_PATH.open(encoding="utf-8")
                        if not json.loads(l)["dataset"].startswith("ood:")})
    cand = [json.loads(l) for l in V39_CANDIDATES.open(encoding="utf-8")]
    longgap_uids = sorted({r["sample_uid"] for r in cand})
    checks["eval_frame"] = {
        "n_eval_uids": len(eval_uids),
        "n_longgap_uids": len(longgap_uids),
        "longgap_subset_of_eval": set(longgap_uids) <= set(eval_uids),
        "n_longgap_candidate_records": len(cand),
    }

    # 3. Corpus manifest: 1599 unique windows.
    manifest = json.load(MANIFEST_PATH.open(encoding="utf-8"))
    m_uids = [r["sample_uid"] for r in manifest["records"]]
    checks["corpus_manifest"] = {
        "n_records": len(m_uids), "uids_unique": len(set(m_uids)) == 1599,
    }

    # 4. Incumbent spot-check against the frozen v3.3 rerun.
    frozen_arm = json.load(FROZEN_V33.open(
        encoding="utf-8"))["arms"]["PICS_joint_relabel"]
    expected = {"beneficial_coverage": 0.2727, "conditional_harm_rate": 0.2053,
                "protected_mis_edit_rate": 0.0091,
                "mean_repair_gain_contaminated": 0.0919, "damage": 0.0402}
    checks["incumbent_spotcheck"] = {
        k: {"expected_4dp": v, "frozen": float(frozen_arm[k]),
            "match_4dp": abs(float(frozen_arm[k]) - v) < 5e-5}
        for k, v in expected.items()}

    # 5. UID-isolation plan (concrete assertions are emitted by the parents
    #    stage into v40_bank_isolation.json).
    checks["uid_isolation_plan"] = {
        "bank_uid_namespaces": ["v40parent:", "v40ep-"],
        "namespace_collision_possible": False,
        "content_isolation": ("parent series sha256 must not occur among the "
                              "1599 manifest clean/corrupted hashes; parent "
                              "first-16-value md5 must not collide with any "
                              "rebuilt corpus window (position-collision "
                              "guard)"),
        "concrete_assertion_file": OUT_ISOLATION.name,
        "concrete_assertion_status": ("present" if OUT_ISOLATION.exists()
                                      else "pending parents stage"),
        "clean_parent_uid_partition": ("parent_split(): sha256(parent_uid) "
                                       "first byte <204 train, <230 val, "
                                       "else test; a parent uid maps to "
                                       "exactly one split by construction"),
        "lodo_rule": ("the 6 development sources stay LODO-isolated: in a "
                      "leave-one-source-out fold, bank windows derived from "
                      "the held-out source never enter training; the 2 new "
                      "public sources are training-only"),
        "longgap_89_rule": ("the 89 frozen long-gap windows are evaluation "
                            "only: no training, no threshold selection"),
    }

    all_pass = bool(
        n_mismatch == 0
        and len(eval_uids) == 771
        and checks["eval_frame"]["longgap_subset_of_eval"]
        and len(longgap_uids) == 89
        and len(m_uids) == 1599 and checks["corpus_manifest"]["uids_unique"]
        and all(c["match_4dp"]
                for c in checks["incumbent_spotcheck"].values()))
    out = {
        "phase": "v4.0 Phase 0 integrity (docs/v4_0_counteract_preregistration"
                 ".md §2)",
        "checks": checks,
        "n_hash_mismatch": n_mismatch,
        "all_pass": all_pass,
        "runtime_sec": time.time() - t0,
    }
    with OUT_INTEGRITY.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)
    print(f"[integrity] all_pass={all_pass} hash_mismatch={n_mismatch} "
          f"-> {OUT_INTEGRITY.name}", flush=True)
    print("___V40_INTEGRITY_DONE___", flush=True)
    return 0 if all_pass else 1


def stage_budget() -> int:
    v39 = json.load(V39_BUDGET.open(encoding="utf-8"))
    budget = carry_over_budget(v39)
    with OUT_BUDGET.open("w", encoding="utf-8") as f:
        json.dump(budget, f, indent=1, ensure_ascii=False)
    print(f"[budget] carried: +{budget['v40_targets']['new_beneficial_and_safe_windows_min']} B&S, "
          f"+{budget['v40_targets']['gain_sum_increase_min']:.3f} gain, "
          f"-1 protected edit, harmful < "
          f"{budget['v40_targets']['harmful_commits_must_decrease_below']} "
          f"-> {OUT_BUDGET.name}", flush=True)
    print("___V40_BUDGET_DONE___", flush=True)
    return 0


def stage_manifest() -> int:
    registry = (json.load(OUT_REGISTRY.open(encoding="utf-8"))
                if OUT_REGISTRY.exists() else None)
    sources = []
    for s in DEV_SOURCES:
        sources.append({"source": s, "role": "development (LODO-isolated)",
                        "provenance": "frozen corpus pipeline "
                                      "(experiments/datasets.py)"})
    for s in PUBLIC_SOURCES:
        entry = {"source": s, "role": "training-only public source"}
        if registry and s in registry.get("sources", {}):
            entry.update(registry["sources"][s])
            entry["obtained"] = True
        else:
            entry["obtained"] = False
            entry["fallback"] = ("not fetched; pilot runs on the 6 "
                                 "development sources with UID-isolated "
                                 "resampling")
        sources.append(entry)
    manifest = {
        "phase": "v4.0 counterfactual action bank design manifest "
                 "(frozen before generation; "
                 "docs/v4_0_counteract_preregistration.md §2-§3)",
        "frozen_at_epoch": time.time(),
        "bank_seed": BANK_SEED,
        "window_len": WINDOW_LEN,
        "corruption": {
            "mechanisms": list(MECHANISMS),
            "severities": list(SEVERITIES),
            "severity_ranges": SEVERITY_RANGES,
            "mixed_share": N_MIXED / N_TOTAL,
            "mixed_components": ("2 distinct mechanisms per mixed episode, "
                                 "severities drawn per component, masks "
                                 "unioned; components fixed in the plan"),
            "clean_control_share": N_CLEAN / N_TOTAL,
            "missing_block_extension": ("block lengths cover 5%-50% of the "
                                        "512-window; the frozen evaluation "
                                        "injector writes 25-63/512 "
                                        "(~5%-12%). The extension is an "
                                        "intentional training-distribution "
                                        "widening, pre-registered here; the "
                                        "evaluation corpus is untouched"),
        },
        "actions": {
            "set": list(ACTIONS),
            "family": ACTION_FAMILY,
            "label_family": LABEL_FAMILY,
            "fact_short": {"max_gap": FACT_SHORT_MAX_GAP,
                           "definition": "raw-NaN runs 1-3, two finite "
                                         "anchors, linear interpolation, "
                                         "observed support unchanged"},
            "tsicl_long": {"min_run": TSICL_MIN_RUN,
                           "checkpoint": str(TSICL_CKPT.relative_to(ROOT)),
                           "checkpoint_sha256": TSICL_CKPT_SHA256,
                           "point_estimator": "median",
                           "contract": "only raw-NaN positions written; "
                                       "observed-support drift exactly 0"},
            "impute_params": IMPUTE_PARAMS,
            "semantic_gating": "candidates are generated only when the "
                               "action is semantically applicable; every "
                               "applicable action is executed per episode",
        },
        "episode_counts": {"n_per_mechanism_severity_cell": N_PER_CELL,
                           "n_mixed": N_MIXED, "n_clean_control": N_CLEAN,
                           "n_total": N_TOTAL,
                           "max_episodes_per_parent": MAX_EPISODES_PER_PARENT,
                           "n_parents_planned": math.ceil(
                               N_TOTAL / MAX_EPISODES_PER_PARENT)},
        "sources": sources,
        "isolation": {
            "eval_frame_excluded": "771 frozen real evaluation windows",
            "corpus_excluded": "1599 manifest windows (content hash + "
                               "first-16-value position guard)",
            "split": "hash split by clean_parent_uid, 80/10/10; a parent "
                     "never crosses train/val/test",
            "assertion_file": OUT_ISOLATION.name,
        },
        "red_line": {
            "freeze_before_labels": ("candidates are written and digested "
                                     "(v40_bank_freeze.json) before "
                                     "compute_action_labels is called"),
            "label_path": ("experiments/v33_labels.py::compute_action_labels "
                           "over metrics_common.canonical_nmse -- the frozen "
                           "v3.3 action-semantic path; no new NMSE"),
            "evaluation_namespace": sorted(EVAL_NAMESPACE),
            "forbidden_model_inputs": ("true_kind/clean/source_id/sample_uid "
                                       "never enter model-input fields; "
                                       "source is a Group-DRO label only"),
        },
        "code_hashes": {
            "experiments/v40_counterfactual_bank.py": _sha256(
                Path(__file__).resolve()),
            "experiments/v33_labels.py": _sha256(
                ROOT / "experiments" / "v33_labels.py"),
            "experiments/metrics_common.py": _sha256(
                ROOT / "experiments" / "metrics_common.py"),
            "experiments/corpus.py": _sha256(ROOT / "experiments" / "corpus.py"),
            "src/introact_ts/actions.py": _sha256(
                ROOT / "src" / "introact_ts" / "actions.py"),
        },
    }
    with OUT_BANK_MANIFEST.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False, default=str)
    print(f"[manifest] -> {OUT_BANK_MANIFEST.name}", flush=True)
    print("___V40_MANIFEST_DONE___", flush=True)
    return 0


def stage_fetch_data() -> int:
    """Fetch the two public training sources, time-boxed; register or fall
    back honestly (§3: give up if the network cannot deliver quickly)."""
    import signal
    import socket
    import urllib.request

    class _FetchTimeout(Exception):
        pass

    def _alarm(_signum, _frame):
        raise _FetchTimeout("hard 35s alarm (DNS/connect stall, not caught "
                            "by socket.setdefaulttimeout)")

    #: urlretrieve takes no timeout kwarg, and a stalled DNS lookup to an
    #: unreachable mirror does not respect socket.setdefaulttimeout either
    #: -- observed hanging past FETCH_TIME_BUDGET_SEC on this node. A hard
    #: SIGALRM around each attempt is what actually bounds it.
    socket.setdefaulttimeout(30)
    signal.signal(signal.SIGALRM, _alarm)
    t0 = time.time()
    revision = None
    try:
        with urllib.request.urlopen(GITHUB_API_COMMIT, timeout=20) as r:
            revision = json.load(r)["sha"]
    except Exception as exc:
        print(f"[fetch-data] commit lookup failed: {exc}", flush=True)
    registry = {"phase": "v4.0 public training-source registry",
                "fetched_at_epoch": t0, "mirror_revision": revision,
                "time_budget_sec": FETCH_TIME_BUDGET_SEC, "sources": {}}
    ok = 0
    for name, info in PUBLIC_DOWNLOADS.items():
        dest = ROOT / "data" / PUBLIC_FILES[name]
        entry = dict(info)
        entry["file"] = f"data/{PUBLIC_FILES[name]}"
        try:
            remaining = FETCH_TIME_BUDGET_SEC - (time.time() - t0)
            if remaining <= 30:
                raise TimeoutError("fetch time budget exhausted")
            print(f"[fetch-data] {name} <- {info['url']}", flush=True)
            signal.alarm(35)
            try:
                urllib.request.urlretrieve(info["url"], str(dest))
            finally:
                signal.alarm(0)
            entry["sha256"] = _sha256(dest)
            entry["bytes"] = dest.stat().st_size
            ok += 1
            print(f"[fetch-data] {name}: {entry['bytes']} bytes, "
                  f"sha256={entry['sha256'][:16]}...", flush=True)
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            if dest.exists():
                dest.unlink()
            print(f"[fetch-data] {name} FAILED: {entry['error']}", flush=True)
        registry["sources"][name] = entry
    registry["n_obtained"] = ok
    registry["fallback"] = (ok < len(PUBLIC_DOWNLOADS))
    if registry["fallback"]:
        registry["fallback_note"] = (
            "pilot proceeds on the 6 development sources with UID-isolated "
            "resampling, as pre-registered")
    with OUT_REGISTRY.open("w", encoding="utf-8") as f:
        json.dump(registry, f, indent=1, ensure_ascii=False)
    print(f"[fetch-data] obtained {ok}/{len(PUBLIC_DOWNLOADS)} in "
          f"{time.time() - t0:.0f}s -> {OUT_REGISTRY.name}", flush=True)
    print("___V40_FETCH_DATA_DONE___", flush=True)
    return 0


# -- Phase 1 stages -----------------------------------------------------------


def _load_registry_sources():
    """Sources actually available for parents (registered public files only)."""
    out = list(DEV_SOURCES)
    if OUT_REGISTRY.exists():
        reg = json.load(OUT_REGISTRY.open(encoding="utf-8"))
        for s in PUBLIC_SOURCES:
            e = reg.get("sources", {}).get(s, {})
            if e.get("sha256") and (ROOT / e["file"]).exists():
                if _sha256(ROOT / e["file"]) == e["sha256"]:
                    out.append(s)
    return out


def _sample_public(name, n, seed):
    """Defect-free 512-windows from one registered public matrix source."""
    import gzip
    path = ROOT / "data" / PUBLIC_FILES[name]
    with gzip.open(path, "rt") as fh:
        mat = np.loadtxt(fh, delimiter=",")
    rng = np.random.RandomState(seed)
    out, attempts = [], 0
    order = rng.permutation(mat.shape[1])
    while len(out) < n and attempts < n * 200:
        attempts += 1
        ci = int(order[len(out) % len(order)])
        col = mat[:, ci]
        if len(col) <= WINDOW_LEN:
            continue
        start = int(rng.randint(0, len(col) - WINDOW_LEN))
        seg = col[start:start + WINDOW_LEN].astype(np.float64)
        if not np.isfinite(seg).all():
            continue
        spread = float(np.std(seg))
        if spread < 0.05 * max(float(np.std(col)), 1e-9) or spread < 1e-8:
            continue
        out.append({"series": seg.copy(), "dataset": name,
                    "channel": str(ci),
                    "freq": "H" if "electricity" in name else "5T",
                    "start": start})
    if len(out) < n:
        raise RuntimeError(f"only {len(out)}/{n} usable windows from {name}")
    return out


def stage_parents() -> int:
    t0 = time.time()
    from datasets import sample_ett_windows, sample_time_windows, INDUSTRIAL
    sources = _load_registry_sources()
    n_parents = math.ceil(N_TOTAL / MAX_EPISODES_PER_PARENT)
    quota = math.ceil(n_parents / len(sources))
    print(f"[parents] {n_parents} parents over {len(sources)} sources "
          f"(quota {quota})", flush=True)

    # Content-isolation ban set: the rebuilt frozen corpus.
    recs, _ = rebuild_corpus()
    manifest = json.load(MANIFEST_PATH.open(encoding="utf-8"))
    gate = verify_against_manifest(recs, manifest)
    if not gate["pass"]:
        raise SystemExit(f"[FATAL] corpus manifest gate: {gate}")
    banned = set()
    for r in recs:
        banned.add(_first16_md5(r["series"]))
        w = r["window"]
        if w.clean_series is not None:
            banned.add(_first16_md5(w.clean_series))
    manifest_hashes = ({r["clean_hash"] for r in manifest["records"]}
                       | {r["corrupted_hash"] for r in manifest["records"]})
    eval_uids = sorted({json.loads(l)["sample_uid"]
                        for l in ROWS_PATH.open(encoding="utf-8")
                        if not json.loads(l)["dataset"].startswith("ood:")})
    print(f"[parents] ban set {len(banned)} keys, {len(eval_uids)} eval uids "
          f"({time.time() - t0:.0f}s)", flush=True)

    metas, arrays = [], []
    for si, src in enumerate(sources):
        got, seed_off = [], 0
        #: (channel, start) pairs already accepted for this source. The
        #: samplers draw `start` uniformly over the column and re-draw with a
        #: fresh seed each while-loop iteration, so on short columns (the
        #: financial sources) the same (channel, start) -- and hence the same
        #: clean_parent_uid -- can recur across iterations; without this the
        #: isolation report's parent_uid_unique check fails downstream.
        seen_keys = set()
        while len(got) < quota:
            n_draw = quota - len(got) + quota // 4 + 8
            seed = BANK_SEED + 101 * si + 7919 * seed_off
            seed_off += 1
            if src in INDUSTRIAL:
                draw = sample_ett_windows(n_draw, window_len=WINDOW_LEN,
                                          datasets=(src,), seed=seed)
            elif src in PUBLIC_SOURCES:
                draw = _sample_public(src, n_draw, seed)
            else:
                draw = sample_time_windows(n_draw, window_len=WINDOW_LEN,
                                           sources=(src,), seed=seed)
            for w in draw:
                if len(got) >= quota:
                    break
                key = (w["channel"], int(w["start"]))
                if key in seen_keys:
                    continue
                s = np.asarray(w["series"], dtype=np.float64)
                if _first16_md5(s) in banned:
                    continue
                if hash_array(s) in manifest_hashes:
                    continue
                seen_keys.add(key)
                got.append(w)
            if seed_off > 25:
                raise RuntimeError(f"cannot fill quota for {src}")
        for w in got[:quota]:
            s = np.asarray(w["series"], dtype=np.float64)
            uid = parent_uid(src, w["channel"], w["start"], s)
            metas.append({"clean_parent_uid": uid, "source": src,
                          "channel": str(w["channel"]), "start": int(w["start"]),
                          "freq": w["freq"], "split": parent_split(uid),
                          "series_sha256": hash_array(s),
                          "array_index": len(arrays)})
            arrays.append(s)
        print(f"[parents] {src}: {quota} ({time.time() - t0:.0f}s)",
              flush=True)

    metas = metas[:n_parents]
    arrays = arrays[:n_parents]
    iso = isolation_report(metas, manifest, eval_uids)
    iso["per_source"] = dict(Counter(m["source"] for m in metas))
    iso["per_split"] = dict(Counter(m["split"] for m in metas))
    iso["banned_keys"] = len(banned)
    if not iso["pass"]:
        with OUT_ISOLATION.open("w", encoding="utf-8") as f:
            json.dump(iso, f, indent=1)
        raise SystemExit(f"[FATAL] isolation assertions failed: {iso}")
    np.savez(OUT_PARENTS_NPZ, **{f"p{m['array_index']}": a
                                 for m, a in zip(metas, arrays)})
    with OUT_PARENTS_META.open("w", encoding="utf-8") as f:
        for m in metas:
            f.write(json.dumps(m, sort_keys=True) + "\n")
    iso["output_sha256"] = {"v40_bank_parents.npz": _sha256(OUT_PARENTS_NPZ),
                            "v40_bank_parents.jsonl": _sha256(OUT_PARENTS_META)}
    iso["runtime_sec"] = time.time() - t0
    with OUT_ISOLATION.open("w", encoding="utf-8") as f:
        json.dump(iso, f, indent=1)
    print(f"[parents] {len(metas)} parents, isolation pass=True "
          f"({time.time() - t0:.0f}s)", flush=True)
    print("___V40_PARENTS_DONE___", flush=True)
    return 0


def _load_parents():
    metas = [json.loads(l) for l in OUT_PARENTS_META.open(encoding="utf-8")]
    z = np.load(OUT_PARENTS_NPZ)
    arrays = [np.asarray(z[f"p{m['array_index']}"], dtype=np.float64)
              for m in metas]
    return metas, arrays


def _candidate_record(entry, meta, action):
    return {
        "episode_uid": episode_uid(entry["idx"], entry["corruption"],
                                   entry["severity"]),
        "clean_parent_uid": meta["clean_parent_uid"],
        "source": meta["source"], "channel": meta["channel"],
        "start": meta["start"], "split": meta["split"],
        "corruption": entry["corruption"], "severity": entry["severity"],
        "components": entry["components"],
        "protected": bool(entry["corruption"] == "none"),
        "family": ACTION_FAMILY[action], "action": action,
        "supported": True, "unsupported_reason": None,
        "applicable": False, "n_filled": 0,
        "candidate_hash": None, "input_hash": None, "mask_hash": None,
        "touched_mask_hash": None,
        "episode_seed": int(entry["seed"]),
        "fill_values": None, "model": None,
        "provenance": {"stage": "candidates", "bank_seed": BANK_SEED,
                       "code_sha256": _sha256(Path(__file__).resolve()),
                       "python": sys.version.split()[0]},
    }


def stage_candidates() -> int:
    t0 = time.time()
    metas, arrays = _load_parents()
    plan = episode_plan()
    with OUT_PLAN.open("w", encoding="utf-8") as f:
        json.dump({"bank_seed": BANK_SEED, "n_episodes": len(plan),
                   "plan": plan}, f)
    #: tsicl_long's file is opened here too (gate-out records land in it
    #: immediately below); stage_tsicl reopens it in append mode afterwards
    #: to add the GPU-computed gated-in records without truncating these.
    out_files = {a: (ROOT / "results" / f"{_STEM}bank_cand_{a}.jsonl").open(
        "w", encoding="utf-8") for a in ACTIONS}
    tsicl_worklist = []
    n_gate_out = Counter()
    for i, entry in enumerate(plan):
        meta = metas[entry["parent_idx"]]
        clean = arrays[entry["parent_idx"]]
        dirty, mask = apply_episode_corruption(clean, entry)
        ihash, mhash = hash_array(dirty), mask_hash(mask)
        for action in ACTIONS:
            rec = _candidate_record(entry, meta, action)
            rec["input_hash"], rec["mask_hash"] = ihash, mhash
            gated, reason = action_gate(dirty, action)
            if not gated:
                rec["supported"] = False
                rec["unsupported_reason"] = f"semantic_gate: {reason}"
                n_gate_out[action] += 1
            elif action == "tsicl_long":
                tsicl_worklist.append({
                    "episode_uid": rec["episode_uid"],
                    "parent_idx": int(entry["parent_idx"]),
                    "plan_entry": {k: entry[k] for k in
                                   ("idx", "corruption", "severity",
                                    "components", "seed")}})
                continue  # gated-in tsicl_long: GPU stage appends its record
            else:
                y, touched, applicable, params = run_cpu_action(dirty, action)
                rec["applicable"] = bool(applicable)
                rec["params"] = params
                rec["n_filled"] = int(touched.sum()) if applicable else 0
                rec["candidate_hash"] = (hash_array(y) if applicable else None)
                rec["touched_mask_hash"] = mask_hash(touched)
            # Reached for every action except the gated-in tsicl_long case
            # above (which `continue`s past this write on purpose).
            out_files[action].write(json.dumps(rec, sort_keys=True) + "\n")
        if (i + 1) % 500 == 0:
            print(f"[candidates] {i + 1}/{len(plan)} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    for f in out_files.values():
        f.close()
    with OUT_TSICL_WORKLIST.open("w", encoding="utf-8") as f:
        json.dump({"n": len(tsicl_worklist), "worklist": tsicl_worklist}, f)
    print(f"[candidates] {len(plan)} episodes, tsicl worklist "
          f"{len(tsicl_worklist)}, gated-out {dict(n_gate_out)} "
          f"({time.time() - t0:.0f}s)", flush=True)
    print("___V40_CANDIDATES_DONE___", flush=True)
    return 0


def stage_tsicl() -> int:
    t0 = time.time()
    import torch
    torch.cuda.set_per_process_memory_fraction(0.55)
    assert _sha256(TSICL_CKPT) == TSICL_CKPT_SHA256, \
        "TS-ICL checkpoint sha256 mismatch"
    from tsicl import TSICL
    model = TSICL(model_path=str(TSICL_CKPT))
    metas, arrays = _load_parents()
    wl = json.load(OUT_TSICL_WORKLIST.open(encoding="utf-8"))["worklist"]
    out_path = ROOT / "results" / f"{_STEM}bank_cand_tsicl_long.jsonl"
    #: The candidates stage pre-populates this file with the gated-out
    #: (unsupported) tsicl_long records; this stage appends the GPU-computed
    #: gated-in ones rather than truncating, so freeze sees the full action
    #: set per episode. n_gate_out below re-derives the expected pre-existing
    #: line count to guard against appending onto a stale or re-run file.
    n_gate_out_expected = N_TOTAL - len(wl)
    n_existing = sum(1 for _ in out_path.open(encoding="utf-8"))
    assert n_existing == n_gate_out_expected, (
        f"[FATAL] {out_path.name} has {n_existing} lines, expected "
        f"{n_gate_out_expected} gated-out records from the candidates "
        f"stage -- re-run candidates before tsicl")
    n_unsupported = 0
    with out_path.open("a", encoding="utf-8") as f:
        for i, item in enumerate(wl):
            entry = item["plan_entry"]
            meta = metas[item["parent_idx"]]
            clean = arrays[item["parent_idx"]]
            dirty, mask = apply_episode_corruption(clean, entry)
            rec = _candidate_record(entry, meta, "tsicl_long")
            rec["input_hash"], rec["mask_hash"] = (hash_array(dirty),
                                                   mask_hash(mask))
            rec["provenance"]["stage"] = "tsicl"
            rec["provenance"]["device"] = (
                "cuda" if torch.cuda.is_available() else "cpu")
            try:
                nm = raw_nan_mask(dirty)
                pos = np.flatnonzero(nm)
                point, _quants = model.impute(
                    inputs=dirty, quantile_levels=[0.1, 0.5, 0.9],
                    denormalize=True, point_estimator="median",
                    replace_by_gt=True, squeeze_output=True)
                point = np.asarray(point.detach().cpu().numpy(),
                                   dtype=np.float64).reshape(-1)[:len(dirty)]
                fill = point[pos]
                if not np.isfinite(fill).all():
                    raise ValueError("TS-ICL produced non-finite values")
                y, touched = rebuild_tsicl_output(dirty, fill)
                rec["applicable"] = True
                rec["params"] = {"quantile_levels": [0.1, 0.5, 0.9],
                                 "point_estimator": "median",
                                 "replace_by_gt": True}
                rec["n_filled"] = int(nm.sum())
                rec["candidate_hash"] = hash_array(y)
                rec["touched_mask_hash"] = mask_hash(touched)
                rec["fill_values"] = [float(v) for v in fill]
                rec["model"] = {"huggingface_id": "taharnbl/TS-ICL",
                                "checkpoint_sha256": TSICL_CKPT_SHA256}
            except Exception as exc:  # unsupported, never a silent fallback
                rec["supported"] = False
                rec["unsupported_reason"] = f"{type(exc).__name__}: {exc}"
                n_unsupported += 1
            f.write(json.dumps(rec, sort_keys=True) + "\n")
            if (i + 1) % 100 == 0:
                print(f"[tsicl] {i + 1}/{len(wl)} "
                      f"({time.time() - t0:.0f}s)", flush=True)
    gpu_peak = (float(torch.cuda.max_memory_allocated() / 2**20)
                if torch.cuda.is_available() else None)
    print(f"[tsicl] {len(wl)} candidates ({n_unsupported} unsupported), "
          f"gpu_peak={gpu_peak} MB ({time.time() - t0:.0f}s)", flush=True)
    print("___V40_TSICL_DONE___", flush=True)
    return 0


def stage_freeze() -> int:
    t0 = time.time()
    files = {a: ROOT / "results" / f"{_STEM}bank_cand_{a}.jsonl"
             for a in ACTIONS}
    missing = [a for a, p in files.items() if not p.exists()]
    if missing:
        raise SystemExit(f"[FATAL] candidate stages missing: {missing}")
    recs = []
    per_file = {}
    for a in ACTIONS:
        rs = [json.loads(l) for l in files[a].open(encoding="utf-8")]
        per_file[files[a].name] = {"sha256": _sha256(files[a]),
                                   "n_records": len(rs)}
        recs.extend(rs)
    by_ep = defaultdict(list)
    for r in recs:
        by_ep[r["episode_uid"]].append(r["action"])
    bad = {e: a for e, a in by_ep.items() if sorted(a) != sorted(ACTIONS)}
    if bad:
        raise SystemExit(f"[FATAL] {len(bad)} episodes lack the full action "
                         f"set, e.g. {list(bad.items())[:3]}")
    recs.sort(key=lambda r: (r["episode_uid"], r["action"]))
    with OUT_CANDIDATES.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    digest = digest_records(recs)
    dist = {
        "n_episodes": len(by_ep),
        "n_records": len(recs),
        "per_corruption": dict(Counter(r["corruption"] for r in recs
                                       if r["action"] == "keep")),
        "per_severity": dict(Counter(
            r["severity"] for r in recs if r["action"] == "keep")),
        "per_split": dict(Counter(r["split"] for r in recs
                                  if r["action"] == "keep")),
        "per_source": dict(Counter(r["source"] for r in recs
                                   if r["action"] == "keep")),
        "n_supported_per_action": dict(Counter(
            r["action"] for r in recs if r["supported"])),
        "n_applicable_per_action": dict(Counter(
            r["action"] for r in recs if r["applicable"])),
    }
    freeze = {
        "phase": "v4.0 Phase 1 candidate freeze (labels not yet joined)",
        "frozen_at_epoch": time.time(),
        "per_file": per_file,
        "merged_file": OUT_CANDIDATES.name,
        "merged_sha256": _sha256(OUT_CANDIDATES),
        "record_digest_sha256": digest,
        "distribution": dist,
        "label_freeze_discipline": ("all candidate outputs and hashes are "
                                    "frozen here; evaluate refuses to run "
                                    "without this file and re-verifies every "
                                    "candidate hash by deterministic "
                                    "recomputation before any label is "
                                    "joined"),
        "runtime_sec": time.time() - t0,
    }
    with OUT_FREEZE.open("w", encoding="utf-8") as f:
        json.dump(freeze, f, indent=1)
    print(f"[freeze] {dist['n_episodes']} episodes, {dist['n_records']} "
          f"records, digest={digest[:16]}... -> {OUT_FREEZE.name}", flush=True)
    print("___V40_FREEZE_DONE___", flush=True)
    return 0


def stage_evaluate() -> int:
    t0 = time.time()
    if not OUT_FREEZE.exists():
        raise SystemExit("[FATAL] candidates not frozen; run candidate "
                         "stages then freeze before evaluate")
    freeze = json.load(OUT_FREEZE.open(encoding="utf-8"))
    if _sha256(OUT_CANDIDATES) != freeze["merged_sha256"]:
        raise SystemExit("[FATAL] merged candidates file changed after freeze")
    print(f"[freeze verified] digest={freeze['record_digest_sha256'][:16]}...",
          flush=True)

    metas, arrays = _load_parents()
    plan = {e["idx"]: e for e in episode_plan()}
    cand = [json.loads(l) for l in OUT_CANDIDATES.open(encoding="utf-8")]
    assert len(cand) == freeze["distribution"]["n_records"]

    # -- re-derive every dirty window and re-verify every candidate hash ------
    n_hash_fail, max_drift = 0, 0.0
    dirty_cache = {}
    for r in cand:
        idx = int(r["episode_uid"].split(":")[0].split("-")[1])
        if idx not in dirty_cache:
            entry = plan[idx]
            p = r["clean_parent_uid"]
            pi = next(i for i, m in enumerate(metas)
                      if m["clean_parent_uid"] == p)
            dirty, _mask = apply_episode_corruption(arrays[pi], entry)
            assert hash_array(dirty) == r["input_hash"], \
                f"dirty reproduction failed on {r['episode_uid']}"
            dirty_cache[idx] = dirty
        x = dirty_cache[idx]
        if not r["supported"] or not r["applicable"]:
            continue
        if r["action"] == "tsicl_long":
            y, _t = rebuild_tsicl_output(x, r["fill_values"])
        else:
            y, _t, app, _p = run_cpu_action(x, r["action"])
            assert app, f"{r['episode_uid']}:{r['action']} no longer applies"
        if hash_array(y) != r["candidate_hash"]:
            n_hash_fail += 1
        obs = np.isfinite(x)
        drift = float(np.max(np.abs(y[obs] - x[obs]))) if obs.any() else 0.0
        if r["family"] in ("FACT_SHORT", "TSICL_LONG"):
            max_drift = max(max_drift, drift)
    if n_hash_fail:
        raise SystemExit(f"[FATAL] {n_hash_fail} frozen candidate hashes do "
                         f"not reproduce")
    print(f"[candidates re-verified] max fill drift={max_drift} "
          f"({time.time() - t0:.0f}s)", flush=True)

    # -- join labels (evaluation namespace from here on) ----------------------
    clean_of = {m["clean_parent_uid"]: a for m, a in zip(metas, arrays)}
    records = []
    for r in cand:
        idx = int(r["episode_uid"].split(":")[0].split("-")[1])
        x = dirty_cache[idx]
        clean = clean_of[r["clean_parent_uid"]]
        labels = None
        if r["supported"] and r["applicable"]:
            if r["action"] == "tsicl_long":
                y, touched = rebuild_tsicl_output(x, r["fill_values"])
            else:
                y, touched, _app, _p = run_cpu_action(x, r["action"])
            labels = compute_action_labels(
                LABEL_FAMILY[r["action"]], x, y, clean,
                touched=touched, params=r.get("params") or {})
            labels = {k: (float(v) if isinstance(
                v, (int, float, np.floating)) and v is not None else v)
                for k, v in labels.items()}
            if r["action"] == "keep":
                assert abs(labels["true_repair_gain"]) <= 1e-12
        rec = dict(r)
        rec.pop("fill_values", None)
        rec["labels"] = labels
        rec["before_nmse"] = labels["before_nmse"] if labels else None
        rec["after_nmse"] = labels["after_nmse"] if labels else None
        rec["gain"] = labels["true_repair_gain"] if labels else 0.0
        rec["true_loss"] = labels["true_loss"] if labels else 0.0
        rec["harmful"] = bool(labels and labels["true_loss"] > HARM_LOSS)
        rec["beneficial_and_safe"] = bool(
            labels and labels["beneficial_and_safe"])
        rec["provenance"] = {**r["provenance"], "stage": "evaluate",
                             "label_path": "v33_labels.compute_action_labels"}
        problems = validate_record(rec, labeled=True)
        assert not problems, f"{r['episode_uid']}:{r['action']}: {problems}"
        records.append(rec)
    with OUT_BANK_RECORDS.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
    print(f"[labels joined] {len(records)} records -> "
          f"{OUT_BANK_RECORDS.name} ({time.time() - t0:.0f}s)", flush=True)

    # -- report ------------------------------------------------------------------
    def cell_stats(rs):
        app = [r for r in rs if r["applicable"]]
        gains = [r["gain"] for r in app]
        n_app = len(app)
        return {
            "n_records": len(rs), "n_applicable": n_app,
            "n_bs": sum(1 for r in app if r["beneficial_and_safe"]),
            "bs_rate": (sum(1 for r in app if r["beneficial_and_safe"])
                        / n_app if n_app else None),
            "n_harmful": sum(1 for r in app if r["harmful"]),
            "harmful_rate": (sum(1 for r in app if r["harmful"]) / n_app
                             if n_app else None),
            "gain_mean": float(np.mean(gains)) if gains else None,
            "gain_median": float(np.median(gains)) if gains else None,
            "gain_p10": float(np.percentile(gains, 10)) if gains else None,
            "gain_p90": float(np.percentile(gains, 90)) if gains else None,
        }

    by_msa = defaultdict(list)
    for r in records:
        by_msa[(r["corruption"], r["severity"], r["action"])].append(r)
    cells = {f"{c}|{s}|{a}": cell_stats(rs)
             for (c, s, a), rs in sorted(by_msa.items())}

    plan_idx = {e["idx"]: e for e in episode_plan()}
    longgap_ep = {episode_uid(e["idx"], e["corruption"], e["severity"])
                  for e in plan_idx.values()
                  if e["corruption"] == "missing_block"
                  or (e["corruption"] == "mixed" and any(
                      c[0] == "missing_block" for c in e["components"]))}
    tsicl_longgap = [r for r in records
                     if r["action"] == "tsicl_long"
                     and r["episode_uid"] in longgap_ep]
    split_detail = {}
    for split in ("train", "val", "test"):
        rs = [r for r in records if r["split"] == split
              and r["action"] == "keep"]
        split_detail[split] = {
            "n_episodes": len(rs),
            "n_parents": len({r["clean_parent_uid"] for r in rs}),
            "per_source": dict(Counter(r["source"] for r in rs)),
        }
    report = {
        "phase": "v4.0 Phase 1 counterfactual action bank pilot report",
        "freeze_digest": freeze["record_digest_sha256"],
        "n_episodes": freeze["distribution"]["n_episodes"],
        "n_records": len(records),
        "per_action_overall": {a: cell_stats(
            [r for r in records if r["action"] == a]) for a in ACTIONS},
        "per_corruption_severity_action": cells,
        "tsicl_long_on_longgap_episodes": {
            "definition": ("episodes whose corruption is missing_block or a "
                           "mixed containing missing_block"),
            "n_longgap_episodes": len(longgap_ep),
            **cell_stats(tsicl_longgap)},
        "split_detail": split_detail,
        "harmful_examples_cap": 0,
        "runtime_sec": time.time() - t0,
    }
    with OUT_REPORT.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, ensure_ascii=False, default=str)
    print(f"[report] -> {OUT_REPORT.name}", flush=True)
    print("___V40_EVALUATE_DONE___", flush=True)
    return 0


STAGES = {"integrity": stage_integrity, "budget": stage_budget,
          "manifest": stage_manifest, "fetch-data": stage_fetch_data,
          "parents": stage_parents, "candidates": stage_candidates,
          "tsicl": stage_tsicl, "freeze": stage_freeze,
          "evaluate": stage_evaluate}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=sorted(STAGES))
    args = ap.parse_args()
    return STAGES[args.stage]()


if __name__ == "__main__":
    sys.exit(main())
