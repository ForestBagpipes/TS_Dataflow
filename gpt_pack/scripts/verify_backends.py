"""Load each frozen backend and exercise the probe surface against real weights.

The adapters in ``introact_ts.backends`` are written against published APIs but
cannot be executed without the checkpoints, so none of them has run locally.
Run this first on the machine that has the GPU. It reports, per backend, what
loaded, which probe operations returned usable output, and how the forecast
compares to a seasonal-naive reference -- an adapter that imports cleanly can
still return the wrong shape, the wrong axis order, or a degenerate forecast.

    python scripts/verify_backends.py --device cuda
    python scripts/verify_backends.py --device cuda --backends chronos:amazon/chronos-bolt-base
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from introact_ts.backends import FAMILIES, PRESETS, probe_report  # noqa: E402

DEFAULT_SPECS = [
    "surrogate:0",
    "chronos:amazon/chronos-bolt-base",
    "chronos:amazon/chronos-bolt-small",
    "chronos:amazon/chronos-t5-small",
    "moment:AutonLab/MOMENT-1-large",
    "timesfm:google/timesfm-2.5-200m-pytorch",
]


def render(records: list) -> str:
    lines = ["# Backend verification", ""]
    lines.append("| backend | loaded | layers | capabilities | forecast | batch | reconstruct | encode |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in records:
        if not r["loaded"]:
            lines.append(
                f"| `{r['spec']}` | NO | - | - | - | - | - | - |"
            )
            continue
        checks = r["checks"]

        def cell(key):
            v = checks.get(key)
            if v is None:
                return "n/a"
            if isinstance(v, str):
                return "FAIL"
            if key == "forecast":
                return f"ok ({v['vs_seasonal_naive']}x naive)"
            if key == "reconstruct":
                return f"ok (mse {v['mse']})"
            if key == "encode":
                return f"ok ({v['n_layers']}x{v['dim']})"
            return "ok"

        lines.append(
            f"| `{r['spec']}` | yes | {r.get('n_layers', '?')} "
            f"| {','.join(r.get('capabilities', []))} "
            f"| {cell('forecast')} | {cell('forecast_batch')} "
            f"| {cell('reconstruct')} | {cell('encode')} |"
        )

    failures = [
        (r["spec"], k, v)
        for r in records
        for k, v in r.get("checks", {}).items()
        if isinstance(v, str)
    ]
    errors = [(r["spec"], r["error"]) for r in records if r.get("error")]
    if errors or failures:
        lines += ["", "## Problems", ""]
        for spec, err in errors:
            lines.append(f"- `{spec}` did not load: {err}")
        for spec, check, err in failures:
            lines.append(f"- `{spec}` failed `{check}`: {err}")
    else:
        lines += ["", "All requested backends loaded and passed every check."]

    lines += [
        "",
        "`forecast` is reported relative to a seasonal-naive baseline: below 1.0 "
        "means the model beats it. A value near or above 1.0 on a clean seasonal "
        "series usually means the adapter is mis-wiring the input, not that the "
        "checkpoint is weak.",
    ]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--backends", nargs="*", default=None,
                    help="specs to check; defaults to one per family")
    ap.add_argument("--preset", choices=list(PRESETS), default=None,
                    help="check every backend named by a preset")
    ap.add_argument("--out", default=str(ROOT / "results" / "backend_verification.md"))
    args = ap.parse_args()

    if args.preset:
        specs = PRESETS[args.preset]["curation"] + PRESETS[args.preset]["transfer"]
    else:
        specs = args.backends or DEFAULT_SPECS

    print(f"families known: {sorted(FAMILIES)}")
    print(f"checking {len(specs)} backends on {args.device}\n")
    records = probe_report(specs, device=args.device)

    report = render(records)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps(records, indent=2, default=str), encoding="utf-8"
    )
    print(report)
    print(f"written to {out}")

    ok = all(
        r["loaded"] and not any(isinstance(v, str) for v in r["checks"].values())
        for r in records
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
