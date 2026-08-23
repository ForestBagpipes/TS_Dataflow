"""Order flip rate of the substituted judgment backend, before any annotation.

TSRating distils a rater from an LLM's pairwise preferences. Swapping the
backend from `gpt-4o-mini` to `deepseek-v4-pro` is only sound if the new backend
gives a stable preference, so this measures the one thing that would invalidate
the whole arm: how often the preference reverses when the two series swap
places.

The method already presents every pair in both orders. `score_pairwise.py`
loops `for i in range(n): for j in range(n)` with n equal to 2, so it queries
(A,B) and (B,A) and then calibrates by

    calibrated = (p + (1 - p.T)) / 2

Order sensitivity is therefore not an extra experiment, it is a quantity the
method computes and discards. This script keeps it.

Definitions, fixed before the run:

  vote share      of the 20 generations in one order, the fraction preferring
                  the second option, exactly `parse_generations` plus the same
                  normalisation
  agreement       the two orders agree when both put the same series ahead,
                  that is (p_ab > 0.5) equals (p_ba < 0.5)
  flip            the complement of agreement, counted only on pairs where
                  neither order was an exact tie
  high confidence the calibrated score is at most 0.25 or at least 0.75, which
                  is the threshold the method itself uses to decide a pair is
                  usable

Prompt, template, generation count, serialisation and parsing are the
repository's, unchanged. Only the model and the endpoint differ.

The key is read from the environment and is never written to disk or logged.

Usage:
    DEEPSEEK_API_KEY=... python -u experiments/tsrating_consistency.py --pairs 12
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

#: The vendored TSRating checkout. Its serialiser and templates are used
#: verbatim so the prompt this backend sees is the prompt the paper's backend
#: saw.
TSRATING = ROOT / ".tmp" / "TSRating"

BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-pro"

#: The repository's own values, from prompting/run_score_pairwise.py and
#: data_preparation/load_Time_300B.py.
GENERATIONS = 20
LABELS = ("A", "B")
MAX_SEQ_LEN = 128
SERIALIZE_PREC = 4
DIMENSIONS = ("trend", "frequency", "amplitude", "pattern")

#: Thinking is on by default on this model and a pairwise preference needs no
#: chain of thought. Measured on a one letter reply, leaving it on spent 23 of
#: 25 output tokens on reasoning. Both `thinking` and `reasoning_effort` switch
#: it off; the explicit form is used.
THINKING_OFF = {"thinking": {"type": "disabled"}}

#: With thinking on, `max_tokens` has to cover the reasoning as well as the
#: answer. At the disabled run's value of 8 the reasoning would consume the
#: whole budget and the reply would come back empty, so the two arms cannot share
#: one value. This is the only setting that differs between them and it is forced
#: by the mode rather than chosen.
MAX_TOKENS_NO_THINK = 8
MAX_TOKENS_THINK = 2048


def load_serialiser():
    sys.path.insert(0, str(TSRATING / "data_preparation"))
    from serialize import SerializerSettings, serialize_arr  # noqa: E402
    return serialize_arr, SerializerSettings(prec=SERIALIZE_PREC)


def series_to_text(x, serialize_arr, settings):
    """Serialise one window the way the repository does before prompting.

    Its loader takes at most `max_seq_len` points and serialises at precision
    `prec`. The serialiser asserts the values are within `max_val`, so the
    window is put on a comparable footing first, which is also what the
    repository's own Time-300B loader relies on since that corpus is normalised.
    """
    x = np.asarray(x, dtype=np.float64)
    if len(x) > MAX_SEQ_LEN:
        x = x[:MAX_SEQ_LEN]
    lo, hi = float(np.min(x)), float(np.max(x))
    if hi - lo < 1e-12:
        x = np.zeros_like(x)
    else:
        x = (x - lo) / (hi - lo)
    return str(serialize_arr(x, settings))


def _one(client, prompt, thinking):
    kwargs = {}
    if thinking:
        kwargs["max_tokens"] = MAX_TOKENS_THINK
    else:
        kwargs["max_tokens"] = MAX_TOKENS_NO_THINK
        kwargs["extra_body"] = THINKING_OFF
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0,
        **kwargs,
    )
    u = r.usage
    det = getattr(u, "completion_tokens_details", None)
    reasoning = getattr(det, "reasoning_tokens", 0) if det else 0
    return ((r.choices[0].message.content or "").strip(),
            u.prompt_tokens, u.completion_tokens,
            getattr(u, "prompt_cache_hit_tokens", 0), reasoning or 0)


def balance_cny(key):
    """Current balance, used only to enforce the spend cap."""
    import urllib.request
    req = urllib.request.Request(
        "https://api.deepseek.com/user/balance",
        headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=20) as fh:
        d = json.loads(fh.read().decode("utf-8"))
    return float(d["balance_infos"][0]["total_balance"])


def query(client, prompt, n, thinking=False, workers=10):
    """n independent generations.

    This backend rejects `n` greater than one, which is the parameter the
    repository uses to draw its twenty votes in a single request, so the votes
    become twenty requests. They are independent, so they go concurrently. The
    prompt is byte identical across them, which is also why the prefix cache hit
    rate on this workload is high rather than marginal.
    """
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda _: _one(client, prompt, thinking), range(n)))


def vote_share(generations):
    """Fraction of parsed votes that chose the second label."""
    a = sum(1 for g, *_ in generations if g == LABELS[0])
    b = sum(1 for g, *_ in generations if g == LABELS[1])
    if a + b == 0:
        return None, a, b
    return b / (a + b), a, b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=12)
    ap.add_argument("--dimensions", nargs="+", default=list(DIMENSIONS))
    ap.add_argument("--generations", type=int, default=GENERATIONS)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--thinking", action="store_true",
                    help="leave the model's reasoning on, see MAX_TOKENS_THINK")
    ap.add_argument("--max-spend-cny", dest="max_spend", type=float, default=40.0,
                    help="abort once this much has been spent, checked per pair")
    ap.add_argument("--out", default=str(ROOT / "results" / "tsrating_consistency.json"))
    args = ap.parse_args()

    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY is not set, refusing to run")
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=BASE_URL)

    serialize_arr, settings = load_serialiser()

    from corpus import CorpusSpec, build_corpus
    spec = CorpusSpec(n_contaminated=40, n_clean=20, n_hard=10, n_rare_valid=10,
                      n_changepoint=10, n_clean_ood=10, seed=args.seed)
    windows = build_corpus(spec, source="ett")
    rng = np.random.RandomState(args.seed)
    idx = rng.choice(len(windows), size=2 * args.pairs, replace=False)
    pairs = [(windows[idx[2 * i]], windows[idx[2 * i + 1]])
             for i in range(args.pairs)]
    print(f"{len(windows)} windows, {len(pairs)} pairs, "
          f"{len(args.dimensions)} dimensions, {args.generations} generations, "
          f"model {MODEL}, thinking disabled", flush=True)

    rows, tok_in, tok_out, tok_cached, tok_reason, calls = [], 0, 0, 0, 0, 0
    start_balance = balance_cny(key)
    aborted = False
    print(f"balance {start_balance:.2f} CNY, cap {args.max_spend:.2f} CNY, "
          f"thinking {'enabled' if args.thinking else 'disabled'}", flush=True)
    t0 = time.time()
    for dim in args.dimensions:
        if aborted:
            break
        template = (TSRATING / "prompting" / "templates"
                    / f"pairwise_{dim}.txt").read_text(encoding="utf-8")
        for pi, (wa, wb) in enumerate(pairs):
            ta = series_to_text(wa.series, serialize_arr, settings)
            tb = series_to_text(wb.series, serialize_arr, settings)
            forward = template.format(text_a=ta, text_b=tb,
                                      label_a=LABELS[0], label_b=LABELS[1])
            reverse = template.format(text_a=tb, text_b=ta,
                                      label_a=LABELS[0], label_b=LABELS[1])
            g_ab = query(client, forward, args.generations, args.thinking)
            g_ba = query(client, reverse, args.generations, args.thinking)
            calls += 2 * args.generations
            for g in g_ab + g_ba:
                tok_in += g[1]
                tok_out += g[2]
                tok_cached += g[3]
                tok_reason += g[4]

            spent = start_balance - balance_cny(key)
            if spent > args.max_spend:
                print(f"  spend cap reached, {spent:.2f} of {args.max_spend:.2f} "
                      f"CNY, stopping after {len(rows)+1} pair dimensions",
                      flush=True)
                aborted = True

            p_ab, a1, b1 = vote_share(g_ab)
            p_ba, a2, b2 = vote_share(g_ba)
            row = {"dimension": dim, "pair": pi,
                   "p_ab": p_ab, "p_ba": p_ba,
                   "votes_ab": [a1, b1], "votes_ba": [a2, b2],
                   "stratum_a": wa.stratum, "stratum_b": wb.stratum}
            if p_ab is not None and p_ba is not None:
                # In the forward order the second option is wb, in the reverse
                # order the second option is wa. The two agree when they put the
                # same window ahead.
                cal = (p_ab + (1.0 - p_ba)) / 2.0
                row["calibrated"] = cal
                row["tie"] = bool(abs(p_ab - 0.5) < 1e-9 or abs(p_ba - 0.5) < 1e-9)
                row["agree"] = bool((p_ab > 0.5) == (p_ba < 0.5))
                row["high_confidence"] = bool(cal <= 0.25 or cal >= 0.75)
            rows.append(row)
            print(f"  {dim:10s} pair {pi:2d}  p_ab={p_ab}  p_ba={p_ba}  "
                  f"agree={row.get('agree')}  cal={row.get('calibrated')}",
                  flush=True)
            if aborted:
                break

    scored = [r for r in rows if "agree" in r and not r["tie"]]
    flip = [r for r in scored if not r["agree"]]
    by_dim = {}
    for dim in args.dimensions:
        s = [r for r in scored if r["dimension"] == dim]
        f = [r for r in s if not r["agree"]]
        hc = [r for r in rows if r["dimension"] == dim and r.get("high_confidence")]
        by_dim[dim] = {"scored": len(s), "flips": len(f),
                       "flip_rate": len(f) / len(s) if s else None,
                       "high_confidence": len(hc),
                       "hc_rate": len(hc) / len(pairs)}

    elapsed = time.time() - t0
    report = {
        "model": MODEL, "base_url": BASE_URL,
        "thinking": "enabled" if args.thinking else "disabled",
        "max_tokens": MAX_TOKENS_THINK if args.thinking else MAX_TOKENS_NO_THINK,
        "reasoning_tokens": tok_reason,
        "aborted_on_spend_cap": aborted,
        "spend_cny": start_balance - balance_cny(key),
        "generations": args.generations, "pairs": len(pairs),
        "dimensions": list(args.dimensions), "seed": args.seed,
        "calls": calls, "prompt_tokens": tok_in, "completion_tokens": tok_out,
        "cached_prompt_tokens": tok_cached,
        "cache_hit_fraction": tok_cached / tok_in if tok_in else 0.0,
        "seconds": elapsed,
        "overall": {"scored": len(scored), "flips": len(flip),
                    "flip_rate": len(flip) / len(scored) if scored else None},
        "by_dimension": by_dim,
        "rows": rows,
    }
    print()
    print(f"{'dimension':12s}{'scored':>8s}{'flips':>7s}{'flip rate':>11s}"
          f"{'high conf':>11s}")
    for dim, v in by_dim.items():
        fr = "n/a" if v["flip_rate"] is None else f"{v['flip_rate']:.3f}"
        print(f"{dim:12s}{v['scored']:8d}{v['flips']:7d}{fr:>11s}"
              f"{v['hc_rate']:11.3f}")
    o = report["overall"]
    fr = "n/a" if o["flip_rate"] is None else f"{o['flip_rate']:.3f}"
    print(f"{'overall':12s}{o['scored']:8d}{o['flips']:7d}{fr:>11s}")
    print()
    print(f"{calls} calls, {tok_in} prompt tokens, {tok_out} completion tokens "
          f"of which {tok_reason} reasoning, "
          f"cache hit {report['cache_hit_fraction']:.3f}, {elapsed:.0f}s, "
          f"spend {report['spend_cny']:.2f} CNY"
          + (" ABORTED ON CAP" if aborted else ""))
    print(f"per pair per dimension: {tok_in/max(len(rows),1):.0f} prompt tokens, "
          f"{2*args.generations} calls")

    Path(args.out).write_text(json.dumps(report, indent=1, default=float),
                              encoding="utf-8")
    print("___TSRATING_CONSISTENCY_DONE___", flush=True)


if __name__ == "__main__":
    main()
