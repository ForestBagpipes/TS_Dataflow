"""Collect Figures 4 and 5 from the recorded evaluation records.

Figure 4(a) is harmful loss per deployable method, averaged over the three
backbones.  Figure 4(b) is the realised utility of every admissible action
against the bin of its conservative score, with the interval that resamples
parents.  Figure 5 is the improvement over the untouched input as severity
rises, one line per method and one panel per backbone.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = Path(__file__).resolve().parent / "fig45_stats.json"
BACKBONES = ("bolt", "timesfm", "chronos2")
METHODS = (("NATIVE_KEEP", "Keep"), ("BEST_FIXED", "Best Fixed"), ("R2_CART", "R2-CART"),
           ("SAITS", "SAITS"), ("TATO", "TATO"), ("FULL_INTROACT", "IntroAct-TS"))
LEVELS = (("test", 10), ("test30", 30), ("test50", 50))


def load(block: str, backbone: str):
    path = ROOT / f"results/v46/evaluation/{block}_{backbone}.json"
    return json.loads(path.read_text()) if path.exists() else None


def main() -> None:
    harmful, present = [], []
    for key, label in METHODS:
        values = []
        for backbone in BACKBONES:
            payload = load("test", backbone)
            if payload and key in payload["rows"]:
                value = payload["rows"][key].get("harmful_loss")
                if value is not None:
                    values.append(value)
        if values:
            harmful.append({"key": key, "label": label,
                            "harmful_loss": sum(values) / len(values),
                            "backbones": len(values)})
            present.append(key)

    calibration = {}
    for backbone in BACKBONES:
        path = ROOT / f"results/v46/diagnostics/score_utility_test_{backbone}.json"
        if path.exists():
            payload = json.loads(path.read_text())
            calibration[backbone] = {
                "bins": [{"bin": row["bin"], "utility": row["utility_mean"],
                          "lo": row["ci_low"], "hi": row["ci_high"], "n": row["n"]}
                         for row in payload["bins"]],
                "sign_agreement": payload["sign_agreement"],
                "positive": payload["mean_utility_positive_score"],
                "negative": payload["mean_utility_negative_score"]}

    severity = {}
    for backbone in BACKBONES:
        series = {}
        for key, label in METHODS:
            if key == "NATIVE_KEEP":
                continue
            points = []
            for block, level in LEVELS:
                payload = load(block, backbone)
                if not payload or key not in payload["rows"]:
                    continue
                keep = payload["rows"].get("NATIVE_KEEP", {}).get("mase")
                value = payload["rows"][key].get("mase")
                if keep and value:
                    points.append({"severity": level,
                                   "improvement": (keep - value) / keep})
            if len(points) == len(LEVELS):
                series[key] = {"label": label, "points": points}
        if series:
            severity[backbone] = series

    payload = {"harmful_loss": harmful, "calibration": calibration, "severity": severity}
    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    spread = [round(row["harmful_loss"], 4) for row in harmful]
    print("harmful loss:", spread)
    print("calibration backbones:", list(calibration))
    print("severity backbones:", list(severity))


if __name__ == "__main__":
    main()
