"""The three properties a post hoc shield is supposed to have, measured.

A shield sits outside the proposer, watches proposed actions, and vetoes the
ones that would violate the specification. Three properties are usually asked
of such a layer, and all three are measurable here from traces already on disk.

  soundness         no admitted edit violates the specification
  minimal           interference few beneficial edits are blocked
  non blocking      some action is always available

Soundness and minimality are empirical and come from the governance traces.
Non blocking is structural and is argued rather than sampled, since a single
counterexample would refute it and no amount of sampling can establish it.

Minimality needs a notion of beneficial that the shield itself does not have
access to, so it is judged offline against the pristine series. That is the
right ruler for the question: it asks how often the shield refused something
that would have helped, which only an oracle can answer.

CPU only, reads existing results.
"""

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import _nmse  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402

from introact_ts.actions import apply_action  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402

TRACES = ROOT / "results" / "xl" / "xl_ett_multi-family_seed42_traces.json"
TAU_REPORTED = 0.12  # the threshold the xl run used


def main():
    if not TRACES.exists():
        print("deferred, no xl traces on disk")
        return
    spec = CorpusSpec(n_contaminated=740, n_clean=420, n_hard=210,
                      n_rare_valid=210, n_changepoint=210, n_clean_ood=210,
                      seed=42)
    windows = {w.window_id: w for w in build_corpus(spec, source="ett")}
    traces = json.loads(TRACES.read_text(encoding="utf-8"))["introact_full"]
    cfg = VerifyConfig(tau=TAU_REPORTED)
    print(f"{len(traces)} traces, tau {TAU_REPORTED}, epsilon {cfg.epsilon}, "
          f"eta {cfg.eta}\n")

    # -- soundness ---------------------------------------------------------
    admitted = [(t, s) for t in traces for s in t["steps"]
                if s["verdict"] == "ACCEPTED"]
    unsound = [(t, s) for t, s in admitted
               if not (s["delta_utility"] > cfg.epsilon
                       and s["struct_distortion"] < cfg.tau
                       and s["risk"] < cfg.eta)]
    print("soundness, every admitted edit satisfies the specification")
    print(f"  admitted edits           {len(admitted)}")
    print(f"  violating the spec       {len(unsound)}")
    print(f"  soundness rate           "
          f"{1 - len(unsound) / max(len(admitted), 1):.6f}")
    if unsound:
        print("  violations:")
        for t, s in unsound[:5]:
            print(f"    window {t['window_id']} {s['action']} "
                  f"du {s['delta_utility']:+.4f} d {s['struct_distortion']:.4f} "
                  f"r {s['risk']:.3f}")

    # -- minimal interference ---------------------------------------------
    # A blocked edit is beneficial if replaying it alone would have lowered the
    # NMSE against the pristine series. Replay is needed because the trace only
    # records what the shield saw, not the counterfactual outcome.
    blocked = [(t, s) for t in traces for s in t["steps"]
               if s["verdict"].startswith("ROLLED_BACK")]
    print(f"\nminimal interference, of the blocked edits how many would have helped")
    print(f"  blocked edits            {len(blocked)}")

    helpful = 0
    checked = 0
    by_reason = Counter()
    helpful_by_reason = Counter()
    for t, s in blocked:
        w = windows.get(t["window_id"])
        if w is None or w.clean_series is None:
            continue
        try:
            out = apply_action(np.asarray(w.series, float),
                               s["action"], **(s.get("params") or {}))
        except Exception:
            continue
        if not out.applicable:
            continue
        checked += 1
        by_reason[s["verdict"]] += 1
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        before = _nmse(w.series, w.clean_series, ref_var)
        lo = int((out.params or {}).get("lo", 0)) if s["action"] == "RESEGMENT" else 0
        after = _nmse(out.series, w.clean_series[lo:], ref_var)
        if after < before - 1e-9:
            helpful += 1
            helpful_by_reason[s["verdict"]] += 1

    print(f"  replayable and checked   {checked}")
    print(f"  would have helped        {helpful}")
    print(f"  forgone benefit rate     {helpful / max(checked, 1):.4f}")
    print(f"  by veto reason:")
    for reason, n in by_reason.most_common():
        h = helpful_by_reason[reason]
        print(f"    {reason:24s} blocked {n:4d}  of which helpful {h:4d}"
              f"  ({h / max(n, 1):.3f})")

    # -- non blocking ------------------------------------------------------
    print(f"\nnon blocking, stated as a proposition rather than sampled")
    print("  Proposition. In every state at least one action is admissible.")
    print("  Proof. KEEP returns the working copy unchanged. Its delta utility")
    print("  is 0, its structural distance is 0 and its cost is 0, so it is")
    print("  never vetoed by the structural or risk conditions. The utility")
    print("  condition applies only to mutating actions, so KEEP is admissible")
    print("  in every state, and the action set is therefore never empty. A")
    print("  window can always be returned untouched, which is why the shield")
    print("  cannot deadlock.")
    keeps = sum(1 for t in traces for s in t["steps"] if s["action"] == "KEEP")
    empty = sum(1 for t in traces if not t["steps"])
    print(f"  KEEP appears in the traces {keeps} times; "
          f"{empty} traces have no step at all")
    print("  Note this is a structural argument. The counts are consistency")
    print("  evidence, not the proof.")

    payload = {
        "tau": TAU_REPORTED, "epsilon": cfg.epsilon, "eta": cfg.eta,
        "soundness": {"admitted": len(admitted), "violations": len(unsound),
                      "rate": 1 - len(unsound) / max(len(admitted), 1)},
        "minimal_interference": {
            "blocked": len(blocked), "checked": checked, "helpful": helpful,
            "forgone_rate": helpful / max(checked, 1),
            "by_reason": {k: {"blocked": v, "helpful": helpful_by_reason[k]}
                          for k, v in by_reason.items()}},
        "non_blocking": {"argument": "KEEP is admissible in every state",
                         "keep_steps": keeps, "empty_traces": empty},
    }
    (ROOT / "results" / "shield_properties.json").write_text(
        json.dumps(payload, indent=1, default=float), encoding="utf-8")
    print("\n___SHIELD_PROPERTIES_DONE___")


if __name__ == "__main__":
    main()
