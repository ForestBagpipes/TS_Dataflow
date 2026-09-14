"""v3.4 Phase 1: conditional-risk feasibility replay (pre-registered in
docs/v3_4_scrc_pics_preregistration.md §5).

Question: can threshold-only replay of the frozen PICS_joint_relabel scores
reach the conditional-risk gates (CHR <= 0.10 with a one-sided 95%
Clopper-Pearson upper bound also <= 0.10) without giving up the incumbent's
beneficial coverage (bcov >= 0.273, pme <= 0.0091)? No TSFM is re-run; the
PICS dual heads are deterministically rebuilt from the frozen candidate table
(results/v33_training_data.jsonl), the frozen HGB hyperparameters and the
frozen leave-one-real-dataset-out split, reusing PICS / _PICSArm / _split /
_episode_metrics verbatim.

Integrity self-check (runs first, aborts on failure): the rebuilt scores,
replayed through the original PICS threshold rule (PICS.decide code path via
_decisions), must reproduce results/v33_arms_compare.json's PICS_joint_relabel
arm metrics to 1e-9. The reference values are hardcoded below from the local
frozen copy of v33_arms_compare.json so the check is independent of whatever
is currently writing on the server.

Four selectors, all thresholds chosen on the calibration fold only:
  pics_threshold           PICS as-is (corpus-risk calibration + spread gate)
  corpus_risk              v3.3 logic as a pure threshold rule (no spread gate)
  direct_conditional       one global (tau_b, tau_h) pair, admissible iff the
                           calibration replay has CHR <= 0.10 AND its one-sided
                           95% Clopper-Pearson upper bound <= 0.10; maximise
                           calibration beneficial coverage
  per_family_conditional   greedy per-family thresholds under the same global
                           conditional-risk gate

Held-out folds are only ever evaluated, never used for threshold selection.
The oracle (test-side) frontier is included strictly as a post-hoc
feasibility/diagnostic object, labelled as such.
"""

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from introact_ts.contextual_shield import (  # noqa: E402
    EPISODE_FAMILY_ORDER, EPISODE_GRID, ShieldConfig,
)
from introact_ts.pics import PICS_JOINT_FEATURES  # noqa: E402
from v32_compare_arms import (  # noqa: E402
    _PICSArm, _feats, _load_rows, _paired_boot, _split, PROTECTED_STRATA,
)
from v33_compare_arms import _decisions, _episode_metrics  # noqa: E402

#: Refined bounded grid for the conditional-risk selectors (0.01 step).
REFINED_GRID = tuple(float(x) for x in np.round(np.arange(0.01, 1.0, 0.01), 2))

CHR_GATE = 0.10
CP_LEVEL = 0.95          # one-sided Clopper-Pearson level
BCOV_TARGET = 0.273      # Phase-1 pre-registered bar (>= incumbent bcov 0.2727)
PME_TARGET = 0.0091
BCOV_INSUFFICIENT = 0.20
N_BOOT = 10000
BOOT_SEED = 20260901
TOL = 1e-9

#: Reference: PICS_joint_relabel arm of results/v33_arms_compare.json
#: (local frozen copy, sha256 2164596135b83951a6aa1a08879d63b29f2c64ad7d613c16ac5de9afe4b44fa3).
REFERENCE_ARM = {
    "n_windows": 771,
    "committed": 151,
    "commit_rate": 0.19584954604409857,
    "damage": 0.040207522697795074,
    "conditional_harm_rate": 0.2052980132450331,
    "conditional_mean_loss": 0.2052980132450331,
    "beneficial_commits": 120,
    "protected_mis_edit_rate": 0.00906344410876133,
    "beneficial_coverage": 0.2727272727272727,
    "mean_repair_gain_contaminated": 0.09189960143728719,
}
REFERENCE_FOLDS = {  # (committed, CHR, bcov, pme) per held-out dataset
    "Crypto": (4, 0.0, 0.2, 0.0),
    "ETTh1": (5, 0.2, 0.05555555555555555, 0.0),
    "ETTh2": (13, 0.46153846153846156, 0.1111111111111111, 0.05660377358490566),
    "ETTm1": (33, 0.2727272727272727, 0.3333333333333333, 0.0),
    "Oil Price": (7, 0.2857142857142857, 0.15625, 0.0),
    "US Term Structure": (89, 0.14606741573033707, 0.4198895027624309, 0.0),
}

SEL_NAMES = ("pics_threshold", "corpus_risk", "direct_conditional",
             "per_family_conditional",
             "direct_conditional_cpUB205", "per_family_conditional_cpUB205")

#: Strict reading of the Phase-1 gate: calibration CHR AND its one-sided 95%
#: Clopper-Pearson upper bound both <= 0.10. Lenient sensitivity reading (the
#: v3.4 §8 hard gate): CHR <= 0.10 and upper bound < 0.205.
CP_GATE_STRICT = 0.10
CP_GATE_LENIENT = 0.205


# -- score table ---------------------------------------------------------------

class _Table:
    """Window-grouped candidate scores for fast first-commit replay."""

    def __init__(self, windows, fold_key):
        # windows: list of candidate dicts (proposer order) with row+scores.
        self.windows = windows
        self.fold_key = fold_key
        flat = [c for w in windows for c in w]
        self.n = len(flat)
        self.n_windows = len(windows)
        self.cand_bs = np.array([c["score_bs"] for c in flat])
        self.cand_harm = np.array([c["score_harm"] for c in flat])
        self.cand_family = np.array([c["row"]["family"] for c in flat])
        self.cand_loss = np.array([c["row"]["true_loss"] for c in flat])
        self.cand_gain = np.array([c["row"]["true_repair_gain"] for c in flat])
        self.cand_ben = np.array([c["row"]["beneficial"] for c in flat], float)
        self.cand_bsa = np.array([c["row"]["beneficial_and_safe"] for c in flat],
                                 float)
        self.cand_ds = np.array([c["row"]["dataset"] for c in flat])
        sizes = np.array([len(w) for w in windows])
        self.starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
        self.ends = np.cumsum(sizes)
        self.win_uid = [w[0]["row"]["sample_uid"] for w in windows]
        self.win_stratum = np.array([w[0]["row"]["stratum"] for w in windows])
        self.win_prot = np.array([s in PROTECTED_STRATA
                                  for s in self.win_stratum])
        self.win_cont = self.win_stratum == "contaminated"

    def replay(self, thresholds, spread_gate=None):
        """First-commit replay. ``thresholds``: {family: (t_bs, t_h)}.
        ``spread_gate``: optional (spread array, cap) applied to every
        candidate. Returns one candidate index per window, -1 for KEEP."""
        mask = np.zeros(self.n, bool)
        for fam, (t_bs, t_h) in thresholds.items():
            mask |= ((self.cand_family == fam)
                     & (self.cand_bs >= t_bs) & (self.cand_harm <= t_h))
        if spread_gate is not None:
            spreads, cap = spread_gate
            mask &= spreads <= cap
        first = np.minimum.reduceat(
            np.where(mask, np.arange(self.n), self.n), self.starts)
        return np.where(first < self.ends, first, -1)


def _score_rows(pics, rows, names):
    out = []
    for r in rows:
        bs_h, harm_h = pics.heads.get(r["family"], pics.global_heads)
        f = [_feats(r, names)]
        out.append({
            "row": r,
            "score_bs": float(bs_h.pessimistic(f)[0]),
            "score_harm": float(harm_h.pessimistic(f)[0]),
            "spread": float(harm_h.spread(f)[0]),
        })
    return out


def _windows_of(scored):
    by_uid = defaultdict(list)
    for e in scored:
        by_uid[e["row"]["sample_uid"]].append(e)
    return list(by_uid.values())


# -- metrics -------------------------------------------------------------------

@lru_cache(maxsize=None)
def _cp_upper_cached(k, n, level=CP_LEVEL):
    from scipy.stats import beta
    return float(beta.ppf(level, k + 1, n - k))


def _cp_upper(k, n, level=CP_LEVEL):
    """One-sided Clopper-Pearson upper bound for k successes of n."""
    if n <= 0:
        return None
    return _cp_upper_cached(k, n, level)


def _eb_upper(x, delta=0.05):
    """One-sided empirical-Bernstein upper bound (Maurer & Pontil) at 1-delta,
    for values in [0, 1]."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 2:
        return None
    s2 = float(np.var(x, ddof=1))
    t = np.log(2.0 / delta)
    return float(x.mean() + np.sqrt(2.0 * s2 * t / n) + 7.0 * t / (3.0 * (n - 1)))


def _cml_boot_upper(cond_losses, n_boot=N_BOOT, seed=BOOT_SEED):
    """Bootstrap 95th percentile of the conditional mean loss, windows
    resampled; resamples with zero commits are skipped."""
    x = np.asarray(cond_losses, float)
    n = len(x)
    if n == 0:
        return None
    rng = np.random.RandomState(seed)
    idx = rng.randint(0, n, size=(n_boot, n))
    return float(np.percentile(x[idx].mean(axis=1), 95))


def _stats_from_picks(tab, picks, light=False):
    """Working-point metrics; definitions match v33_compare_arms
    ._episode_metrics (verified against it for every reported point).
    ``light=True`` skips the bootstrap/EB bounds and the per-source counters
    (grid-search inner loop)."""
    picks = np.asarray(picks)
    comm = picks >= 0
    pc = np.where(comm, picks, 0)
    loss_w = np.where(comm, tab.cand_loss[pc], 0.0)
    harm_w = comm & (tab.cand_loss[pc] > 0.03)
    ben_w = comm & (tab.cand_ben[pc] > 0.5)
    bsa_w = comm & (tab.cand_bsa[pc] > 0.5)
    gain_w = np.where(comm, tab.cand_gain[pc], 0.0)
    n = max(tab.n_windows, 1)
    n_comm = int(comm.sum())
    n_harm = int(harm_w.sum())
    cond_losses = tab.cand_loss[pc[comm]]
    cont_n = int(tab.win_cont.sum())
    prot_n = int(tab.win_prot.sum())
    per_ds = defaultdict(lambda: [0, 0])
    commit_ds, commit_fam = Counter(), Counter()
    if not light:
        for i in range(tab.n_windows):
            per_ds[tab.cand_ds[tab.starts[i]]][1] += 1
            if comm[i]:
                r = tab.windows[i][picks[i] - tab.starts[i]]["row"]
                commit_ds[r["dataset"]] += 1
                commit_fam[r["family"]] += 1
                if bsa_w[i]:
                    per_ds[r["dataset"]][0] += 1
    total_bs = sum(v[0] for v in per_ds.values())
    out = {
        "n_windows": tab.n_windows,
        "committed": n_comm,
        "commit_rate": n_comm / n,
        "harm_count": n_harm,
        "conditional_harm_rate": (n_harm / n_comm) if n_comm else None,
        "chr_cp_upper_95": _cp_upper(n_harm, n_comm),
        "conditional_mean_loss": (float(cond_losses.mean())
                                  if n_comm else None),
        "cml_boot_upper_95": None if light else _cml_boot_upper(cond_losses),
        "cml_empirical_bernstein_upper_95": None if light
            else _eb_upper(cond_losses),
        "damage": float(loss_w.mean()),
        "protected_mis_edit_rate": float((tab.win_prot & comm).sum()
                                         / max(prot_n, 1)),
        "coverage": float((tab.win_cont & comm).sum() / max(cont_n, 1)),
        "beneficial_coverage": float((tab.win_cont & ben_w).sum()
                                     / max(cont_n, 1)),
        "beneficial_commits": int(bsa_w.sum()),
        "mean_repair_gain_contaminated": (float(gain_w[tab.win_cont].mean())
                                          if cont_n else 0.0),
        "max_dataset_bs_share": (max((v[0] / total_bs for v in per_ds.values()),
                                     default=0.0) if total_bs else 0.0),
        "commit_by_source": dict(commit_ds),
        "commit_by_family": dict(commit_fam),
    }
    if not light:
        out.update({
            "_loss": loss_w,
            "_prot_edit": (tab.win_prot & comm).astype(float),
            "_cont_improved": (tab.win_cont & ben_w).astype(float),
            "_committed": comm.astype(float),
            "_harmful_commit": harm_w.astype(float),
            "_cond_losses": cond_losses,
        })
    return out


def strip(m):
    return {k: v for k, v in m.items() if not k.startswith("_")}


# -- selectors -------------------------------------------------------------------

def _cal_admissible(tab, picks, gate=CHR_GATE, cp_gate=CP_GATE_STRICT):
    comm = picks >= 0
    n_comm = int(comm.sum())
    if n_comm == 0:
        return None
    pc = picks[comm]
    n_harm = int((tab.cand_loss[pc] > 0.03).sum())
    chr_ = n_harm / n_comm
    if chr_ > gate:
        return None
    cp = _cp_upper(n_harm, n_comm)
    if cp is None or cp > cp_gate:
        return None
    cont = tab.win_cont
    bcov = float((cont & comm & (tab.cand_ben[np.where(comm, picks, 0)] > 0.5)
                  ).sum() / max(int(cont.sum()), 1))
    return {"committed": n_comm, "harm": n_harm, "chr": chr_,
            "chr_cp_upper": cp, "bcov": bcov}


def _select_direct(tab, grid, gate=CHR_GATE, cp_gate=CP_GATE_STRICT):
    """One global (t_bs, t_h) pair for all eligible families, chosen on the
    calibration replay: admissible under the conditional-risk gate, then
    maximise calibration bcov; ties toward lower CHR, lower harm cap, higher
    benefit threshold (the conservative corner)."""
    best = None
    for t_bs in grid:
        for t_h in grid:
            thr = {f: (t_bs, t_h) for f in EPISODE_FAMILY_ORDER}
            st = _cal_admissible(tab, tab.replay(thr), gate, cp_gate)
            if st is None:
                continue
            key = (st["bcov"], -st["chr"], -t_h, t_bs)
            if best is None or key > best[0]:
                best = (key, (t_bs, t_h), st)
    if best is None:
        return None, {"n_admissible": 0}
    return {f: best[1] for f in EPISODE_FAMILY_ORDER}, {
        "pair": list(best[1]), "calibration": best[2]}


def _select_per_family(tab, grid, gate=CHR_GATE, cp_gate=CP_GATE_STRICT):
    """Greedy per-family thresholds under the same global conditional-risk
    gate, mirroring select_episode_thresholds' walk: while family F is
    calibrated, earlier families apply their thresholds and later families
    stay closed."""
    thresholds = {}
    trace = []
    for fam in EPISODE_FAMILY_ORDER:
        best = None
        for t_bs in grid:
            for t_h in grid:
                thr = dict(thresholds)
                thr[fam] = (t_bs, t_h)
                st = _cal_admissible(tab, tab.replay(thr), gate, cp_gate)
                if st is None:
                    continue
                key = (st["bcov"], -st["chr"], -t_h, t_bs)
                if best is None or key > best[0]:
                    best = (key, (t_bs, t_h), st)
        if best is not None:
            thresholds[fam] = best[1]
            trace.append({"family": fam, "pair": list(best[1]),
                          "calibration": best[2]})
        else:
            trace.append({"family": fam, "pair": None})
    return thresholds, trace


def _boundary_flags(thresholds, grid):
    """Harm cap on the searched grid boundary = calibration failure
    (pre-registered, prereg §2.2)."""
    lo, hi = grid[0], grid[-1]
    flags = {}
    for fam, (t_bs, t_h) in thresholds.items():
        flags[fam] = {
            "harm_cap": t_h,
            "on_lower_boundary": bool(t_h <= lo + 1e-12),
            "on_upper_boundary": bool(t_h >= hi - 1e-12),
        }
    failure = any(f["on_lower_boundary"] or f["on_upper_boundary"]
                  for f in flags.values())
    return flags, failure


# -- bootstrap --------------------------------------------------------------------

def _ratio_diff_boot(h_a, c_a, h_b, c_b, n_boot=N_BOOT, seed=BOOT_SEED):
    h_a, c_a = np.asarray(h_a, float), np.asarray(c_a, float)
    h_b, c_b = np.asarray(h_b, float), np.asarray(c_b, float)
    rng = np.random.RandomState(seed)
    idx = rng.randint(0, len(h_a), size=(n_boot, len(h_a)))
    ca, cb = c_a[idx].sum(axis=1), c_b[idx].sum(axis=1)
    ok = (ca > 0) & (cb > 0)
    if not ok.any():
        return {"diff": None, "ci": [None, None], "n_valid": 0}
    d = h_a[idx][ok].sum(axis=1) / ca[ok] - h_b[idx][ok].sum(axis=1) / cb[ok]
    return {"diff": float(h_a.sum() / max(c_a.sum(), 1)
                          - h_b.sum() / max(c_b.sum(), 1)),
            "ci": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))],
            "n_valid": int(ok.sum())}


def _cond_mean_diff_boot(a_loss, a_comm, b_loss, b_comm,
                         n_boot=N_BOOT, seed=BOOT_SEED):
    a = np.where(np.asarray(a_comm, bool), np.asarray(a_loss, float), -1.0)
    b = np.where(np.asarray(b_comm, bool), np.asarray(b_loss, float), -1.0)
    rng = np.random.RandomState(seed)
    idx = rng.randint(0, len(a), size=(n_boot, len(a)))
    diffs = []
    for bi in idx:
        xa, xb = a[bi], b[bi]
        xa, xb = xa[xa > -1], xb[xb > -1]
        if len(xa) and len(xb):
            diffs.append(xa.mean() - xb.mean())
    if not diffs:
        return {"diff_ci": [None, None], "n_valid": 0}
    d = np.asarray(diffs)
    return {"diff_ci": [float(np.percentile(d, 2.5)),
                        float(np.percentile(d, 97.5))],
            "n_valid": int(len(diffs))}


def _bootstrap_vs_pics(sel_stats, pics_stats):
    return {
        "bcov_sel_minus_pics": _paired_boot(sel_stats["_cont_improved"],
                                            pics_stats["_cont_improved"],
                                            N_BOOT, BOOT_SEED),
        "damage_sel_minus_pics": _paired_boot(sel_stats["_loss"],
                                              pics_stats["_loss"],
                                              N_BOOT, BOOT_SEED),
        "pme_sel_minus_pics": _paired_boot(sel_stats["_prot_edit"],
                                           pics_stats["_prot_edit"],
                                           N_BOOT, BOOT_SEED),
        "commit_sel_minus_pics": _paired_boot(sel_stats["_committed"],
                                              pics_stats["_committed"],
                                              N_BOOT, BOOT_SEED),
        "chr_ratio_sel_minus_pics": _ratio_diff_boot(
            sel_stats["_harmful_commit"], sel_stats["_committed"],
            pics_stats["_harmful_commit"], pics_stats["_committed"]),
        "cml_sel_minus_pics": _cond_mean_diff_boot(
            sel_stats["_loss"], sel_stats["_committed"],
            pics_stats["_loss"], pics_stats["_committed"]),
    }


# -- self-check -------------------------------------------------------------------

def _close(a, b, tol=TOL):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def _selfcheck(arm_stats, fold_stats):
    diffs = {}
    ok = True
    for k, ref in REFERENCE_ARM.items():
        got = arm_stats.get(k)
        match = _close(got, ref) if isinstance(ref, float) else got == ref
        diffs[k] = {"reference": ref, "got": got, "match": bool(match)}
        ok &= bool(match)
    for ds, (c, chr_, bcov, pme) in REFERENCE_FOLDS.items():
        f = fold_stats.get(ds, {})
        fm = (f.get("committed") == c
              and _close(f.get("conditional_harm_rate"), chr_)
              and _close(f.get("beneficial_coverage"), bcov)
              and _close(f.get("protected_mis_edit_rate"), pme))
        diffs[f"fold:{ds}"] = {
            "reference": {"committed": c, "conditional_harm_rate": chr_,
                          "beneficial_coverage": bcov,
                          "protected_mis_edit_rate": pme},
            "got": {k: f.get(k) for k in (
                "committed", "conditional_harm_rate", "beneficial_coverage",
                "protected_mis_edit_rate")},
            "match": bool(fm)}
        ok &= bool(fm)
    return ok, diffs


# -- main ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "results" / "v33_training_data.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "results" / "v34_conditional_risk_frontier.json"))
    args = ap.parse_args()
    t0 = time.perf_counter()

    rows = _load_rows(args.data)
    real = [r for r in rows if not r["dataset"].startswith("ood:")]
    datasets = sorted({r["dataset"] for r in real})
    print(f"{len(rows)} candidates ({len(real)} real), {len(datasets)} datasets",
          flush=True)

    # -- per-fold fit, self-check replay, calibration selection ------------------
    fold_info = {}
    fold_test_tables = {}
    fold_sel = {s: {} for s in SEL_NAMES}
    selfcheck_fold_stats = {}
    pics_committed_all = {}
    for test_ds in datasets:
        tf = time.perf_counter()
        train, cal, test = _split(real, test_ds)
        arm = _PICSArm(PICS_JOINT_FEATURES)
        arm.fit(train, cal)
        pics = arm.pics

        # 1) original code path replay (self-check + pics_threshold selector)
        committed = _decisions(test, arm)
        pics_committed_all.update(committed)
        m = _episode_metrics(test, committed)
        selfcheck_fold_stats[test_ds] = {
            k: v for k, v in m.items() if not k.startswith("_")}

        # 2) scored tables for threshold-only selectors
        test_scored = _score_rows(pics, test, PICS_JOINT_FEATURES)
        tab_test = _Table(_windows_of(test_scored), test_ds)
        fold_test_tables[test_ds] = (tab_test, test_scored)
        cal_scored = _score_rows(pics, cal, PICS_JOINT_FEATURES)
        tab_cal = _Table(_windows_of(cal_scored), test_ds)
        fold_cal_tables[test_ds] = tab_cal

        # cross-check: vectorised replay with the spread gate must reproduce
        # the original code path's metric record exactly
        spreads = np.array([c["spread"] for c in test_scored])
        picks_chk = tab_test.replay(dict(pics.thresholds),
                                    spread_gate=(spreads, pics.spread_cap))
        comm_chk = {}
        for i, uid in enumerate(tab_test.win_uid):
            p = picks_chk[i]
            if p >= 0:
                r = tab_test.windows[i][p - tab_test.starts[i]]["row"]
                comm_chk[uid] = (r, 0, "vectorised", None)
            else:
                comm_chk[uid] = None
        m_chk = _episode_metrics(test, comm_chk)
        for k in ("committed", "conditional_harm_rate", "beneficial_coverage",
                  "protected_mis_edit_rate", "damage"):
            a, b = m[k], m_chk[k]
            same = (a == b) if not isinstance(a, float) else _close(a, b)
            if not same:
                print(f"FATAL: vectorised replay mismatch {test_ds} {k}: "
                      f"{a} vs {b}", flush=True)
                sys.exit(3)

        # selectors: corpus_risk reuses the fitted PICS thresholds as a pure
        # threshold rule; direct/per-family select on the calibration fold
        thr_corpus = {f: tuple(t) for f, t in pics.thresholds.items()}
        thr_direct, direct_info = _select_direct(tab_cal, REFINED_GRID)
        thr_pf, pf_trace = _select_per_family(tab_cal, REFINED_GRID)
        thr_direct_l, direct_info_l = _select_direct(
            tab_cal, REFINED_GRID, cp_gate=CP_GATE_LENIENT)
        thr_pf_l, pf_trace_l = _select_per_family(
            tab_cal, REFINED_GRID, cp_gate=CP_GATE_LENIENT)
        fold_sel["pics_threshold"][test_ds] = dict(pics.thresholds)
        fold_sel["corpus_risk"][test_ds] = thr_corpus
        fold_sel["direct_conditional"][test_ds] = thr_direct
        fold_sel["per_family_conditional"][test_ds] = thr_pf
        fold_sel["direct_conditional_cpUB205"][test_ds] = thr_direct_l
        fold_sel["per_family_conditional_cpUB205"][test_ds] = thr_pf_l
        d_flags, d_fail = _boundary_flags(
            thr_direct and {"__global__": thr_direct[EPISODE_FAMILY_ORDER[0]]}
            or {}, REFINED_GRID)
        p_flags, p_fail = _boundary_flags(thr_pf, REFINED_GRID)
        dl_flags, dl_fail = _boundary_flags(
            thr_direct_l and {"__global__": thr_direct_l[EPISODE_FAMILY_ORDER[0]]}
            or {}, REFINED_GRID)
        pl_flags, pl_fail = _boundary_flags(thr_pf_l, REFINED_GRID)
        fold_info[test_ds] = {
            "n_train_rows": len(train), "n_cal_rows": len(cal),
            "n_test_rows": len(test),
            "pics_thresholds": {f: list(t) for f, t in pics.thresholds.items()},
            "spread_cap": float(pics.spread_cap),
            "direct_selection": direct_info,
            "direct_boundary": {"flags": d_flags, "calibration_failure": d_fail},
            "per_family_trace": pf_trace,
            "per_family_boundary": {"flags": p_flags,
                                    "calibration_failure": p_fail},
            "direct_selection_cpUB205": direct_info_l,
            "direct_boundary_cpUB205": {"flags": dl_flags,
                                        "calibration_failure": dl_fail},
            "per_family_trace_cpUB205": pf_trace_l,
            "per_family_boundary_cpUB205": {"flags": pl_flags,
                                            "calibration_failure": pl_fail},
        }
        print(f"  fold {test_ds}: fit+select {time.perf_counter()-tf:.1f}s "
              f"pics={pics.thresholds} direct={direct_info.get('pair')} "
              f"pf={ {f: tuple(v) for f, v in thr_pf.items()} } "
              f"direct205={direct_info_l.get('pair')} "
              f"pf205={ {f: tuple(v) for f, v in thr_pf_l.items()} }",
              flush=True)

    # -- self-check against the frozen reference --------------------------------
    pics_metrics = _episode_metrics(real, pics_committed_all)
    ok, diffs = _selfcheck(
        {k: v for k, v in pics_metrics.items() if not k.startswith("_")},
        selfcheck_fold_stats)
    print(f"self-check vs v33_arms_compare.json PICS_joint_relabel: "
          f"{'PASS' if ok else 'FAIL'}", flush=True)

    base_out = {
        "status": "ok" if ok else "selfcheck_failed",
        "selfcheck": {"passed": bool(ok), "tolerance": TOL,
                      "reference": "results/v33_arms_compare.json "
                                   "PICS_joint_relabel (local frozen copy)",
                      "diffs": diffs},
        "config": {
            "chr_gate": CHR_GATE, "cp_level": CP_LEVEL,
            "cp_gate_strict": CP_GATE_STRICT,
            "cp_gate_lenient_sensitivity": CP_GATE_LENIENT,
            "refined_grid": [REFINED_GRID[0], REFINED_GRID[-1],
                             len(REFINED_GRID)],
            "episode_grid_v33": [EPISODE_GRID[0], EPISODE_GRID[-1],
                                 len(EPISODE_GRID)],
            "n_boot": N_BOOT, "boot_seed": BOOT_SEED,
            "bcov_target": BCOV_TARGET, "pme_target": PME_TARGET,
            "split": "leave-one-dataset-out", "split_seed": 20260901,
            "hgb": vars(ShieldConfig()),
            "note": "thresholds selected on the calibration fold only; "
                    "held-out folds are evaluation-only. Selectors 2-4 are "
                    "pure threshold rules on the rebuilt PICS scores (no "
                    "spread gate).",
        },
        "provenance": {
            "data": os.path.basename(args.data),
            "code_facts": {
                "threshold_selection": "PICS.fit -> select_episode_thresholds "
                    "(src/introact_ts/pics.py:184-186; "
                    "src/introact_ts/contextual_shield.py:166-220)",
                "admissibility": "episode_replay corrected corpus risk "
                    "(n*damage+1)/(n+1) <= alpha=0.03 "
                    "(contextual_shield.py:160-162,180-182)",
                "grid": "EPISODE_GRID 0.05..0.95 step 0.05 "
                    "(contextual_shield.py:133)",
                "tie_break": "max committed, then lower harm cap, then higher "
                    "benefit threshold (contextual_shield.py:193,214)",
                "decision_rule": "PICS.decide spread gate + dual thresholds "
                    "(src/introact_ts/pics.py:191-207); spread cap = cal "
                    "95th pct (pics.py:177)",
            },
        },
        "folds": fold_info,
    }
    if not ok:
        Path(args.out).write_text(json.dumps(base_out, indent=1, default=float),
                                  encoding="utf-8")
        print("self-check FAILED; wrote diagnostics and stopping.", flush=True)
        print(f"___V34_PHASE1_DONE___ status=selfcheck_failed out={args.out}")
        return

    # -- pooled working points -----------------------------------------------------
    # pooled test table: windows blocked by fold (datasets order), so fold
    # test tables are contiguous segments of the pooled flat arrays; scores
    # come from each window's own fold model. All selectors share this window
    # order, which is what makes the paired bootstrap valid.
    pooled_windows = [w for test_ds in datasets
                      for w in fold_test_tables[test_ds][0].windows]
    tab_pool = _Table(pooled_windows, None)

    # per-window arrays for the pics arm in pooled-table order (for pairing)
    pics_picks = np.full(tab_pool.n_windows, -1, dtype=int)
    for i, uid in enumerate(tab_pool.win_uid):
        got = pics_committed_all.get(uid)
        if got:
            row = got[0]
            for j, c in enumerate(tab_pool.windows[i]):
                if c["row"] is row:
                    pics_picks[i] = tab_pool.starts[i] + j
                    break
    pics_stats = _stats_from_picks(tab_pool, pics_picks)
    # the pooled vectorised stats must equal the original-code-path metrics
    for k in ("committed", "damage", "conditional_harm_rate",
              "beneficial_coverage", "protected_mis_edit_rate",
              "mean_repair_gain_contaminated"):
        assert _close(pics_stats[k], pics_metrics[k]), (k, pics_stats[k],
                                                        pics_metrics[k])

    selectors = {}
    for name in SEL_NAMES:
        if name == "pics_threshold":
            stats = pics_stats
        else:
            picks = np.full(tab_pool.n_windows, -1, dtype=int)
            off = 0
            for test_ds in datasets:
                tab = fold_test_tables[test_ds][0]
                thr = fold_sel[name][test_ds]
                if thr is None:
                    off += tab.n_windows
                    continue
                p = tab.replay(thr)
                picks[off:off + tab.n_windows] = np.where(
                    p >= 0, p + tab_pool.starts[off], -1)
                off += tab.n_windows
            stats = _stats_from_picks(tab_pool, picks)
        meets = (stats["conditional_harm_rate"] is not None
                 and stats["conditional_harm_rate"] <= CHR_GATE
                 and (stats["chr_cp_upper_95"] is not None
                      and stats["chr_cp_upper_95"] <= CHR_GATE)
                 and stats["beneficial_coverage"] >= BCOV_TARGET
                 and stats["protected_mis_edit_rate"] <= PME_TARGET)
        meets_lenient = (stats["conditional_harm_rate"] is not None
                         and stats["conditional_harm_rate"] <= CHR_GATE
                         and (stats["chr_cp_upper_95"] is not None
                              and stats["chr_cp_upper_95"] <= CP_GATE_LENIENT)
                         and stats["beneficial_coverage"] >= BCOV_TARGET
                         and stats["protected_mis_edit_rate"] <= PME_TARGET)
        selectors[name] = {
            "working_point": strip(stats),
            "meets_phase1_bars_on_test": bool(meets),
            "meets_phase1_bars_on_test_cpUB205": bool(meets_lenient),
            "paired_bootstrap_vs_pics": _bootstrap_vs_pics(stats, pics_stats),
        }
        print(f"  {name}: commit={stats['committed']} harm={stats['harm_count']} "
              f"CHR={stats['conditional_harm_rate']} "
              f"bcov={stats['beneficial_coverage']:.4f} "
              f"pme={stats['protected_mis_edit_rate']:.4f}", flush=True)

    # -- frontiers ------------------------------------------------------------------
    tf = time.perf_counter()
    # (a) honest frontier: per harm cap, t_bs chosen on calibration (direct
    # selector rule), evaluated pooled on held-out folds
    frontier_cal = []
    for t_h in REFINED_GRID:
        picks = np.full(tab_pool.n_windows, -1, dtype=int)
        any_sel = False
        # per-fold calibration selection at this harm cap
        off = 0
        for test_ds in datasets:
            tab_test = fold_test_tables[test_ds][0]
            tab_cal = fold_cal_tables[test_ds]
            best = None
            for t_bs in REFINED_GRID:
                thr = {f: (t_bs, t_h) for f in EPISODE_FAMILY_ORDER}
                st = _cal_admissible(tab_cal, tab_cal.replay(thr))
                if st is None:
                    continue
                key = (st["bcov"], -st["chr"], t_bs)
                if best is None or key > best[0]:
                    best = (key, t_bs)
            if best is not None:
                any_sel = True
                thr = {f: (best[1], t_h) for f in EPISODE_FAMILY_ORDER}
                p = tab_test.replay(thr)
                picks[off:off + tab_test.n_windows] = np.where(
                    p >= 0, p + tab_pool.starts[off], -1)
            off += tab_test.n_windows
        st = _stats_from_picks(tab_pool, picks, light=True)
        frontier_cal.append({
            "harm_cap": t_h, "any_fold_admissible": bool(any_sel),
            "committed": st["committed"], "harm_count": st["harm_count"],
            "conditional_harm_rate": st["conditional_harm_rate"],
            "chr_cp_upper_95": st["chr_cp_upper_95"],
            "conditional_mean_loss": st["conditional_mean_loss"],
            "beneficial_coverage": st["beneficial_coverage"],
            "protected_mis_edit_rate": st["protected_mis_edit_rate"],
            "damage": st["damage"],
            "mean_repair_gain_contaminated":
                st["mean_repair_gain_contaminated"],
        })
    print(f"  frontier_cal done {time.perf_counter()-tf:.1f}s", flush=True)

    # (b) oracle global frontier: full refined grid evaluated on pooled
    # held-out folds. POST-HOC feasibility analysis only; never used to pick
    # a working point.
    tf = time.perf_counter()
    og = {"label": "POST-HOC oracle on held-out folds (feasibility only)",
          "t_bs": list(REFINED_GRID), "t_h": list(REFINED_GRID),
          "chr": [], "chr_cp_upper": [], "bcov": [], "pme": [], "damage": [],
          "cml": [], "committed": [], "harm_count": []}
    for t_bs in REFINED_GRID:
        for t_h in REFINED_GRID:
            thr = {f: (t_bs, t_h) for f in EPISODE_FAMILY_ORDER}
            st = _stats_from_picks(tab_pool, tab_pool.replay(thr), light=True)
            og["chr"].append(st["conditional_harm_rate"])
            og["chr_cp_upper"].append(st["chr_cp_upper_95"])
            og["bcov"].append(st["beneficial_coverage"])
            og["pme"].append(st["protected_mis_edit_rate"])
            og["damage"].append(st["damage"])
            og["cml"].append(st["conditional_mean_loss"])
            og["committed"].append(st["committed"])
            og["harm_count"].append(st["harm_count"])
    print(f"  oracle global frontier done {time.perf_counter()-tf:.1f}s",
          flush=True)

    # (c) oracle per-family: coordinate ascent (2 passes) on pooled held-out
    # folds, maximising test bcov subject to test CHR <= gate. POST-HOC only.
    tf = time.perf_counter()
    def _test_admissible_bcov(thr):
        st = _stats_from_picks(tab_pool, tab_pool.replay(thr), light=True)
        chr_ = st["conditional_harm_rate"]
        if chr_ is None or chr_ > CHR_GATE:
            return None
        return st
    thr = {}
    trace = []
    for _pass in range(2):
        for fam in EPISODE_FAMILY_ORDER:
            best = None
            for t_bs in REFINED_GRID:
                for t_h in REFINED_GRID:
                    cand = dict(thr)
                    cand[fam] = (t_bs, t_h)
                    st = _test_admissible_bcov(cand)
                    if st is None:
                        continue
                    key = (st["beneficial_coverage"], -chr0(st), -t_h, t_bs)
                    if best is None or key > best[0]:
                        best = (key, (t_bs, t_h), st)
            if best is not None:
                thr[fam] = best[1]
                trace.append({"pass": _pass, "family": fam,
                              "pair": list(best[1]),
                              "bcov": best[2]["beneficial_coverage"],
                              "chr": best[2]["conditional_harm_rate"]})
    oracle_pf = _stats_from_picks(tab_pool, tab_pool.replay(thr)) if thr else None
    print(f"  oracle per-family done {time.perf_counter()-tf:.1f}s", flush=True)

    # -- Phase-1 determination ---------------------------------------------------
    chr_arr = np.array([x if x is not None else np.nan for x in og["chr"]])
    cp_arr = np.array([x if x is not None else np.nan
                       for x in og["chr_cp_upper"]])
    bcov_arr = np.array(og["bcov"])
    pme_arr = np.array(og["pme"])
    under = chr_arr <= CHR_GATE
    under_cp = under & (cp_arr <= CHR_GATE)
    max_bcov_under = float(np.nanmax(bcov_arr[under])) if under.any() else None
    max_bcov_under_cp = (float(np.nanmax(bcov_arr[under_cp]))
                         if under_cp.any() else None)
    qual = under & (bcov_arr >= BCOV_TARGET) & (pme_arr <= PME_TARGET)
    best_qual = None
    if qual.any():
        qi = int(np.nanargmax(np.where(qual, bcov_arr, -np.inf)))
        n_g = len(REFINED_GRID)
        best_qual = {
            "t_bs": REFINED_GRID[qi // n_g], "t_h": REFINED_GRID[qi % n_g],
            "chr": float(chr_arr[qi]), "chr_cp_upper": float(cp_arr[qi]),
            "bcov": float(bcov_arr[qi]), "pme": float(pme_arr[qi]),
            "damage": float(og["damage"][qi]), "cml": og["cml"][qi],
            "committed": og["committed"][qi],
            "harm_count": og["harm_count"][qi],
        }
    insufficient = (max_bcov_under is not None
                    and max_bcov_under < BCOV_INSUFFICIENT)
    cal_failures = [
        {"fold": ds, "selector": sel}
        for ds, info in fold_info.items()
        for sel, key in (("direct_conditional", "direct_boundary"),
                         ("per_family_conditional", "per_family_boundary"),
                         ("direct_conditional_cpUB205",
                          "direct_boundary_cpUB205"),
                         ("per_family_conditional_cpUB205",
                          "per_family_boundary_cpUB205"))
        if info[key]["calibration_failure"]]
    determination = {
        "crc_only_candidate_exists_oracle_global": bool(qual.any()),
        "best_qualifying_oracle_point": best_qual,
        "oracle_per_family": {
            "thresholds": {f: list(t) for f, t in thr.items()},
            "trace": trace,
            "working_point": strip(oracle_pf) if oracle_pf else None,
            "boundary": _boundary_flags(thr, REFINED_GRID)[0] if thr else {},
            "meets_phase1_bars": bool(
                oracle_pf is not None
                and oracle_pf["conditional_harm_rate"] is not None
                and oracle_pf["conditional_harm_rate"] <= CHR_GATE
                and oracle_pf["beneficial_coverage"] >= BCOV_TARGET
                and oracle_pf["protected_mis_edit_rate"] <= PME_TARGET),
        },
        "max_bcov_under_chr_gate_oracle": max_bcov_under,
        "max_bcov_under_chr_gate_cp_oracle": max_bcov_under_cp,
        "score_ranking_insufficient": bool(insufficient),
        "calibration_failures_harm_cap_on_grid_boundary": cal_failures,
        "honest_cal_selected_meet_bars": {
            name: {"strict_cpUB010": selectors[name]["meets_phase1_bars_on_test"],
                   "lenient_cpUB205":
                       selectors[name]["meets_phase1_bars_on_test_cpUB205"]}
            for name in SEL_NAMES if name not in ("pics_threshold",
                                                  "corpus_risk")},
        "criteria": {
            "chr<=": CHR_GATE, "bcov>=": BCOV_TARGET, "pme<=": PME_TARGET,
            "insufficient_rule": ("record 'score ranking insufficient' iff "
                                  "every threshold with CHR<=0.10 has "
                                  "bcov<0.20 (oracle frontier)"),
        },
    }

    out = dict(base_out)
    out["selectors"] = selectors
    out["frontiers"] = {
        "cal_selected_direct_by_harm_cap": frontier_cal,
        "oracle_global_posthoc": og,
    }
    out["determination"] = determination
    import resource
    out["runtime"] = {
        "wall_seconds": time.perf_counter() - t0,
        "cpu_count": os.cpu_count(),
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
        "max_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    }
    Path(args.out).write_text(json.dumps(out, indent=1, default=float),
                              encoding="utf-8")
    print(json.dumps({k: determination[k] for k in (
        "crc_only_candidate_exists_oracle_global", "score_ranking_insufficient",
        "max_bcov_under_chr_gate_oracle", "honest_cal_selected_meet_bars")},
        indent=1), flush=True)
    print(f"___V34_PHASE1_DONE___ status=ok out={args.out} "
          f"wall={time.perf_counter()-t0:.1f}s", flush=True)


def chr0(st):
    return st["conditional_harm_rate"] or 0.0


#: calibration-fold score tables, populated per fold in main()
fold_cal_tables = {}


if __name__ == "__main__":
    main()
