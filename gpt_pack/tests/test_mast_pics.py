"""MAST-PICS contract tests (v3.3, docs/v3_3_mast_pics_design.md §3-4)."""

import numpy as np
import pytest

from introact_ts.contextual_shield import ShieldConfig
from introact_ts.mast_pics import (
    MAST_BENEFIT_FEATURES,
    MAST_HARM_FEATURES,
    MASTPICS,
    SupportIndex,
    v2_hard_gate_ok,
    v2_structure_ok,
)


def _row(uid, family, dataset, beneficial, harmful, loss, profile,
         distortion=0.0, gain=0.1, seed=0):
    rng = np.random.RandomState(seed)
    feats = {n: float(rng.randn()) for n in MAST_BENEFIT_FEATURES
             if n != "missing_fraction"}
    for n in ("hypothesis", "dominant_defect", "secondary_defect",
              "route_source", "rung"):
        feats[n] = "x"
    feats["action_family"] = family
    return {
        "sample_uid": uid, "dataset": dataset, "family": family,
        "features": feats, "profile": list(profile),
        "missing_fraction": 0.1,
        "struct_distortion": distortion,
        "delta_utility": 0.02, "risk": 0.1,
        "true_loss": loss, "beneficial": float(beneficial),
        "harmful": float(harmful),
        "beneficial_and_safe": float(beneficial and not harmful),
        "true_repair_gain": gain,
    }


def test_support_index_self_exclusion():
    rng = np.random.RandomState(0)
    # Clustered training profiles: ID neighbours are close, an alien direction
    # is far. (An unstructured Gaussian cloud in 12 dims is nearly orthogonal
    # everywhere and would make the assertion vacuous.)
    centers = rng.randn(5, 12)
    P = np.vstack([centers[i % 5] + rng.randn(12) * 0.01 for i in range(50)])
    idx = SupportIndex(K=5).fit(P)
    own = idx.score(P, exclude_self=True)
    alien = (np.arange(12, dtype=float) + 1.0) * 100.0
    far = idx.score(alien[None, :])[0]
    assert far > np.percentile(own, 95)
    # A training point queried against its own index is supported.
    assert idx.score(P[:1])[0] < np.percentile(own, 95)


def test_support_index_small_fold_degenerates_gracefully():
    P = np.random.RandomState(1).randn(5, 12)
    idx = SupportIndex(K=20).fit(P)
    s = idx.score(P, exclude_self=True)
    assert len(s) == 5 and np.isfinite(s).all()


def test_v2_structure_thresholds():
    assert v2_structure_ok("DENOISE", 0.05)
    assert not v2_structure_ok("DENOISE", 0.2)
    assert not v2_structure_ok("DESPIKE", 1e-9)  # DESPIKE tau is 0.0
    assert v2_structure_ok("IMPUTE", 0.01)


def test_v2_hard_gate():
    row = {"family": "IMPUTE", "delta_utility": 0.02,
           "struct_distortion": 0.01, "risk": 0.1}
    assert v2_hard_gate_ok(row)
    row["risk"] = 0.9
    assert not v2_hard_gate_ok(row)


def _toy_corpus(n_per_fam=40, n_sources=3):
    rows = []
    rng = np.random.RandomState(7)
    for s in range(n_sources):
        base = rng.randn(12) * (s + 1)
        for i in range(n_per_fam):
            for fam in ("DENOISE", "IMPUTE"):
                ben = int(rng.rand() < 0.5)
                loss = 0.0 if ben else float(rng.choice([0.0, 1.0]))
                rows.append(_row(f"u{s}_{i}_{fam}", fam, f"ds{s}",
                                 ben, int(loss > 0.03), loss,
                                 profile=base + rng.randn(12) * 0.01,
                                 distortion=0.005, seed=i))
    return rows


def test_mast_fit_and_decide_end_to_end():
    rows = _toy_corpus()
    train, cal = rows[: len(rows) // 2], rows[len(rows) // 2:]
    m = MASTPICS(ShieldConfig(min_family_n=20)).fit(train, cal)
    assert m.support_q95 > 0
    row = dict(cal[0])
    ok, reason = m.decide(row)
    assert reason in ("accepted", "benefit_threshold", "harm_cap",
                      "ood_hazard", "no_threshold", "family_closed",
                      "family_ineligible")
    # RESEGMENT is closed regardless of scores.
    bad = dict(row)
    bad["family"] = "RESEGMENT"
    ok, reason = m.decide(bad)
    assert not ok and reason == "family_closed"


def test_hazard_requires_both_low_support_and_unstable():
    rows = _toy_corpus()
    train, cal = rows[: len(rows) // 2], rows[len(rows) // 2:]
    m = MASTPICS(ShieldConfig(min_family_n=20)).fit(train, cal)
    alien = dict(cal[0])
    alien["profile"] = list(np.ones(12) * 100.0)
    # Low support but structurally tame: no hazard.
    alien["struct_distortion"] = 0.001
    assert not m._hazard(alien, 0.0, 10.0)
    # Low support and unstable: hazard.
    alien["struct_distortion"] = 0.5
    assert m._hazard(alien, 0.0, 10.0)
    # Unstable but supported: no hazard.
    assert not m._hazard(alien, 0.0, 0.0)
    # support-only mode hazards on low support alone.
    m2 = MASTPICS(ShieldConfig(min_family_n=20), gate_mode="support")
    m2.fit(train, cal)
    assert m2._hazard(alien, 0.0, 10.0)


def test_constant_head_when_single_class():
    rows = [dict(r, beneficial=0.0, harmful=1.0, true_loss=1.0,
                 beneficial_and_safe=0.0) for r in _toy_corpus()]
    train, cal = rows[: len(rows) // 2], rows[len(rows) // 2:]
    m = MASTPICS(ShieldConfig(min_family_n=20)).fit(train, cal)
    ok, reason = m.decide(cal[0])
    assert not ok  # nothing beneficial exists; the shield must refuse
