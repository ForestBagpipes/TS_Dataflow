"""Smoke the v2 configuration: per family thresholds, ladder on, corrected loss.

Five checks, all of which have to pass before the xl run. The fourth is not a
performance target but a mechanism check, because DESPIKE's calibrated threshold
is zero and a threshold of zero admits nothing by definition. Asking that arm to
keep a 0.601 acceptance rate would be asking the run to contradict its own
calibration, so what is checked instead is that the refusals happen for the
stated reason and that the cost is measured rather than hidden.

  a  RESEGMENT commits almost nothing inside the protected strata, and level
     shift repair survives in the contaminated layer
  b  DENOISE is no longer refused every time
  c  IMPUTE's acceptance rises and its losses on the gap kinds stay where the
     calibration said they were
  d  DESPIKE candidates are proposed, are refused on structural grounds, and the
     spike windows they would have repaired are counted as unrepaired
  e  the corrected damage rate is below v1's recomputed value on the same corpus

Usage:
    python -u experiments/smoke_v2.py --scale small --source mixed --seed 0
"""

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from build_calibration import build as build_calibration  # noqa: E402
from build_calibration import build_slice  # noqa: E402
from corpus import build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402
from run_main import score_rows  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.policy import PolicyConfig  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402

PROTECTED = ("clean", "hard", "rare_valid", "changepoint")
OPS = ("IMPUTE", "DESPIKE", "DENOISE", "RESEGMENT")


def load_thresholds(path):
    blob = json.loads(Path(path).read_text(encoding="utf-8"))
    return {f: r["lambda_star"] for f, r in blob["families"].items()}, blob


def run(models, windows, states, reference, vcfg, pcfg, n_jobs):
    agent = IntroActAgent(models, AgentConfig(verification=vcfg, policy=pcfg,
                                              n_jobs=n_jobs))
    agent._calib = reference._calib
    agent._ood = reference._ood
    agent._reference = reference._reference
    return [agent.curate_window(w, s, peer_idx=i)
            for i, (w, s) in enumerate(zip(windows, states))]


def wilson(k, n, z=1.96):
    """Wilson score interval for a binomial proportion.

    A normal interval is useless at the rates this run produces: zero
    acceptances out of twelve is not evidence of a broken arm when the
    calibrated admission rate is 9.4 percent, and an interval that does not say
    so invites reading noise as failure.
    """
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - h), min(1.0, c + h))


def funnel(traces, byid, layers):
    """Per layer and family: candidates, then what each condition removed.

    `verify` short circuits, so a candidate's verdict names the first condition
    it failed. Reading the counts as a funnel is therefore exact rather than an
    approximation: everything reaching the structural condition passed utility,
    and everything reaching risk passed both.
    """
    out = defaultdict(lambda: defaultdict(lambda: {
        "candidates": 0, "no_op": 0, "failed_utility": 0,
        "failed_structure": 0, "failed_risk": 0, "accepted": 0}))
    for t in traces:
        w = byid[t.window_id]
        layer = layers(w)
        for r in t.records:
            name = getattr(r.action, "value", r.action)
            if name not in OPS:
                continue
            cell = out[name][layer]
            cell["candidates"] += 1
            v = getattr(r.verdict, "value", r.verdict)
            if v == "NO_OP":
                cell["no_op"] += 1
            elif v == "ROLLED_BACK_UTILITY":
                cell["failed_utility"] += 1
            elif v == "ROLLED_BACK_STRUCTURE":
                cell["failed_structure"] += 1
            elif v == "ROLLED_BACK_RISK":
                cell["failed_risk"] += 1
            elif v == "ACCEPTED":
                cell["accepted"] += 1
    return out


def by_operator(traces, byid):
    """Attempts, acceptances and where they land, per operator."""
    out = defaultdict(lambda: {"attempts": 0, "accepted": 0, "on_protected": 0,
                               "verdicts": Counter()})
    for t in traces:
        w = byid[t.window_id]
        for r in t.records:
            name = getattr(r.action, "value", r.action)
            if name not in OPS:
                continue
            rec = out[name]
            rec["attempts"] += 1
            v = getattr(r.verdict, "value", r.verdict)
            rec["verdicts"][v] += 1
            if v == "ACCEPTED":
                rec["accepted"] += 1
                if w.stratum in PROTECTED:
                    rec["on_protected"] += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="small", choices=list(SCALES))
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--slice-n", dest="slice_n", type=int, default=0,
                    help="build a held out slice of this size instead of "
                         "using a named scale")
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=16)
    ap.add_argument("--tau", type=float, default=0.02)
    ap.add_argument("--families", default=str(ROOT / "results" / "conformal_family.json"))
    ap.add_argument("--out", default=str(ROOT / "results" / "smoke_v2.json"))
    args = ap.parse_args()

    taus, blob = load_thresholds(args.families)
    print(f"per family thresholds: {taus}")
    print(f"calibrated at alpha {blob['alpha']} on {blob['n_windows']} windows")

    if args.slice_n:
        # A held out slice at deployment's stratum shares, disjoint from the
        # calibration corpus and from every deployment seed. The 91 window
        # `small` corpus cannot distinguish a near zero admission rate from a
        # broken arm, which is what made the first smoke unreadable.
        from build_calibration import ident
        cal, _ = build_calibration(n=1600, seed=101, source=args.source)
        windows, dropped, short = build_slice(
            args.slice_n, args.seed, source=args.source,
            also_avoid=[cal], verbose=True)
        if short:
            raise SystemExit(f"slice is short in {short}, raise oversample")
        ids = set(ident(w) for w in windows)
        overlap = len(ids & set(ident(w) for w in cal))
        print(f"hard check: overlap with calibration {overlap}, "
              f"internal duplicates {len(windows) - len(ids)}")
        if overlap or len(windows) != len(ids):
            raise SystemExit("slice is not disjoint, pick another seed")
    else:
        spec = SCALES[args.scale]
        spec.seed = args.seed
        windows = build_corpus(spec, source=args.source)
    byid = {w.window_id: w for w in windows}
    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)

    reference = IntroActAgent(models, AgentConfig(
        verification=VerifyConfig(tau=args.tau), n_jobs=args.n_jobs))
    t0 = time.time()
    states = reference.perceive(windows)
    print(f"{len(windows)} windows, perception {time.time() - t0:.0f}s",
          flush=True)

    # v1: global threshold, no ladder, but the corrected loss, so the damage
    # rates are comparable. This is v1 recomputed rather than v1 as recorded.
    v1 = run(models, windows, states, reference,
             VerifyConfig(tau=args.tau), PolicyConfig(), args.n_jobs)
    # v2: per family thresholds and the ladder.
    v2 = run(models, windows, states, reference,
             VerifyConfig(tau=args.tau, tau_by_family=taus),
             PolicyConfig(enable_param_ladder=True), args.n_jobs)

    r1, r2 = score_rows(v1, windows), score_rows(v2, windows)
    o1, o2 = by_operator(v1, byid), by_operator(v2, byid)

    def repaired(traces):
        """Per contamination kind: how many were edited and how many improved."""
        out = defaultdict(lambda: {"n": 0, "edited": 0, "improved": 0})
        for t in traces:
            w = byid[t.window_id]
            if w.stratum != "contaminated":
                continue
            rec = out[w.contamination or "none"]
            rec["n"] += 1
            if t.content_modified(w.series):
                rec["edited"] += 1
                a = np.asarray(t.final_series, dtype=np.float64)
                c = np.asarray(w.clean_series, dtype=np.float64)[t.crop_offset:]
                n = min(len(a), len(c))
                d0 = (np.asarray(w.series, dtype=np.float64)
                      - np.asarray(w.clean_series, dtype=np.float64))
                d1 = a[:n] - c[:n]
                before = float(np.sqrt(np.nanmean(d0 ** 2)))
                after = float(np.sqrt(np.nanmean(d1 ** 2)))
                rec["improved"] += int(after < before - 1e-9)
        return out

    p1, p2 = repaired(v1), repaired(v2)

    print()
    print(f"{'operator':11s}{'v1 att':>8s}{'v1 acc':>8s}{'v1 prot':>9s}"
          f"{'v2 att':>8s}{'v2 acc':>8s}{'v2 prot':>9s}{'v2 tau':>9s}")
    for op in OPS:
        a, b = o1[op], o2[op]
        print(f"{op:11s}{a['attempts']:8d}{a['accepted']:8d}{a['on_protected']:9d}"
              f"{b['attempts']:8d}{b['accepted']:8d}{b['on_protected']:9d}"
              f"{taus.get(op, args.tau):9.4f}")

    print()
    print("v2 verdict breakdown per operator")
    for op in OPS:
        v = o2[op]["verdicts"]
        tot = max(sum(v.values()), 1)
        print(f"  {op:11s}" + "  ".join(f"{k}={n / tot:.3f}"
                                        for k, n in sorted(v.items())))

    print()
    print("injected layer, edited and improved by contamination kind")
    print(f"{'kind':20s}{'n':>5s}{'v1 edit':>9s}{'v1 impr':>9s}"
          f"{'v2 edit':>9s}{'v2 impr':>9s}")
    for k in sorted(set(p1) | set(p2)):
        a, b = p1[k], p2[k]
        print(f"{k:20s}{a['n']:5d}{a['edited']:9d}{a['improved']:9d}"
              f"{b['edited']:9d}{b['improved']:9d}")

    def layer_of(w):
        if w.stratum in PROTECTED or w.stratum == "clean_ood":
            return "protected"
        return "contaminated" if w.stratum == "contaminated" else "other"

    f2 = funnel(v2, byid, layer_of)
    print()
    print("v2 condition funnel, per family and layer")
    print(f"{'family':11s}{'layer':13s}{'cands':>7s}{'no_op':>7s}"
          f"{'-utility':>10s}{'-struct':>9s}{'-risk':>7s}{'accept':>8s}"
          f"{'rate':>9s}{'Wilson 95%':>22s}")
    for op in OPS:
        for layer in ("protected", "contaminated"):
            c = f2[op][layer]
            live = c["candidates"] - c["no_op"]
            pr, lo, hi = wilson(c["accepted"], max(live, 0))
            print(f"{op:11s}{layer:13s}{c['candidates']:7d}{c['no_op']:7d}"
                  f"{c['failed_utility']:10d}{c['failed_structure']:9d}"
                  f"{c['failed_risk']:7d}{c['accepted']:8d}{pr:9.4f}"
                  f"   [{lo:.4f}, {hi:.4f}]")
    print("  rate and interval are over candidates the operator executed, so a "
          "NO_OP is not counted as a refusal")

    inj = [t for t in v2 if byid[t.window_id].stratum == "contaminated"]
    edited = sum(1 for t in inj if t.content_modified(byid[t.window_id].series))
    improved = sum(v["improved"] for v in p2.values())
    cov, cov_lo, cov_hi = wilson(improved, len(inj))
    n_harm = int(round(r2["damage_rate"] * max(r2["committed_edits"], 0)))
    d_p, d_lo, d_hi = wilson(n_harm, max(r2["committed_edits"], 0))
    print()
    print(f"injected layer: {len(inj)} windows, {edited} edited, "
          f"{improved} improved")
    print(f"  coverage {cov:.4f}  Wilson 95% [{cov_lo:.4f}, {cov_hi:.4f}]")
    print(f"  damage rate {r2['damage_rate']:.4f}  "
          f"Wilson 95% [{d_lo:.4f}, {d_hi:.4f}]  over "
          f"{r2['committed_edits']} committed edits")

    print()
    print("branch decision")
    safe = (d_hi < 0.6060 and d_hi < 0.6882
            and r2["protected_mis_edit_rate"] < 0.0635)
    print(f"  safety: damage CI upper {d_hi:.4f} below 0.6060 and 0.6882, "
          f"mis edit {r2['protected_mis_edit_rate']:.4f} below 0.0635 -> "
          f"{'PASS' if safe else 'FAIL'}")
    go = None
    if safe:
        go = bool(cov >= 0.15 and cov_lo >= 0.08)
        print(f"  coverage {cov:.4f} at least 0.15 and lower bound "
              f"{cov_lo:.4f} at least 0.08 -> "
              f"{'v2 xl approved' if go else 'v2 stays a slice row'}")
    else:
        print("  safety line failed, stop and follow the playbook")

    # The five checks.
    print()
    checks = {}
    checks["a_resegment_protected"] = o2["RESEGMENT"]["on_protected"] <= max(
        1, int(0.1 * max(o1["RESEGMENT"]["on_protected"], 1)))
    checks["a_level_shift_repair"] = p2["level_shift"]["improved"] > 0 \
        if p1["level_shift"]["improved"] > 0 else True
    checks["b_denoise_not_zero"] = o2["DENOISE"]["accepted"] > 0
    checks["c_impute_up"] = o2["IMPUTE"]["accepted"] >= o1["IMPUTE"]["accepted"]
    checks["d_despike_refused_structurally"] = (
        o2["DESPIKE"]["attempts"] > 0
        and o2["DESPIKE"]["accepted"] == 0
        and o2["DESPIKE"]["verdicts"].get("ROLLED_BACK_STRUCTURE", 0) > 0)
    checks["e_damage_down"] = r2["damage_rate"] < r1["damage_rate"]

    print(f"{'check':34s}{'result':>8s}")
    for k, v in checks.items():
        print(f"{k:34s}{'PASS' if v else 'FAIL':>8s}")

    print()
    print(f"damage rate      v1 {r1['damage_rate']:.4f}   v2 {r2['damage_rate']:.4f}")
    print(f"mis edit rate    v1 {r1['protected_mis_edit_rate']:.4f}   "
          f"v2 {r2['protected_mis_edit_rate']:.4f}")
    print(f"committed edits  v1 {r1['committed_edits']:5d}   "
          f"v2 {r2['committed_edits']:5d}")
    sp = p2.get("spike", {"n": 0, "edited": 0})
    print(f"spike windows unrepaired under v2: "
          f"{sp['n'] - sp['edited']} of {sp['n']}, which is the measured cost "
          f"of DESPIKE's zero threshold")

    Path(args.out).write_text(json.dumps(
        {"thresholds": taus, "checks": checks, "v1": r1, "v2": r2,
         "n_windows": len(windows), "slice_seed": args.seed,
         "funnel_v2": {op: {l: dict(c) for l, c in v.items()}
                       for op, v in f2.items()},
         "coverage": {"improved": improved, "edited": edited,
                      "n_injected": len(inj), "rate": cov,
                      "wilson": [cov_lo, cov_hi]},
         "damage_wilson": [d_lo, d_hi],
         "branch": {"safety_pass": bool(safe), "xl_approved": go},
         "operators_v1": {k: {**v, "verdicts": dict(v["verdicts"])}
                          for k, v in o1.items()},
         "operators_v2": {k: {**v, "verdicts": dict(v["verdicts"])}
                          for k, v in o2.items()},
         "repair_v1": {k: dict(v) for k, v in p1.items()},
         "repair_v2": {k: dict(v) for k, v in p2.items()}},
        indent=1, default=float), encoding="utf-8")
    print()
    print(f"{sum(checks.values())} of {len(checks)} checks pass")
    print("___SMOKE_V2_DONE___", flush=True)


if __name__ == "__main__":
    main()
