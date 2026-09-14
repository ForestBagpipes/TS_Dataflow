"""v3.5 ACV shared core: changed-support extraction and post-action anchors.

Pre-registered in ``docs/v3_5_acv_preregistration.md`` §2 (frozen data flow).
This module is the single source of truth for Phase 0 (structural support
audit), Phase 1 (ACV probe) and Phase 2 (TSFM_RECONSTRUCT operator probe):
given a candidate's window (the corrupted series exactly as the frozen
seed-101 corpus holds it), its family and its params, it re-runs the
production operator, derives the *changed support* (the points the action
actually rewrote), decomposes that support into contiguous runs, and selects
up to ``MAX_ANCHORS`` post-action anchor target blocks of real, finite,
action-untouched observations.

Ground-truth discipline: everything here is a pure function of the corrupted
series, the sample_uid and the candidate params. No clean series, no labels,
no TSFM. Anchor selection is deterministic and depends only on the
sample_uid and the support, so multiprocess and repeated runs agree bit for
bit.

KEEP semantics (frozen here, per §2): KEEP modifies nothing, so there is no
action position to align a post-action anchor to -- the prequential contrast
``forecast_error(KEEP -> Y) - forecast_error(APPLY(a) -> Y)`` borrows the
anchor targets of the *other* candidates in the same window (§2.4: KEEP and
APPLY share identical target/anchor/context). KEEP itself therefore has no
support and no anchors of its own: ``prequential_supported = 0`` and
``support_conformity_supported = 0`` (no support exists to mask and
reconstruct). This is not a coverage failure; KEEP is the always-legal
baseline arm whose score is fixed at 0 in the §7 tournament, and it is
implicit (the v3.3 candidate table carries no KEEP rows).

Anchor rule (main-agent decision, 2026-09): the adopted reading of §2.3
("固定 horizons 8/16/32 + 最多 3 个") is **multi-horizon** -- each support run
contributes one anchor per feasible horizon (8, then 16, then 32, overlapping
starts), capped at ``MAX_ANCHORS`` per candidate. The stricter Phase-0 reading
("one anchor per run at the largest feasible horizon") is preserved as
``multi_horizon=False`` and both readings' coverage numbers are reported by
the Phase 0 audit. Note the multi-horizon anchors of one run share their
start, so their targets overlap; they are correlated evidence, which the
§2.5 lcb statistics do not model -- recorded here as a known limitation.
"""

import hashlib
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from introact_ts.actions import (  # noqa: E402
    Action, apply_action, missing_mask, _mask_runs,
)
from v33_labels import hash_array  # noqa: E402

# -- frozen ACV constants (pre-registered §2, do not tune) ---------------------

#: Anchor target block lengths. Longest feasible horizon wins per run.
HORIZONS = (8, 16, 32)
#: Max anchors per candidate.
MAX_ANCHORS = 3
#: Minimum finite, action-untouched context points for support conformity:
#: the TSFM reconstructs the masked support from what surrounds it, so a
#: handful of observed points outside the support must exist. Far below any
#: realistic TSFM context; this only certifies the *structural* minimum.
MIN_CONFORMITY_CONTEXT = 8
#: Shadow-certificate evidence sensitivity, reused for geometry inference
#: (identical to v34_shadow_certificate.EVIDENCE_MIN_RUN / BLOCK_MIN_RUN).
EVIDENCE_MIN_RUN = 8
BLOCK_MIN_RUN = 4

KEEP_ROLE = "baseline_arm"


# -- changed support -----------------------------------------------------------


def rerun_operator(series: np.ndarray, family: str, params: dict):
    """Re-run the production operator for one candidate.

    Returns the ``ActionOutcome``. Callers verify
    ``hash_array(out.series) == candidate_table['output_hash']`` -- the gate-1
    proof that the re-run reproduces the frozen candidate exactly.
    """
    return apply_action(np.asarray(series, dtype=np.float64),
                        Action(family), **params)


def value_changed(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Points whose value the operator actually rewrote.

    Compared at the 6-decimal resolution of ``hash_array`` so this mask is
    exactly consistent with the output-hash verification: any point counted
    here is a point where the hashed bytes differ. NaN -> finite (IMPUTE
    fill) counts as changed; finite -> identical value does not, even when
    the operator's ``touched`` declaration covers it (a frozen-run fill can
    land on the frozen value).
    """
    a = np.asarray(before, dtype=np.float64)
    b = np.asarray(after, dtype=np.float64)
    nan_flip = np.isfinite(a) != np.isfinite(b)
    both = np.isfinite(a) & np.isfinite(b)
    diff = np.zeros(len(a), dtype=bool)
    diff[both] = np.round(a[both], 6) != np.round(b[both], 6)
    return nan_flip | diff


def changed_support_mask(series: np.ndarray, family: str, outcome) -> np.ndarray:
    """The candidate's changed support: points the action actually modified,
    in input-window coordinates.

    - KEEP / no-op: empty support.
    - IMPUTE / DESPIKE: the operator's ``touched`` declaration intersected
      with the actual value change.
    - DENOISE: ``touched`` is None (whole-window rewrite), so the support is
      every point whose value moved.
    - RESEGMENT: length-changing. The action *discards* the complement of
      the kept span ``[lo, hi)``; values inside the kept span are copied
      verbatim. Support = discarded positions ``[0, lo) U [hi, T)``.
    """
    x = np.asarray(series, dtype=np.float64)
    T = len(x)
    if family == "KEEP":
        return np.zeros(T, dtype=bool)
    y = np.asarray(outcome.series, dtype=np.float64)
    if family == "RESEGMENT":
        support = np.ones(T, dtype=bool)
        lo = int(outcome.params.get("lo", 0))
        hi = int(outcome.params.get("hi", lo + len(y)))
        support[max(0, lo):min(T, hi)] = False
        return support
    if len(y) != T:
        # Defensive: only RESEGMENT changes length. Unverifiable otherwise.
        return np.ones(T, dtype=bool)
    changed = value_changed(x, y)
    if outcome.touched is not None:
        touched = np.asarray(outcome.touched)
        if touched.dtype == bool and len(touched) == T:
            return touched & changed
    return changed


def retain_span(family: str, outcome, T: int):
    """Window span that survives into the action output (input coordinates).

    RESEGMENT keeps ``[lo, hi)``; every other family keeps the whole window.
    Anchor targets must come from the retained span: a discarded point is not
    available as a post-action observation under APPLY.
    """
    if family == "RESEGMENT":
        lo = int(outcome.params.get("lo", 0))
        hi = int(outcome.params.get("hi", T))
        return max(0, lo), min(T, hi)
    return 0, T


def support_runs(support: np.ndarray) -> list:
    """Contiguous True runs of the support mask as (lo, hi) half-open pairs."""
    return _mask_runs(np.asarray(support, dtype=bool))


# -- geometry (identical logic to v34_shadow_certificate.geometry_of) ---------


def evidence_mask(series: np.ndarray) -> np.ndarray:
    """Real missing evidence: NaN plus stuck-sensor runs, NaN-layout only."""
    return missing_mask(np.asarray(series, dtype=np.float64),
                        min_run=EVIDENCE_MIN_RUN)


def geometry_of(series: np.ndarray) -> str:
    """'block' when the missing evidence is dominated by contiguous runs of
    >= BLOCK_MIN_RUN points, else 'scattered'. Evidence-free -> 'block'.
    Byte-identical rule to v34_shadow_certificate.geometry_of, copied here so
    Phase 1/2 import it from the shared module."""
    ev = evidence_mask(series)
    if not ev.any():
        return "block"
    block_pts = sum(hi - lo for lo, hi in _mask_runs(ev)
                    if hi - lo >= BLOCK_MIN_RUN)
    return "block" if 2 * block_pts >= int(ev.sum()) else "scattered"


# -- anchor selection ----------------------------------------------------------


def _anchor_key(sample_uid: str, run_lo: int, run_hi: int, horizon: int) -> str:
    """Deterministic per-anchor ordering key from sample_uid + support only."""
    return hashlib.sha256(
        f"{sample_uid}|acv-anchor|{run_lo}|{run_hi}|{horizon}"
        .encode("utf-8")).hexdigest()


def eligible_anchor_mask(series: np.ndarray, support: np.ndarray,
                         retain=(0, None)) -> np.ndarray:
    """Points allowed as anchor targets: finite in the original (corrupted)
    series, untouched by the action, and inside the retained span.

    Finiteness is read off the corrupted window itself, so a target can never
    be a materialised NaN -- the probe-materialised series is never built
    here.
    """
    x = np.asarray(series, dtype=np.float64)
    T = len(x)
    lo, hi = retain
    hi = T if hi is None else hi
    elig = np.isfinite(x) & ~np.asarray(support, dtype=bool)
    out = np.zeros(T, dtype=bool)
    out[max(0, lo):min(T, hi)] = elig[max(0, lo):min(T, hi)]
    return out


def run_anchor_capacities(series: np.ndarray, support: np.ndarray,
                          retain=(0, None), horizons=HORIZONS) -> list:
    """Per support run, the first eligible post-run block and which horizons
    fit it.

    Each entry: ``run_lo/run_hi`` (the support run), ``block_start`` and
    ``block_len`` (the first maximal run of eligible points at or after the
    run end), and ``feasible_horizons`` (the horizons the block can host).
    Reported separately from ``select_anchors`` so the audit can quantify
    both §2 readings -- multi-horizon (one anchor per feasible horizon,
    overlapping starts, adopted) and legacy (exactly one anchor per run at
    the largest feasible horizon) -- from the same structural pass.
    """
    x = np.asarray(series, dtype=np.float64)
    T = len(x)
    elig = eligible_anchor_mask(x, support, retain)
    caps = []
    for lo, hi in support_runs(support):
        s = hi
        while s < T and not elig[s]:
            s += 1
        e = s
        while e < T and elig[e]:
            e += 1
        caps.append({"run_lo": int(lo), "run_hi": int(hi),
                     "block_start": int(s), "block_len": int(e - s),
                     "feasible_horizons":
                         [int(H) for H in horizons if e - s >= H]})
    return caps


def select_anchors(sample_uid: str, series: np.ndarray, support: np.ndarray,
                   horizons=HORIZONS, max_anchors: int = MAX_ANCHORS,
                   retain=(0, None), multi_horizon: bool = True) -> list:
    """Up to ``max_anchors`` post-action anchor target blocks for one candidate.

    Multi-horizon rule (adopted, ``multi_horizon=True``): for each support
    run, try the horizons in the fixed order (8, 16, 32) and emit one anchor
    per feasible horizon, all starting at the first block of consecutive
    eligible points at or after the run's end; runs whose trailing eligible
    run is shorter than the smallest horizon contribute nothing (horizon
    insufficient -> skipped, per §2).

    Legacy rule (``multi_horizon=False``, the stricter Phase-0 reading): one
    anchor per run, at the largest horizon that fits.

    Under both rules, when more than ``max_anchors`` anchors survive, the cap
    is chosen by the sha256 ordering key of (sample_uid, run, horizon) --
    a function of the uid and the support alone, so multiprocess and repeated
    runs select bit-identical anchors.

    Guarantees (test-enforced): every anchor target is disjoint from the
    support, consists solely of original finite observations, and the call is
    deterministic in (sample_uid, series, support).
    """
    anchors = []
    for cap in run_anchor_capacities(series, support, retain, horizons):
        feasible = cap["feasible_horizons"]
        if not feasible:
            continue
        emit = sorted(feasible) if multi_horizon else [max(feasible)]
        for H in emit:
            anchors.append({"run_lo": cap["run_lo"], "run_hi": cap["run_hi"],
                            "horizon": int(H), "start": cap["block_start"],
                            "end": int(cap["block_start"] + H)})
    if len(anchors) > max_anchors:
        keyed = sorted(anchors, key=lambda a: _anchor_key(
            sample_uid, a["run_lo"], a["run_hi"], a["horizon"]))
        anchors = keyed[:max_anchors]
    anchors.sort(key=lambda a: (a["start"], a["horizon"]))
    return anchors


def anchor_failure_reason(series: np.ndarray, support: np.ndarray,
                          anchors: list, retain=(0, None)):
    """Why a supported candidate has no valid anchor, or None when it has one.

    ``support_reaches_window_end``: the last support run ends too close to
    the window end for even the shortest horizon of real observations.
    ``fragmented_tail``: eligible points exist after every run, but no
    contiguous block reaches the smallest horizon.
    """
    if anchors or not np.asarray(support, dtype=bool).any():
        return None
    T = len(series)
    _, rhi = retain
    rhi = T if rhi is None else rhi
    last_hi = max(hi for _, hi in support_runs(support))
    if last_hi + min(HORIZONS) > rhi:
        return "support_reaches_window_end"
    return "fragmented_tail"


# -- per-candidate audit record --------------------------------------------------


def audit_candidate(sample_uid: str, series: np.ndarray, family: str,
                    params: dict, multi_horizon: bool = True) -> dict:
    """The full structural ACV audit record for one candidate.

    Pure function of (uid, corrupted series, family, params). The operator is
    re-run through the production dispatch; the caller compares
    ``output_hash`` against the frozen candidate table (gate 1).
    ``multi_horizon`` selects the anchor rule (see ``select_anchors``); the
    adopted rule is multi-horizon and is the default everywhere.
    """
    x = np.asarray(series, dtype=np.float64)
    T = len(x)
    if family == "KEEP":
        # KEEP is implicit (no candidate-table rows). It modifies nothing, so
        # there is no action position to align anchors to; it borrows other
        # candidates' anchors as the baseline arm (see module docstring).
        return {
            "sample_uid": sample_uid, "family": "KEEP", "role": KEEP_ROLE,
            "applicable": True, "output_hash": hash_array(x.copy()),
            "support_n": 0, "support_runs": [], "anchors": [],
            "prequential_supported": 0, "support_conformity_supported": 0,
            "anchor_failure_reason": None,
            "geometry": geometry_of(x),
        }
    out = rerun_operator(x, family, params)
    y = np.asarray(out.series, dtype=np.float64)
    if out.applicable:
        support = changed_support_mask(x, family, out)
        retain = retain_span(family, out, T)
    else:
        # Operator declined: output is the untouched input, no support.
        support = np.zeros(T, dtype=bool)
        retain = (0, T)
    anchors = select_anchors(sample_uid, x, support, retain=retain,
                             multi_horizon=multi_horizon)
    caps = run_anchor_capacities(x, support, retain)
    runs = support_runs(support)
    n_support = int(support.sum())

    # Structural invariants, re-checked per candidate on every run (gates 4-5).
    for a in anchors:
        assert not support[a["start"]:a["end"]].any(), \
            "anchor target intersects changed support"
        assert np.isfinite(x[a["start"]:a["end"]]).all(), \
            "anchor target contains a non-finite (materialised) point"

    context = int(eligible_anchor_mask(x, support, retain).sum())
    conformity = int(n_support > 0 and context >= MIN_CONFORMITY_CONTEXT)
    return {
        "sample_uid": sample_uid,
        "family": family,
        "applicable": bool(out.applicable),
        "output_hash": hash_array(y) if out.applicable else None,
        "output_len": int(len(y)),
        "window_len": int(T),
        "retain_span": [int(retain[0]), int(retain[1])],
        "support_n": n_support,
        "support_runs": [[int(lo), int(hi)] for lo, hi in runs],
        "n_support_runs": len(runs),
        "run_capacities": caps,
        "anchors": anchors,
        "n_anchors": len(anchors),
        "anchor_rule": "multi_horizon" if multi_horizon else "legacy_per_run",
        "prequential_supported": int(len(anchors) > 0),
        "support_conformity_supported": conformity,
        "conformity_context_n": context,
        "anchor_failure_reason": anchor_failure_reason(x, support, anchors,
                                                       retain),
        "geometry": geometry_of(x),
    }
