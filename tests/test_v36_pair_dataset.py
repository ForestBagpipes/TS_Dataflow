"""v3.6 Phase 0 pair-dataset tests: KEEP uniqueness, pair symmetry, no
cross-window pairs, label rules 1–4, two-process determinism, and the
episode/sample_uid bijection. Pre-registration: docs/v3_6_pair_preregistration.md §4."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

import v36_pair_dataset as m  # noqa: E402

INPUT = ROOT / "results" / "v33_training_data.jsonl"
NEEDS_TABLE = pytest.mark.skipif(not INPUT.exists(), reason="frozen candidate table missing")


def make_cand(uid, family, rung="default", bns=False, gain=0.0, loss=0.0, params=None):
    return {
        "sample_uid": uid,
        "window_id": 0,
        "dataset": "TEST",
        "stratum": "contaminated",
        "family": family,
        "rung": rung,
        "params": params or {},
        "features": {"confidence": 0.5},
        "beneficial": bns,
        "harmful": False,
        "safe": True,
        "beneficial_and_safe": bns,
        "true_loss": loss,
        "true_repair_gain": gain,
        "output_hash": "deadbeef",
    }


def fwd_pairs(ep):
    pairs, stats = m.generate_pairs(ep)
    return [p for p in pairs if p["pair_direction"] == "forward"], pairs, stats


def pair_of(pairs, fam_i, fam_j):
    return [
        p for p in pairs
        if p["cand_i"]["family"] == fam_i and p["cand_j"]["family"] == fam_j
    ]


# --------------------------------------------------------------------------
# Synthetic-episode unit tests (label rules 1–4, KEEP, symmetry, windows)
# --------------------------------------------------------------------------


def test_keep_present_unique_and_label_semantics():
    cands = [make_cand("u1", "IMPUTE", bns=True, gain=1.0),
             make_cand("u1", "DESPIKE", bns=False)]
    eps = m.build_episodes(cands)
    ep = next(iter(eps.values()))
    assert ep["keep"]["family"] == "KEEP"
    assert sum(1 for c in ep["candidates"] if c["family"] == "KEEP") == 0
    keep = ep["keep"]
    # KEEP leaves data untouched: loss/gain 0, safe but never beneficial_and_safe.
    assert keep["true_loss"] == 0.0 and keep["true_repair_gain"] == 0.0
    assert keep["safe"] is True and keep["beneficial_and_safe"] is False
    assert keep["features"] == {}  # empty marker, no deployable features


def test_rule1_beneficial_and_safe_beats_keep():
    ep = next(iter(m.build_episodes([make_cand("u1", "IMPUTE", bns=True, gain=2.0)]).values()))
    fwd, _, _ = fwd_pairs(ep)
    p = pair_of(fwd, "IMPUTE", "KEEP")
    assert len(p) == 1 and p[0]["label"] == 1
    # negative: KEEP must never be preferred over a B&S action
    assert pair_of(fwd, "KEEP", "IMPUTE") == []


def test_rule2_keep_beats_non_beneficial_and_safe():
    ep = next(iter(m.build_episodes([make_cand("u1", "DESPIKE", bns=False)]).values()))
    fwd, _, _ = fwd_pairs(ep)
    p = pair_of(fwd, "KEEP", "DESPIKE")
    assert len(p) == 1 and p[0]["label"] == 1
    # negative: a non-B&S action must never be preferred over KEEP
    assert pair_of(fwd, "DESPIKE", "KEEP") == []


def test_rule3_higher_gain_wins_then_loss_tiebreak_then_tie():
    # higher true_repair_gain wins
    cands = [make_cand("u1", "IMPUTE", bns=True, gain=2.0, loss=0.5),
             make_cand("u1", "DESPIKE", bns=True, gain=1.0, loss=0.1)]
    ep = next(iter(m.build_episodes(cands).values()))
    fwd, _, stats = fwd_pairs(ep)
    p = pair_of(fwd, "IMPUTE", "DESPIKE")
    assert len(p) == 1 and p[0]["label"] == 1 and stats["ties"] == 0

    # gain tie -> lower true_loss wins
    cands = [make_cand("u1", "IMPUTE", bns=True, gain=1.0, loss=0.5),
             make_cand("u1", "DESPIKE", bns=True, gain=1.0, loss=0.1)]
    ep = next(iter(m.build_episodes(cands).values()))
    fwd, _, stats = fwd_pairs(ep)
    assert len(pair_of(fwd, "DESPIKE", "IMPUTE")) == 1 and stats["ties"] == 0

    # full tie -> no B&S-B&S pair at all, tie counted
    cands = [make_cand("u1", "IMPUTE", bns=True, gain=1.0, loss=0.5),
             make_cand("u1", "DESPIKE", bns=True, gain=1.0, loss=0.5)]
    ep = next(iter(m.build_episodes(cands).values()))
    fwd, _, stats = fwd_pairs(ep)
    assert pair_of(fwd, "IMPUTE", "DESPIKE") == []
    assert pair_of(fwd, "DESPIKE", "IMPUTE") == []
    assert stats["ties"] == 1


def test_rule4_two_non_bns_never_form_a_training_pair():
    cands = [make_cand("u1", "DESPIKE", bns=False),
             make_cand("u1", "DENOISE", bns=False)]
    ep = next(iter(m.build_episodes(cands).values()))
    fwd, all_pairs, stats = fwd_pairs(ep)
    # only KEEP pairs exist; no DESPIKE-vs-DENOISE pair in either direction
    assert pair_of(all_pairs, "DESPIKE", "DENOISE") == []
    assert pair_of(all_pairs, "DENOISE", "DESPIKE") == []
    assert stats["nonbns_excluded_combos"] == 1
    assert {p["cand_j"]["family"] for p in fwd} == {"DESPIKE", "DENOISE"}
    assert all(p["cand_i"]["family"] == "KEEP" for p in fwd)


def test_pair_symmetry_forward_reverse():
    cands = [make_cand("u1", "IMPUTE", bns=True, gain=2.0),
             make_cand("u1", "DESPIKE", bns=True, gain=1.0),
             make_cand("u1", "DENOISE", bns=False)]
    ep = next(iter(m.build_episodes(cands).values()))
    _, pairs, _ = fwd_pairs(ep)
    fwd = [p for p in pairs if p["pair_direction"] == "forward"]
    rev = [p for p in pairs if p["pair_direction"] == "reverse"]
    assert len(fwd) == len(rev)
    rev_keys = {(m.cand_key(p["cand_j"]), m.cand_key(p["cand_i"])): p["label"] for p in rev}
    for p in fwd:
        key = (m.cand_key(p["cand_i"]), m.cand_key(p["cand_j"]))
        assert key in rev_keys
        assert rev_keys[key] == 1 - p["label"]


def test_pairs_never_cross_windows():
    cands = [make_cand("u1", "IMPUTE", bns=True, gain=2.0),
             make_cand("u2", "IMPUTE", bns=True, gain=1.0)]
    eps = m.build_episodes(cands)
    assert len(eps) == 2
    for ep in eps.values():
        _, pairs, _ = fwd_pairs(ep)
        for p in pairs:
            assert p["episode_id"] == ep["episode_id"]
            assert p["pair_id"].startswith(ep["episode_id"] + "|")
            assert p["sample_uid"] == ep["sample_uid"]


def test_episode_sample_uid_bijection_synthetic():
    cands = [make_cand("u1", "IMPUTE"), make_cand("u1", "DESPIKE"),
             make_cand("u2", "IMPUTE")]
    eps = m.build_episodes(cands)
    assert len(eps) == 2
    uids = [ep["sample_uid"] for ep in eps.values()]
    assert sorted(uids) == ["u1", "u2"]
    for ep in eps.values():
        assert {c["sample_uid"] for c in ep["candidates"]} == {ep["sample_uid"]}


# --------------------------------------------------------------------------
# Integration tests on the real frozen table (built into a tmp dir)
# --------------------------------------------------------------------------


def _run_builder(tmp_path, tag):
    out = tmp_path / f"pairs_{tag}.jsonl"
    integ = tmp_path / f"integrity_{tag}.json"
    subprocess.run(
        [sys.executable, str(ROOT / "experiments" / "v36_pair_dataset.py"),
         "--out", str(out), "--integrity", str(integ)],
        check=True, cwd=str(ROOT), capture_output=True, text=True,
    )
    return out, integ


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    if not INPUT.exists():
        pytest.skip("frozen candidate table missing")
    tmp = tmp_path_factory.mktemp("v36pair")
    out, integ = _run_builder(tmp, "a")
    records = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    return records, json.loads(integ.read_text(encoding="utf-8")), out


@NEEDS_TABLE
def test_integrity_all_pass(built):
    _, integrity, _ = built
    assert integrity["overall"] == "PASS"
    for name, chk in integrity["checks"].items():
        assert chk["status"] == "PASS", f"{name}: {chk['detail']}"


@NEEDS_TABLE
def test_episode_count_and_uid_bijection_real(built):
    records, integrity, _ = built
    assert integrity["episode_count"] == 827
    assert integrity["candidate_count"] == 2414
    by_ep = {}
    for r in records:
        by_ep.setdefault(r["episode_id"], set()).add(r["sample_uid"])
    assert all(len(v) == 1 for v in by_ep.values())


@NEEDS_TABLE
def test_keep_unique_real(built):
    records, _, _ = built
    keep_per_ep = {}
    for r in records:
        for side in ("cand_i", "cand_j"):
            if r[side]["family"] == "KEEP":
                keep_per_ep.setdefault(r["episode_id"], set()).add(
                    json.dumps(r[side], sort_keys=True)
                )
    assert keep_per_ep, "no KEEP pair found"
    assert all(len(v) == 1 for v in keep_per_ep.values())


@NEEDS_TABLE
def test_determinism_two_processes(tmp_path):
    out_a, _ = _run_builder(tmp_path, "d1")
    out_b, _ = _run_builder(tmp_path, "d2")
    ha = hashlib.sha256(out_a.read_bytes()).hexdigest()
    hb = hashlib.sha256(out_b.read_bytes()).hexdigest()
    assert ha == hb
