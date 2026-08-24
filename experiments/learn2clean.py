"""Learn2Clean, ported to this paper's action space. Baseline L7.

Berti-Equille, WWW 2019. Q learning selects a sequence of preparation
operators, the reward is the change in a downstream quality metric, and each
selected operator is applied to the data immediately.

That last property is the reason this baseline is here. It is the closest
published design to ours and it differs in exactly the place the paper argues
about: there is no sandbox and no shield, so an operator chosen during
exploration rewrites the corpus and cannot be taken back. Our method's claim is
that deferring the verdict until after execution on a copy is what makes
learning safe, and a faithful Learn2Clean is the arm that claim is measured
against.

**What is ported and what is not.** The original operates on relational data
with normalisation, deduplication, imputation and outlier detection as its
operators. Ported here are its mechanism and its safety posture, not its
operator set:

  state    a discretised digest of the window's statistical profile
  action   one of this paper's seven operators, the same set our policy uses
  reward   the change in the downstream metric after the operator is applied
  update   tabular Q learning, epsilon greedy over the same action set
  timing   the operator is applied to the working series at once, no copy

Giving it our operator set rather than the original's is what makes the
comparison about the mechanism. A version that kept the original's operators
would differ from us in both the mechanism and the vocabulary, and no reading of
the result could separate the two.

**Reward, and why it is the fidelity change.** The original uses a downstream
model metric. The equivalent here that every arm can produce is the distance to
the clean reference, so the reward is its reduction. This gives Learn2Clean the
strongest possible signal, an oracle it would not have in deployment. That is
deliberate: a baseline weakened by a poor reward proves nothing, and if it still
damages protected windows while holding an oracle reward, the damage is the
mechanism rather than the signal.

Usage:
    python -u experiments/learn2clean.py --scale small --device cpu --preset offline
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))

from corpus import build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402

from introact_ts.actions import apply_action  # noqa: E402
from introact_ts.profiling import extract_statistical_profile  # noqa: E402
from introact_ts.types import Action, GovernanceTrace  # noqa: E402

#: The same seven operators the policy in section 3.4 chooses among, so the two
#: differ by mechanism and not by vocabulary.
ACTIONS = (Action.KEEP, Action.IMPUTE, Action.DESPIKE, Action.DENOISE,
           Action.RESEGMENT, Action.QUARANTINE, Action.ABSTAIN)

#: Terminal actions end the episode.
TERMINAL = (Action.KEEP, Action.QUARANTINE, Action.ABSTAIN)

#: Profile dimensions the state digest is built from, and the number of bins
#: each is cut into. A tabular method needs a small discrete state, and these
#: three carry the defect signal the operator choice turns on.
DIGEST_DIMS = (0, 1, 6)
DIGEST_BINS = 3


def state_of(profile, edges):
    """Discretised profile digest, the tabular state."""
    p = np.asarray(profile, dtype=np.float64)
    key = []
    for k, d in enumerate(DIGEST_DIMS):
        key.append(int(np.searchsorted(edges[k], p[d])))
    return tuple(key)


def digest_edges(profiles):
    """Bin edges from the corpus, so the state space is data driven."""
    P = np.asarray(profiles, dtype=np.float64)
    qs = np.linspace(0, 100, DIGEST_BINS + 1)[1:-1]
    return [np.percentile(P[:, d], qs) for d in DIGEST_DIMS]


def fidelity(series, clean, crop=0):
    """Distance to the clean reference. Lower is better."""
    if clean is None:
        return None
    a = np.asarray(series, dtype=np.float64)
    b = np.asarray(clean, dtype=np.float64)[crop:crop + len(a)]
    n = min(len(a), len(b))
    if n == 0:
        return None
    d = a[:n] - b[:n]
    d = d[np.isfinite(d)]
    if d.size == 0:
        return None
    return float(np.sqrt(np.mean(d ** 2)))


def run(windows, profiles, episodes=3, alpha=0.5, gamma=0.9, epsilon=0.2,
        max_steps=3, seed=42):
    """Q learning over the corpus, operators applied in place.

    Returns the traces of the final pass plus the learning record. Every
    episode edits the working series for real, which is the property under
    test, so the damage accumulated during exploration is part of the result
    rather than something the harness hides.
    """
    rng = np.random.RandomState(seed)
    edges = digest_edges(profiles)
    Q = defaultdict(lambda: np.zeros(len(ACTIONS), dtype=np.float64))
    history = []

    # One working copy of the corpus, carried across episodes. There is no
    # sandbox, so an edit made while exploring stays.
    work = {w.window_id: np.asarray(w.series, dtype=np.float64).copy()
            for w in windows}
    crops = {w.window_id: 0 for w in windows}

    for ep in range(episodes):
        damage_this_ep = 0
        order = rng.permutation(len(windows))
        for wi in order:
            w = windows[wi]
            x = work[w.window_id]
            s = state_of(profiles[wi], edges)
            for _ in range(max_steps):
                if rng.rand() < epsilon:
                    ai = int(rng.randint(len(ACTIONS)))
                else:
                    ai = int(np.argmax(Q[s]))
                action = ACTIONS[ai]
                if action in TERMINAL:
                    Q[s][ai] += alpha * (0.0 - Q[s][ai])
                    break
                before = fidelity(x, w.clean_series, crops[w.window_id])
                out = apply_action(x, action)
                if not out.applicable:
                    Q[s][ai] += alpha * (-0.01 - Q[s][ai])
                    continue
                new_crop = crops[w.window_id]
                if action is Action.RESEGMENT:
                    new_crop += int(out.params.get("lo", 0))
                after = fidelity(out.series, w.clean_series, new_crop)
                reward = 0.0 if (before is None or after is None) else before - after
                if reward < 0:
                    damage_this_ep += 1
                # The edit is committed regardless of the reward's sign. This is
                # the design, not an oversight: the reward is observed after the
                # data has already changed.
                x = out.series
                crops[w.window_id] = new_crop
                work[w.window_id] = x
                s2 = state_of(profiles[wi], edges)
                Q[s][ai] += alpha * (reward + gamma * float(np.max(Q[s2]))
                                     - Q[s][ai])
                s = s2
        history.append({"episode": ep, "harmful_edits": int(damage_this_ep),
                        "states": len(Q)})

    traces = []
    for w in windows:
        x = work[w.window_id]
        src = np.asarray(w.series, dtype=np.float64)
        changed = (len(x) != len(src)
                   or bool(np.any(np.abs(x - src[:len(x)]) > 1e-9)))
        traces.append(GovernanceTrace(
            window_id=w.window_id, stratum=w.stratum,
            contamination=w.contamination,
            initial_series=src.copy(), final_series=x,
            records=[], final_state="COMMIT" if changed else "KEEP",
            initial_utility=0.0, final_utility=0.0, risk_state={},
            probe_calls=0, crop_offset=crops[w.window_id]))
    return traces, history, Q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="small", choices=list(SCALES))
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--episodes", type=int, default=3)
    ap.add_argument("--epsilon", type=float, default=0.2)
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=1)
    ap.add_argument("--out", default=str(ROOT / "results" / "learn2clean.json"))
    args = ap.parse_args()

    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = build_corpus(spec, source=args.source)
    profiles = [extract_statistical_profile(
        np.nan_to_num(np.asarray(w.series, dtype=np.float64))) for w in windows]
    print(f"{len(windows)} windows, {args.episodes} episodes, "
          f"epsilon {args.epsilon}", flush=True)

    t0 = time.time()
    traces, history, Q = run(windows, profiles, episodes=args.episodes,
                             epsilon=args.epsilon, seed=args.seed)
    seconds = time.time() - t0

    from run_main import PROTECTED, score_rows
    row = score_rows(traces, windows)
    row["compute_seconds"] = seconds
    row["episodes"] = args.episodes
    row["q_states"] = len(Q)
    row["learning_history"] = history

    print(f"\nedits {row['committed_edits']}  "
          f"protected mis edits {row['protected_mis_edits']}  "
          f"damage {row['damage_rate']:.4f}  "
          f"repair {row['repair_gain']:+.4f}  {seconds:.0f}s")
    print("harmful edits per episode, which accumulate because there is no "
          "sandbox:")
    for h in history:
        print(f"  episode {h['episode']}  harmful {h['harmful_edits']:5d}  "
              f"states {h['states']}")

    Path(args.out).write_text(json.dumps(row, indent=1, default=float),
                              encoding="utf-8")
    print("___LEARN2CLEAN_DONE___", flush=True)


if __name__ == "__main__":
    main()
