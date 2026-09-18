"""Collect the two panels of Figure 3 from the recorded diagnostics.

Panel (a) is the joint distribution of the within-episode reconstruction rank
and the within-episode realised-utility rank over the four catalog
interventions, summed over the backbones and row-normalised.

Panel (b) is the cross-validated conditional harmful rate against the
intervention rate over the penalty grid, with the selected point marked.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = Path(__file__).resolve().parent / "fig3_stats.json"
BACKBONES = ("bolt", "timesfm", "chronos2")


def main() -> None:
    grid = None
    agree, disc, rho, n = [], [], [], 0
    for backbone in BACKBONES:
        path = ROOT / f"results/v46/diagnostics/reconstruction_test_{backbone}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        rg = payload.get("rank_grid")
        if rg:
            grid = rg if grid is None else [[a + b for a, b in zip(r1, r2)]
                                            for r1, r2 in zip(grid, rg)]
        agree.append(payload["winner_agreement"])
        disc.append(payload["discordant_rate"])
        rho.append(payload["mean_within_episode_spearman"])
        n += payload["episodes_compared"]

    curve = []
    selected = None
    for backbone in BACKBONES:
        path = ROOT / f"results/v46/protocol/selection_{backbone}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        chosen = payload["selection"]["selected"]
        for row in payload["selection"]["grid"]:
            point = {"backbone": backbone, "k": row["k"], "beta": row["beta"],
                     "intervention_rate": row["intervention_rate"],
                     "conditional_hir": row["conditional_hir"]}
            curve.append(point)
            if row["k"] == chosen["k"] and abs(row["beta"] - chosen["beta"]) < 1e-9:
                point["selected"] = True
                if backbone == "bolt":
                    selected = point
        cap = payload["harm_cap"]["cap"]

    stats = {
        "rank_grid": grid,
        "winner_agreement": sum(agree) / len(agree) if agree else None,
        "discordant_rate": sum(disc) / len(disc) if disc else None,
        "spearman": sum(rho) / len(rho) if rho else None,
        "episodes": n,
        "curve": curve,
        "selected": selected,
        "cap": cap,
        "actions": ["FFILL", "SINGLE_TSICL", "MULTI_TSICL", "CONTEXT_RIDGE"],
    }
    OUT.write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "curve"}, indent=1)[:600])
    print("curve points:", len(curve))


if __name__ == "__main__":
    main()
