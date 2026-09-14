"""Unit tests for v3.9 Phase 0 (MIRAGE-TS integration replay).

Pure-logic tests only: no corpus rebuild, no server, no frozen artifacts.
The corpus-level integrity gates (incumbent 1e-9 replay, 88/76/12 FACT_SHORT
equivalence, two-process decision digest) run on the server and are recorded
in results/v39_phase0_manifest.json; only the two-process determinism of the
digest helper itself is tested here on a fixed synthetic decision table.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

import v33_compare_arms as v33  # noqa: E402
import v39_phase0_replay as p0  # noqa: E402
from v38_explicit_impute_probe import impute_explicit_linear  # noqa: E402


def _wiggle(T=128, seed=0):
    rng = np.random.RandomState(seed)
    return np.cumsum(rng.randn(T)) + rng.randn(T) * 0.1 + 10.0


# -- FACT_SHORT operator contract -------------------------------------------------


def test_fact_short_certifies_runs_of_length_1_to_3_only():
    x = _wiggle(seed=1)
    x[10] = np.nan        # length 1
    x[30:32] = np.nan     # length 2
    x[50:53] = np.nan     # length 3
    x[70:74] = np.nan     # length 4: overlong for FACT_SHORT
    res = impute_explicit_linear(x, max_gap=p0.FACT_SHORT_MAX_GAP)
    cert = [(d["lo"], d["hi"], d["certified"], d["abstain_reason"])
            for d in res["gap_decisions"]]
    assert cert == [(10, 11, True, None), (30, 32, True, None),
                    (50, 53, True, None), (70, 74, False, "overlong_gap")]
    assert res["applicable"] and res["n_filled"] == 6


def test_fact_short_requires_two_sided_finite_anchors():
    x = _wiggle(seed=2)
    x[0:2] = np.nan       # touches the left endpoint
    x[126:128] = np.nan   # touches the right endpoint
    res = impute_explicit_linear(x, max_gap=p0.FACT_SHORT_MAX_GAP)
    assert [d["certified"] for d in res["gap_decisions"]] == [False, False]
    assert {d["abstain_reason"] for d in res["gap_decisions"]} == \
        {"boundary_gap"}
    assert not res["applicable"]


def test_fact_short_observed_support_strictly_unchanged():
    x = _wiggle(seed=3)
    x[40:43] = np.nan
    res = impute_explicit_linear(x, max_gap=p0.FACT_SHORT_MAX_GAP)
    obs = np.isfinite(x)
    assert np.array_equal(res["series"][obs], x[obs])
    assert np.isfinite(res["series"]).all()
    # touched mask is exactly the raw NaN mask
    assert np.array_equal(res["touched"], ~obs)


def test_fact_short_equals_wide_only_on_corpus_gap_distribution():
    # corpus-like: gap lengths {1,2,3} u {25..63} -> max_gap 3 == max_gap 16
    x = _wiggle(T=128, seed=4)
    x[10] = np.nan
    x[30:32] = np.nan
    x[50:53] = np.nan
    x[80:105] = np.nan    # 25-long missing block: abstained by both
    a = impute_explicit_linear(x, max_gap=3)
    b = impute_explicit_linear(x, max_gap=16)
    assert np.array_equal(a["series"], b["series"])
    assert np.array_equal(a["filled"], b["filled"])
    # counterexample: a 10-long gap separates the two tiers
    y = _wiggle(seed=5)
    y[60:70] = np.nan
    a2 = impute_explicit_linear(y, max_gap=3)
    b2 = impute_explicit_linear(y, max_gap=16)
    assert not a2["applicable"] and b2["applicable"]
    assert not np.array_equal(a2["series"], b2["series"])


def test_fact_short_linear_fill_exact():
    x = np.arange(12, dtype=np.float64)
    x[5:7] = np.nan
    res = impute_explicit_linear(x, max_gap=3)
    assert np.allclose(res["series"][5:7], [5.0, 6.0])


# -- priority resolution -------------------------------------------------------------


def _cand(family, gain=0.1, loss=0.0):
    return {"sample_uid": "w", "dataset": "D", "stratum": "contaminated",
            "true_kind": "k", "corrupted_hash": "h", "family": family,
            "rung": "default", "params": {}, "true_repair_gain": gain,
            "true_loss": loss, "beneficial": gain > 0, "beneficial_and_safe":
            gain > 0 and loss <= p0.HARM_LOSS}


def test_resolve_priority_orders():
    fact, pics = _cand("FACT_SHORT"), _cand("DESPIKE")
    assert p0.resolve_priority(fact, pics, "fact_first")[0] == "FACT_SHORT"
    assert p0.resolve_priority(fact, pics, "pics_first")[0] == \
        "PICS_non_IMPUTE"
    # fall-through when the first-priority side has nothing
    assert p0.resolve_priority(None, pics, "fact_first")[0] == \
        "PICS_non_IMPUTE"
    assert p0.resolve_priority(fact, None, "pics_first")[0] == "FACT_SHORT"
    assert p0.resolve_priority(None, None, "fact_first") == ("KEEP", None)


# -- frame discipline ------------------------------------------------------------------


def test_keep_placeholders_hold_the_frame_denominator():
    uids = ["w1", "w2", "w3"]
    meta = {u: {"dataset": "D", "stratum": "contaminated", "true_kind": "k",
                "corrupted_hash": "h"} for u in uids}
    rows = [_cand("IMPUTE") | {"sample_uid": "w1"},
            _cand("DESPIKE") | {"sample_uid": "w2"}]
    nonimpute = [r for r in rows if r["family"] != "IMPUTE"]
    framed = p0.with_keep_placeholders(nonimpute, uids, meta)
    assert len(framed) == 3  # w3 got a KEEP placeholder
    assert framed[-1]["family"] == "KEEP"
    committed = {"w1": None, "w2": (nonimpute[0], 0, "t", None), "w3": None}
    met = v33._episode_metrics(framed, committed)
    assert met["n_windows"] == 3 and met["committed"] == 1


def test_placeholder_rows_are_never_committable():
    meta = {"dataset": "D", "stratum": "clean", "true_kind": "k",
            "corrupted_hash": "h"}
    ph = p0.placeholder_row("w9", meta)
    from introact_ts.contextual_shield import EPISODE_FAMILY_ORDER
    assert ph["family"] not in EPISODE_FAMILY_ORDER


# -- target budget arithmetic -----------------------------------------------------------


def test_target_budget_arithmetic():
    stats = {"improved": 120, "gain_sum": 40.0, "committed": 100,
             "harmful": 10, "prot_edit": 4, "loss_sum": 30.0}
    targets = dict(p0.TARGETS)
    out = p0.target_budget(stats, targets, n_cont=440, n_frame=771,
                           prot_n=331)
    # bcov: ceil(0.30*440) - 120 = 132 - 120
    assert out["new_beneficial_commits_needed_for_bcov"] == 12
    # gain: 0.10*440 - 40 = 4
    assert abs(out["gain_deficit_sum"] - 4.0) < 1e-12
    assert abs(out["required_mean_gain_per_new_beneficial_commit"]
               - 4.0 / 12) < 1e-12
    # CHR: h <= (0.10*(100+12) - 10)/0.9 = 1.2/0.9 -> floor 1
    assert out["max_new_harmful_commits_at_required_beneficial"] == 1
    # h0/(c0+b) <= 0.10 -> b >= 10/0.10 - 100 = 0
    assert out["new_safe_commits_needed_for_chr_with_zero_new_harmful"] == 0
    # pme: floor(0.0055*331) = 1 -> headroom 1 - 4 = -3 (infeasible by adding)
    assert out["pme_protected_edit_budget"] == 1
    assert out["pme_headroom_edits"] == -3
    # damage: 0.0402*771 - 30
    assert abs(out["damage_headroom_sum"] - (0.0402 * 771 - 30.0)) < 1e-9


def test_target_budget_chr_infeasible_without_safe_commits():
    stats = {"improved": 0, "gain_sum": 0.0, "committed": 100,
             "harmful": 20, "prot_edit": 0, "loss_sum": 0.0}
    out = p0.target_budget(stats, dict(p0.TARGETS), n_cont=440, n_frame=771,
                           prot_n=331)
    # 20/(100+b) <= 0.10 -> b >= 100
    assert out["new_safe_commits_needed_for_chr_with_zero_new_harmful"] == 100


# -- five-quantity report ------------------------------------------------------------------


def test_arm_report_five_quantities():
    uids = [f"w{i}" for i in range(4)]
    rows = []
    for u in uids:
        rows.append({"sample_uid": u, "dataset": "D",
                     "stratum": "contaminated", "true_kind": "k",
                     "corrupted_hash": "h", "family": "DESPIKE",
                     "rung": "d", "params": {}, "true_repair_gain": 0.5,
                     "true_loss": 0.0, "beneficial": True,
                     "beneficial_and_safe": True})
    picks = {uids[0]: (rows[0], 0, "t", None),
             uids[1]: ({**rows[1], "true_loss": 0.5, "beneficial": False,
                        "beneficial_and_safe": False}, 0, "t", None),
             uids[2]: None, uids[3]: None}
    met = v33._episode_metrics(rows, picks)
    rep = p0.arm_report(met, picks, n_frame=4, n_proposed=3, n_applicable=2)
    assert rep["proposal_coverage"] == 0.75
    assert rep["applicability_coverage"] == 0.5
    assert rep["committed"] == 2 and rep["harmful_commits"] == 1
    assert rep["action_conditional_bs_precision"] == 0.5
    assert rep["action_conditional_chr"] == 0.5
    assert rep["bcov"] == 0.25
    assert rep["abstention_rate"] == 0.5


# -- two-process digest determinism ----------------------------------------------------------


def _toy_slim():
    picks = {}
    for arm in ("A_pics_joint_relabel", "C_fact_short_only"):
        per = {}
        for i in range(3):
            row = {"family": "FACT_SHORT" if i else "DESPIKE",
                   "rung": "fact_short", "params": {"max_gap": 3},
                   "true_repair_gain": 0.01 * (i + 1), "true_loss": 0.0}
            per[f"uid{i}"] = (row, 0, "t", None)
        per["uid3"] = None
        picks[arm] = per
    return p0.slim_decisions(picks)


def test_two_process_digest_determinism():
    snippet = (
        "import sys, json\n"
        "sys.path.insert(0, %r)\n"
        "sys.path.insert(0, %r)\n"
        "from v39_phase0_replay import digest_blob, slim_decisions\n"
        "picks = {}\n"
        "for arm in ('A_pics_joint_relabel', 'C_fact_short_only'):\n"
        "    per = {}\n"
        "    for i in range(3):\n"
        "        row = {'family': 'FACT_SHORT' if i else 'DESPIKE',\n"
        "               'rung': 'fact_short', 'params': {'max_gap': 3},\n"
        "               'true_repair_gain': 0.01 * (i + 1), 'true_loss': 0.0}\n"
        "        per['uid%%d' %% i] = (row, 0, 't', None)\n"
        "    per['uid3'] = None\n"
        "    picks[arm] = per\n"
        "slim = slim_decisions(picks)\n"
        "print(json.dumps(digest_blob(slim)))\n"
        % (str(ROOT / "src"), str(ROOT / "experiments")))
    outs = []
    for _ in range(2):
        proc = subprocess.run([sys.executable, "-c", snippet],
                              capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr
        outs.append(json.loads(proc.stdout.strip()))
    assert outs[0] == outs[1], "two independent processes must agree"
    assert p0.digest_blob(_toy_slim()) == outs[0]
