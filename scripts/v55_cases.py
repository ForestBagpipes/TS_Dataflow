#!/usr/bin/env python3
"""Plot two actual TEST requests chosen by a declared, reproducible rule."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from introact_ts.v44 import catalog as C

ROOT = Path(__file__).resolve().parent.parent
BLOCK = "test"
BACKBONE = "bolt"
OUT = ROOT / "latex/figure/fig_case_v55.pdf"
META = ROOT / "results/v55/case_figure.json"


def choose(catalogs, winner: str):
    eligible = []
    for c in catalogs:
        if c.horizon != 96 or c.pattern != "P4_tail":
            continue
        if c.oracle()[0] != winner or not c.actions["SAITS"].scored:
            continue
        keep = c.actions["KEEP"].mase
        saits = c.actions["SAITS"].mase
        if keep is None or saits is None:
            continue
        margin = (saits - keep) if winner == "KEEP" else (keep - saits)
        if margin > 0:
            eligible.append((float(margin), c))
    if not eligible:
        raise RuntimeError(f"no eligible {winner} case")
    margins = np.asarray([x[0] for x in eligible])
    target = float(np.quantile(margins, 0.75))
    return min(eligible, key=lambda item: (abs(item[0] - target),
                                            item[1].episode))


def main() -> None:
    C.REPLAY = "results/v47/replay"
    catalogs = C.load_catalog(ROOT, BLOCK, BACKBONE)
    chosen = [choose(catalogs, name) for name in ("KEEP", "SAITS")]
    with np.load(ROOT / "results/v47/replay/saits/test.npz",
                 allow_pickle=False) as store:
        fig, axes = plt.subplots(2, 1, figsize=(8.4, 5.8), sharex=True)
        fig.subplots_adjust(bottom=0.21, hspace=0.28)
        records = []
        for ax, (winner, (margin, c)) in zip(axes, zip(("KEEP", "SAITS"), chosen)):
            repaired = store[f"{c.episode}|SAITS"]
            dirty = c.reference_target
            x_context = np.arange(-128, 0)
            x_future = np.arange(c.horizon)
            ax.plot(x_context, repaired[-128:], color="#008b8b", lw=1.2,
                    label="SAITS-filled context")
            valid = np.isfinite(dirty[-128:])
            ax.scatter(x_context[valid], dirty[-128:][valid], s=6,
                       color="#31333b", label="Observed context", zorder=3)
            ax.plot(x_future, c.future, color="#31333b", lw=1.3,
                    label="Future target")
            ax.plot(x_future, c.actions["KEEP"].prediction,
                    color="#355bb5", lw=1.1, label="KEEP forecast")
            ax.plot(x_future, c.actions["SAITS"].prediction,
                    color="#cf6839", lw=1.1, label="SAITS forecast")
            ax.axvline(-0.5, color="#9aa0a6", lw=0.8)
            ax.set_title(f"{winner} best: {c.source}, H=96, "
                         f"KEEP {c.actions['KEEP'].mase:.3f}, "
                         f"SAITS {c.actions['SAITS'].mase:.3f}",
                         loc="left", fontsize=9)
            ax.grid(alpha=0.2)
            records.append({"winner": winner, "episode": c.episode,
                            "source": c.source, "parent": c.parent,
                            "pattern": c.pattern, "severity": c.severity,
                            "keep_mase": c.actions["KEEP"].mase,
                            "saits_mase": c.actions["SAITS"].mase,
                            "margin": margin,
                            "selection": "H=96, tail gap, "
                                         "oracle winner, nearest 75th percentile "
                                         "KEEP-vs-SAITS margin"})
        axes[-1].set_xlabel("Steps relative to forecast origin")
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=3,
                   bbox_to_anchor=(0.5, 0.01), frameon=False, fontsize=8)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(OUT)
        plt.close(fig)
    META.parent.mkdir(parents=True, exist_ok=True)
    META.write_text(json.dumps({"stage": "v55-case-figure",
                                "backbone": BACKBONE, "block": BLOCK,
                                "cases": records, "figure": str(OUT)}, indent=1))
    print(META.read_text())


if __name__ == "__main__":
    main()
