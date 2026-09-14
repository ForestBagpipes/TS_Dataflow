"""Unit tests for v3.8 Phase 0 (oracle replay + IMPUTE mask audit).

Pure-logic tests only: no corpus rebuild, no server, no frozen artifacts.
The two-process determinism test spawns real subprocesses on a fixed
synthetic series; the corpus-level determinism gate itself runs on the
server and is recorded in results/v38_phase0_manifest.json.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

import v38_impute_mask_audit as audit  # noqa: E402
import v38_oracle_replay as replay  # noqa: E402
from introact_ts.probe import materialize_for_probe  # noqa: E402


def _wiggle(T=256, seed=0):
    """Continuous noise: no exact repeats, no NaN."""
    rng = np.random.RandomState(seed)
    return np.cumsum(rng.randn(T)) + rng.randn(T) * 0.1


# -- layering ---------------------------------------------------------------------


def test_layers_are_mutually_exclusive_and_exhaustive():
    nan_only = _wiggle(seed=1)
    nan_only[100:120] = np.nan
    flat_only = _wiggle(seed=2)
    flat_only[100:130] = flat_only[99]
    mixed = _wiggle(seed=3)
    mixed[50:70] = np.nan
    mixed[150:180] = mixed[149]
    neither = _wiggle(seed=4)

    cases = {
        "actual_nan_only": nan_only,
        "finite_flatline_only": flat_only,
        "mixed": mixed,
        "neither": neither,
    }
    seen = set()
    for want, x in cases.items():
        layer = audit.window_layer(audit.raw_nan_mask(x),
                                   audit.finite_flatline_mask(x))
        assert layer == want, f"expected {want}, got {layer}"
        assert layer in audit.LAYERS
        seen.add(layer)
    # every window lands in exactly one layer, and all four layers exist
    assert seen == set(audit.LAYERS)


def test_flatline_threshold_and_finite_only():
    x = _wiggle(seed=5)
    x[10:25] = 42.4242   # 15-long constant run: below k=16
    x[60:76] = 43.4343   # 16-long constant run: at k
    x[120:150] = np.nan  # NaN run must never be a flatline
    fm = audit.finite_flatline_mask(x)
    assert not fm[10:25].any(), "15-long run must stay below k=16"
    assert fm[60:76].all(), "16-long run must be flagged"
    assert not fm[120:150].any(), "NaN is not a finite flatline"
    assert np.isfinite(x[fm]).all()
    # mask positions are exactly the constant run
    assert set(np.flatnonzero(fm)) == set(range(60, 76))


def test_flatline_matches_corpus_injection_scale():
    # corpus.py injects flatlines of length 24..50 at T=512; all must flag
    for length in (24, 33, 50):
        x = _wiggle(T=512, seed=length)
        x[200:200 + length] = x[199]
        fm = audit.finite_flatline_mask(x)
        assert fm[200:200 + length].all()


# -- raw vs materialised -----------------------------------------------------------


def test_materialize_erases_nan_so_masks_must_come_from_raw():
    x = _wiggle(seed=6)
    x[80:110] = np.nan
    nm_raw = audit.raw_nan_mask(x)
    mat = materialize_for_probe(x)
    nm_mat = audit.raw_nan_mask(mat)
    assert nm_raw.sum() == 30
    assert nm_mat.sum() == 0, "forward-fill erases the NaN evidence"
    # gap geometry is only recoverable from the raw series
    assert audit.gap_runs(nm_raw) == [30]
    assert audit.gap_runs(nm_mat) == []


# -- gap runs and anchors ------------------------------------------------------------


def test_gap_runs_and_anchor_geometry_boundaries():
    T = 64
    x = np.arange(T, dtype=np.float64)
    x[0:5] = np.nan        # leading run: no left anchor
    x[20:23] = np.nan      # interior run: both anchors
    x[60:64] = np.nan      # trailing run: no right anchor
    nm = audit.raw_nan_mask(x)
    assert audit.gap_runs(nm) == [5, 3, 4]
    geo = audit.anchor_geometry(x, nm)
    assert [(g["lo"], g["hi"]) for g in geo] == [(0, 5), (20, 23), (60, 64)]
    assert (geo[0]["left_anchor"], geo[0]["right_anchor"]) == (False, True)
    assert (geo[1]["left_anchor"], geo[1]["right_anchor"]) == (True, True)
    assert (geo[2]["left_anchor"], geo[2]["right_anchor"]) == (True, False)


def test_anchor_geometry_single_point_gap():
    x = np.arange(10, dtype=np.float64)
    x[5] = np.nan
    geo = audit.anchor_geometry(x)
    assert len(geo) == 1 and geo[0]["length"] == 1
    assert geo[0]["left_anchor"] and geo[0]["right_anchor"]


# -- mask origin --------------------------------------------------------------------


def test_mask_origin_components():
    x = _wiggle(seed=7)
    x[100:120] = np.nan
    x[150:170] = x[149]
    nm = audit.raw_nan_mask(x)
    fm = audit.finite_flatline_mask(x)
    T = len(x)

    def touched(*spans):
        m = np.zeros(T, dtype=bool)
        for a, b in spans:
            m[a:b] = True
        return m

    assert audit.mask_origin(touched(), nm, fm) == "empty"
    assert audit.mask_origin(touched((100, 120)), nm, fm) == "raw_nan"
    assert audit.mask_origin(touched((150, 170)), nm, fm) == "finite_flatline"
    assert audit.mask_origin(touched((100, 120), (150, 170)),
                             nm, fm) == "raw_nan+finite_flatline"
    assert audit.mask_origin(touched((200, 210)), nm, fm) == "other_finite"
    assert audit.mask_origin(touched((100, 120), (200, 210)),
                             nm, fm) == "raw_nan+other_finite"


# -- replay comparison helpers --------------------------------------------------------


def _arm_metric(**over):
    m = {k: 0.5 for k in replay.ARM_FLOAT_FIELDS}
    m.update({k: 10 for k in replay.ARM_INT_FIELDS})
    m["protected_stratum_edit"] = {"clean": 0.1, "hard": 0.0}
    m.update(over)
    return m


def test_compare_floats_tolerance_boundary():
    got = {"a": 1.0 + 5e-10, "b": 2.0 + 2e-9}
    ref = {"a": 1.0, "b": 2.0}
    out = replay.compare_floats(got, ref, ("a", "b"))
    assert out["a"]["ok"] and not out["b"]["ok"]


def test_compare_arm_metrics_pass_and_fail():
    ref = _arm_metric()
    got = dict(ref)
    got["protected_stratum_edit"] = dict(ref["protected_stratum_edit"])
    assert replay.compare_arm_metrics(got, ref)["pass"]
    bad = dict(got)
    bad["beneficial_coverage"] = ref["beneficial_coverage"] + 1e-8
    assert not replay.compare_arm_metrics(bad, ref)["pass"]
    bad_int = dict(got)
    bad_int["committed"] = ref["committed"] + 1
    assert not replay.compare_arm_metrics(bad_int, ref)["pass"]
    bad_strata = dict(got)
    bad_strata["protected_stratum_edit"] = {"clean": 0.1}  # missing key
    assert not replay.compare_arm_metrics(bad_strata, ref)["pass"]


def test_compare_float_dict_keys_exact():
    a = {"x": 1.0, "y": 2.0}
    assert replay.compare_float_dict(a, dict(a))["ok"]
    assert not replay.compare_float_dict(a, {"x": 1.0})["ok"]
    assert not replay.compare_float_dict(a, {"x": 1.0, "y": 2.0 + 1e-8})["ok"]


# -- oracle pick rule ------------------------------------------------------------------


def test_unrestricted_oracle_picks_rule():
    def row(uid, fam, gain, bns, loss=0.0):
        return {"sample_uid": uid, "family": fam, "rung": "default",
                "params": {}, "true_repair_gain": gain,
                "beneficial_and_safe": bns, "dataset": "D"}

    rows = [
        row("w1", "IMPUTE", 0.3, True),
        row("w1", "DENOISE", 0.5, True),       # higher gain wins
        row("w1", "RESEGMENT", 0.9, True),     # closed family, never picked
        row("w1", "DESPIKE", 0.7, False),      # not b&s, never picked
        row("w2", "IMPUTE", 0.4, False),
    ]
    picks = audit.unrestricted_oracle_picks(rows)
    assert picks["w1"]["family"] == "DENOISE"
    assert picks["w2"] is None


# -- two-process determinism -------------------------------------------------------------


_DIGEST_SNIPPET = (
    "import sys, json\n"
    "sys.path.insert(0, %r)\n"
    "sys.path.insert(0, %r)\n"
    "import numpy as np\n"
    "from v38_impute_mask_audit import digest_of_windows\n"
    "def mk(i):\n"
    "    rng = np.random.RandomState(123 + i)\n"
    "    x = np.cumsum(rng.randn(256)) + rng.randn(256) * 0.1\n"
    "    x[20 * i:20 * i + 10] = np.nan\n"
    "    x[150:170] = x[149]\n"
    "    return ('uid%%d' %% i, x)\n"
    "d = digest_of_windows([mk(i) for i in range(4)])\n"
    "print(json.dumps({'sha256': d['sha256'], 'n': d['n_windows']}))\n"
    % (str(ROOT / "src"), str(ROOT / "experiments")))


def _digest_series():
    return [("uid%d" % i, _mk(i)) for i in range(4)]


def _mk(i):
    rng = np.random.RandomState(123 + i)
    x = np.cumsum(rng.randn(256)) + rng.randn(256) * 0.1
    x[20 * i:20 * i + 10] = np.nan
    x[150:170] = x[149]
    return x


def test_two_process_digest_determinism():
    outs = []
    for _ in range(2):
        proc = subprocess.run([sys.executable, "-c", _DIGEST_SNIPPET],
                              capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr
        outs.append(json.loads(proc.stdout.strip()))
    assert outs[0] == outs[1], "two independent processes must agree"

    # and the in-process build agrees with both
    d = audit.digest_of_windows(_digest_series())
    assert d["sha256"] == outs[0]["sha256"]
