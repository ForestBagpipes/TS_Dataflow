"""B4, curation on the channel grouped corpus and multivariate downstream.

Two things happen here and they are separable. Curation runs per channel, which
is unchanged, on a corpus whose windows were drawn so that every channel at a
position is present. Evaluation then reassembles those channels into blocks and
scores a downstream forecaster on them.

The protocol was fixed in `docs/multivariate_downstream.md` before this ran:
the grouped corpus is the main table and the ungrouped one is a consistency
check. If they disagree materially both are reported and the difference is
diagnosed, and neither is chosen on the basis of being more favourable.

What this does not do is change the model. Channel independence unrolls each
channel separately and shares weights, which the univariate evaluation already
did. The difference is that training pairs now come from aligned positions and
error is reported over blocks.

Usage:
    python -u experiments/run_b4.py --device cuda --n 800
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import _nmse  # noqa: E402
from baselines import BASELINES  # noqa: E402
from corpus import CorpusSpec, build_corpus, build_corpus_grouped  # noqa: E402
from downstream import make_models, split_windows  # noqa: E402
from downstream_mv import block_report, evaluate_mv  # noqa: E402
from gating import gate, proposals_of  # noqa: E402
from regroup import regroup  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402

PROTECTED = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")


class _T:
    """Minimal trace, for arms that produce a series rather than a trace."""

    def __init__(self, wid, series, crop=0):
        self.window_id = wid
        self.final_series = series
        self.crop_offset = crop


def curate_all(windows, states, models, agent, cfg):
    """Every arm on the same corpus, returning traces keyed by method."""
    out = {}
    byid = {w.window_id: (w, s, i)
            for i, (w, s) in enumerate(zip(windows, states))}

    for name in ["no_action", "stat_only", "always_clean"]:
        t0 = time.time()
        out[name] = BASELINES[name](windows, states, models)
        print(f"  {name:22s} {time.time() - t0:.0f}s", flush=True)
        if name == "no_action":
            continue
        t0 = time.time()
        gated = []
        for t in out[name]:
            w, s, idx = byid[t.window_id]
            plan = proposals_of(t)
            if not plan:
                gated.append(_T(w.window_id, np.asarray(w.series, float)))
                continue
            series, crop, _, _ = gate(w, s, models, plan, agent, idx, cfg)
            gated.append(_T(w.window_id, series, crop))
        out[f"{name}_gated"] = gated
        print(f"  {name + '_gated':22s} {time.time() - t0:.0f}s", flush=True)

    t0 = time.time()
    out["introact_full"] = [agent.curate_window(w, s, peer_idx=i)
                            for i, (w, s) in enumerate(zip(windows, states))]
    print(f"  {'introact_full':22s} {time.time() - t0:.0f}s", flush=True)
    return out


def curation_metrics(traces, windows):
    byid = {w.window_id: w for w in windows}
    dmg, before, after = [], [], []
    n_mod = prot = 0
    for t in traces:
        w = byid[t.window_id]
        changed = not np.allclose(
            np.nan_to_num(t.final_series),
            np.nan_to_num(w.series[t.crop_offset:t.crop_offset + len(t.final_series)]),
            rtol=0, atol=1e-12) or t.crop_offset != 0
        if changed:
            n_mod += 1
            if w.stratum in PROTECTED:
                prot += 1
        rv = float(np.var(w.clean_series - np.median(w.clean_series)))
        a = _nmse(t.final_series, w.clean_series[t.crop_offset:], rv)
        b = _nmse(w.series, w.clean_series, rv)
        if w.stratum in PROTECTED:
            dmg.append(a)
        elif w.stratum == "contaminated":
            before.append(b)
            after.append(a)
    bm, am = float(np.mean(before)), float(np.mean(after))
    return {"mean_damage": float(np.mean(dmg)),
            "repair_reduction": (1.0 - am / bm) if bm > 1e-9 else 0.0,
            "n_modified": n_mod, "protected_edits": prot}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--tau", type=float, default=0.02)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--deep", action="store_true")
    args = ap.parse_args()

    n = args.n
    spec = CorpusSpec(
        n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
        n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
        n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125),
        seed=args.seed)

    models = make_pool(PRESETS["multi-family"]["curation"], device=args.device)
    cfg = VerifyConfig(tau=args.tau)
    payload = {"tau": args.tau, "seed": args.seed}

    # -- main table, grouped corpus -------------------------------------
    print("grouped corpus, the main table", flush=True)
    gw, gmap = build_corpus_grouped(spec)
    agent = IntroActAgent(models, AgentConfig(verification=cfg))
    t0 = time.time()
    gs = agent.perceive(gw)
    print(f"  perceive {time.time() - t0:.0f}s on {len(gw)}, "
          f"{len(gmap)} windows carry group metadata", flush=True)
    gtr = curate_all(gw, gs, models, agent, cfg)

    payload["grouped_curation"] = {k: curation_metrics(v, gw)
                                   for k, v in gtr.items()}
    print(f"\n{'method':22s}{'damage':>9s}{'repair':>9s}{'edits':>7s}{'prot':>7s}")
    for k, v in payload["grouped_curation"].items():
        print(f"{k:22s}{v['mean_damage']:9.4f}{v['repair_reduction']:+9.3f}"
              f"{v['n_modified']:7d}{v['protected_edits']:7d}")

    # -- reassemble and evaluate multivariate ---------------------------
    print("\nreassembly and multivariate downstream", flush=True)
    blocks_by_method, pristine, rep = {}, None, None
    for k, traces in gtr.items():
        b, p, r = regroup(traces, gw, gmap)
        blocks_by_method[k] = b
        if pristine is None:
            pristine, rep = p, r
    print(f"  {rep}", flush=True)
    payload["block_report"] = block_report(blocks_by_method["no_action"])
    print(f"  {payload['block_report']}", flush=True)

    nblk = len(blocks_by_method["no_action"])
    rng = np.random.RandomState(args.seed)
    order = rng.permutation(nblk)
    cut = int(0.7 * nblk)
    tr_idx, te_idx = order[:cut], order[cut:]

    payload["multivariate_downstream"] = {}
    for k, blocks in blocks_by_method.items():
        if len(blocks) != nblk:
            payload["multivariate_downstream"][k] = {
                "error": f"block count {len(blocks)} != {nblk}"}
            continue
        t0 = time.time()
        res = evaluate_mv(blocks, pristine, tr_idx, te_idx,
                          make_models(include_deep=args.deep, seed=args.seed))
        payload["multivariate_downstream"][k] = res
        print(f"  {k:22s} {time.time() - t0:.0f}s", flush=True)

    mv = payload["multivariate_downstream"]
    mdls = sorted({m for v in mv.values()
                   for m, x in v.items() if isinstance(x, dict) and "mse" in x})
    for mdl in mdls:
        base = mv.get("no_action", {}).get(mdl, {}).get("mse")
        print(f"\n-- {mdl}")
        print(f"{'method':22s}{'mse':>11s}{'block_mse':>12s}{'vs no_action':>14s}")
        for k in ["no_action", "stat_only", "stat_only_gated", "always_clean",
                  "always_clean_gated", "introact_full"]:
            v = mv.get(k, {}).get(mdl)
            if not v:
                continue
            rel = "ref" if k == "no_action" else f"{100 * (1 - v['mse'] / base):+.1f}%"
            print(f"{k:22s}{v['mse']:11.5f}{v['block_mse']:12.5f}{rel:>14s}")

    # -- consistency check, ungrouped corpus ----------------------------
    print("\nungrouped corpus, consistency check", flush=True)
    uw = build_corpus(spec, source="ett")
    agent2 = IntroActAgent(models, AgentConfig(verification=cfg))
    t0 = time.time()
    us = agent2.perceive(uw)
    print(f"  perceive {time.time() - t0:.0f}s", flush=True)
    utr = curate_all(uw, us, models, agent2, cfg)
    payload["ungrouped_curation"] = {k: curation_metrics(v, uw)
                                     for k, v in utr.items()}

    print(f"\n{'method':22s}{'grouped dmg':>13s}{'ungrouped dmg':>15s}"
          f"{'grouped rep':>13s}{'ungrouped rep':>15s}")
    for k in payload["grouped_curation"]:
        g = payload["grouped_curation"][k]
        u = payload["ungrouped_curation"].get(k)
        if not u:
            continue
        print(f"{k:22s}{g['mean_damage']:13.4f}{u['mean_damage']:15.4f}"
              f"{g['repair_reduction']:+13.3f}{u['repair_reduction']:+15.3f}")

    (ROOT / "results" / "b4.json").write_text(
        json.dumps(payload, indent=1, default=float), encoding="utf-8")
    print("___B4_DONE___", flush=True)


if __name__ == "__main__":
    main()
