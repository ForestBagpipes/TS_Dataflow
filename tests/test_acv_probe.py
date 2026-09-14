"""Tests for the v3.5 Phase 1 ACV probe (experiments/v35_acv_probe.py).

Pre-registered integrity requirements (§5): KEEP/APPLY share anchors,
contexts, scale and checkpoint; the support mask never leaks candidate
values into the reconstruction; tampering with an anchor target must fail;
multiprocess and repeated execution agree bit for bit; no evaluation fields
enter the probe (source scan); operator output hashes reproduce; every
record carries model/checkpoint/config/input/output hashes.

All synthetic, on the offline surrogate pool: no corpus, no GPU, no
evaluation fields.
"""

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

import v35_acv_probe as probe  # noqa: E402
import v35_acv_common as acv  # noqa: E402
from introact_ts.actions import apply_action  # noqa: E402
from introact_ts.backends import make_model_pool  # noqa: E402
from introact_ts.types import Action  # noqa: E402
from v33_labels import hash_array  # noqa: E402


def _series(T=256, seed=3):
    rng = np.random.RandomState(seed)
    t = np.arange(T, dtype=np.float64)
    return np.cumsum(rng.randn(T)) + 2.0 * np.sin(2 * np.pi * t / 24.0)


def _impute_window(T=256, seed=3):
    x = _series(T, seed)
    x[100:120] = np.nan
    return x


def _surrogates():
    return make_model_pool((0, 1, 2))


# -- KEEP/APPLY shared inputs ---------------------------------------------------


def test_keep_apply_share_anchor_context_and_scale():
    x = _impute_window()
    job = probe.build_candidate_jobs(
        "uid:share", x, "IMPUTE", {"method": "linear", "min_run": 8})
    assert job["preq_jobs"]
    for j in job["preq_jobs"]:
        # identical anchor target block and context length on both sides
        assert len(j["keep_ctx"]) == len(j["apply_ctx"]) == j["context_len"]
        assert j["context_len"] == j["start"] - 0  # retain_lo = 0 for IMPUTE
        assert np.isfinite(j["target"]).all()
        assert j["end"] - j["start"] == j["horizon"]
    # one fixed reference scale per candidate, used for both sides
    assert job["reference_scale"] > 0
    models = _surrogates()
    ev = probe.execute_probe([job], models)[0]
    assert ev["prequential"]["supported"] == 1
    for a in ev["prequential"]["anchors"]:
        assert set(a) >= {"err_keep", "err_apply", "gain",
                          "keep_ctx_hash", "apply_ctx_hash", "target_hash"}
        assert a["gain"] == a["err_keep"] - a["err_apply"]


def test_resegment_contexts_length_matched_inside_retained_span():
    x = _series(T=192, seed=5)
    x[:64] += 50.0
    params = {"penalty": 8.0, "min_size": 24, "min_keep_frac": 0.4}
    job = probe.build_candidate_jobs("uid:reseg", x, "RESEGMENT", params)
    rlo, rhi = job["retain_span"]
    for j in job["preq_jobs"]:
        assert rlo <= j["start"] and j["end"] <= rhi
        assert len(j["keep_ctx"]) == len(j["apply_ctx"])
        assert j["context_len"] == j["start"] - rlo


# -- support mask leak-freedom (constructive) -------------------------------------


def test_support_mask_never_sees_support_values():
    x = _impute_window()
    job = probe.build_candidate_jobs(
        "uid:leak", x, "IMPUTE", {"method": "linear", "min_run": 8})
    assert job["conformity"]["applicable"]
    base = job["x_keep"]
    spans = [tuple(s) for s in job["conformity"]["spans"]]
    model = _surrogates()[0]

    # Two decoy series that differ ONLY inside the masked support: one holds
    # the KEEP values, one holds absurd values. Reconstruction must be
    # bit-identical -> the span contents are never read.
    decoy = base.copy()
    for lo, hi in spans:
        decoy[lo:hi] = 1e6
    r1 = probe.flat_reconstruct(model, [(base, spans)])
    r2 = probe.flat_reconstruct(model, [(decoy, spans)])
    for key in r1:
        assert r1[key] is not None and r2[key] is not None
        assert np.array_equal(r1[key], r2[key])


def test_flat_reconstruct_matches_mixin_per_series():
    x = _impute_window()
    base = probe.materialize_for_probe(x)
    spans = [(100, 120), (150, 158)]
    model = _surrogates()[0]
    flat = probe.flat_reconstruct(model, [(base, spans)])
    ref = model.reconstruct_batch(base, spans)
    for j in range(len(spans)):
        assert np.array_equal(flat[(0, j)], np.asarray(ref[j]))


# -- anchor-target tamper detection -------------------------------------------------


def test_tampered_anchor_target_fails_verification():
    x = _impute_window()
    job = probe.build_candidate_jobs(
        "uid:tamper", x, "IMPUTE", {"method": "linear", "min_run": 8})
    probe.verify_job_targets(x, job)  # untampered passes
    job["preq_jobs"][0]["target"] = \
        np.asarray(job["preq_jobs"][0]["target"]) + 1.0
    try:
        probe.verify_job_targets(x, job)
    except AssertionError:
        return
    raise AssertionError("tampered anchor target was not detected")


def test_materialised_nan_target_fails_verification():
    x = _impute_window()
    job = probe.build_candidate_jobs(
        "uid:nantgt", x, "IMPUTE", {"method": "linear", "min_run": 8})
    t = np.asarray(job["preq_jobs"][0]["target"], dtype=np.float64).copy()
    t[0] = np.nan
    job["preq_jobs"][0]["target"] = t
    try:
        probe.verify_job_targets(x, job)
    except AssertionError:
        return
    raise AssertionError("non-finite anchor target was not detected")


# -- determinism: multiprocess and repeated execution --------------------------------


def _synthetic_tasks():
    tasks = []
    for k in range(6):
        x = _impute_window(T=192 + 16 * k, seed=10 + k)
        rows = [{"family": "IMPUTE", "rung": "default",
                 "params": {"method": "linear", "min_run": 8}},
                {"family": "IMPUTE", "rung": "aggressive",
                 "params": {"method": "seasonal", "min_run": 8}}]
        tasks.append((f"uid:det{k}", x, rows))
    return tasks


def _canon(jobs):
    """Hash-stable canonical form of one window's built jobs."""
    def norm(j):
        j = dict(j)
        j["x_keep"] = hash_array(j["x_keep"])
        for pj in j["preq_jobs"]:
            pj["keep_ctx"] = hash_array(pj["keep_ctx"])
            pj["apply_ctx"] = hash_array(pj["apply_ctx"])
            pj["target"] = hash_array(pj["target"])
        c = dict(j["conformity"])
        c["keep_vals"] = [hash_array(v) for v in c["keep_vals"]]
        c["cand_vals"] = [hash_array(v) for v in c["cand_vals"]]
        j["conformity"] = c
        return j
    return json.dumps([norm(j) for j in jobs], sort_keys=True, default=float)


def test_multiprocess_build_bit_identical():
    tasks = _synthetic_tasks()
    serial = [probe._build_uid(t) for t in tasks]
    with ProcessPoolExecutor(max_workers=2) as ex:
        parallel = list(ex.map(probe._build_uid, tasks))
    assert [_canon(j) for j in serial] == [_canon(j) for j in parallel]


def test_execute_probe_repeat_bit_identical():
    tasks = _synthetic_tasks()
    jobs = [j for t in tasks for j in probe._build_uid(t)]
    models = _surrogates()
    ev1 = probe.execute_probe(jobs, models)
    ev2 = probe.execute_probe(jobs, models)
    assert json.dumps(ev1, sort_keys=True, default=float) == \
        json.dumps(ev2, sort_keys=True, default=float)


# -- gain statistics ------------------------------------------------------------------


def test_gain_stats_missing_is_never_zero_filled():
    st = probe.gain_stats([])
    assert st["n"] == 0
    assert all(st[k] is None for k in
               ("mean", "median", "min", "std", "win_rate", "lcb"))
    st1 = probe.gain_stats([0.5])
    assert st1["lcb"] == 0.5 and st1["std"] is None
    st3 = probe.gain_stats([1.0, 2.0, 4.0])
    mean, std = 7.0 / 3.0, float(np.std([1.0, 2.0, 4.0], ddof=1))
    assert abs(st3["lcb"] - (mean - 1.645 * std / np.sqrt(3))) < 1e-12


# -- operator hash reproduction --------------------------------------------------------


def test_operator_output_hash_reproduces_table_convention():
    x = _impute_window()
    params = {"method": "linear", "min_run": 8}
    job = probe.build_candidate_jobs("uid:hash", x, "IMPUTE", params)
    out = apply_action(x, Action.IMPUTE, **params)
    assert job["output_hash"] == hash_array(out.series)
    # The KEEP materialisation hash convention is the v3.3 one.
    assert job["keep_input_hash"] == hash_array(
        probe.materialize_for_probe(x))


# -- record schema ----------------------------------------------------------------------


def test_record_carries_all_hashes():
    x = _impute_window()
    row = {"sample_uid": "uid:rec", "window_id": 0, "dataset": "synthetic",
           "stratum": "contaminated", "family": "IMPUTE", "rung": "default",
           "params": {"method": "linear", "min_run": 8},
           "missing_fraction": float(np.mean(~np.isfinite(x))),
           "corrupted_hash": hash_array(x),
           "output_hash": None, "keep_input_hash": None}
    job = probe.build_candidate_jobs(row["sample_uid"], x, "IMPUTE",
                                     row["params"])
    job["output_hash_verified"] = True
    job["keep_hash_verified"] = True
    ev = probe.execute_probe([job], _surrogates())[0]
    rec = probe.assemble_record(row, job, ev, {"surrogate": "local"},
                                probe.config_hash(), probe.code_hashes())
    for key in ("input_hash", "output_hash", "keep_input_hash",
                "config_hash", "code_hashes"):
        assert rec[key], key
    assert rec["model"]["judge"] == probe.JUDGE_SPEC
    assert "revisions" in rec["model"]
    assert set(rec["code_hashes"]) == set(probe.CODE_FILES)
    # The three fixed scores exist and respect the None discipline.
    assert {"score_a_prequential", "score_b_support",
            "score_c_joint"} <= set(rec)
    assert rec["score_a_prequential"] == rec["prequential"]["lcb"]
    assert rec["score_b_support"] == rec["support_conformity"]["lcb"]


def test_unsupported_candidate_scores_stay_none():
    x = _series(T=128, seed=7)
    # DENOISE rewrites the whole window -> support reaches the tail -> no
    # anchors and (typically) no conformity context. Whatever the support
    # flags, an unsupported block must carry None scores, never 0.
    job = probe.build_candidate_jobs("uid:none", x, "DENOISE",
                                     {"strength": 1.0})
    ev = probe.execute_probe([job], _surrogates())[0]
    scores = probe.fixed_scores(ev)
    if ev["prequential"]["supported"] == 0:
        assert scores["score_a_prequential"] is None
        assert ev["prequential"]["gain_mean"] is None
    if ev["support_conformity"]["supported"] == 0:
        assert scores["score_b_support"] is None
    if scores["score_a_prequential"] is None or \
            scores["score_b_support"] is None:
        assert scores["score_c_joint"] is None


# -- source scan: no evaluation fields enter the probe ---------------------------------


def test_probe_source_free_of_evaluation_fields():
    src = (ROOT / "experiments" / "v35_acv_probe.py").read_text(
        encoding="utf-8")
    # The one grandfathered occurrence: the pure hashing helper import.
    src = src.replace("from v33_labels import hash_array", "")
    forbidden = ["true_kind", "clean", "beneficial", "harmful", "true_loss",
                 "label", "before_nmse", "after_nmse", "clean_hash"]
    low = src.lower()
    for tok in forbidden:
        assert tok not in low, f"probe source references {tok!r}"
