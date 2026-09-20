"""Replace the Figure 3 placeholder panels with the recorded diagnostics."""
import io

PATH = "latex/figure/build_figures.py"
START = "def fig3():"
END = "# ==========================================================================\n# Figure 4"

NEW = '''def fig3():
    """Figure 3: why the criterion has to be forecasting utility, and why selective.

    Both panels read ``figure/fig3_stats.json``.  Panel (a) is the joint
    distribution of the within-episode reconstruction rank and realised-utility
    rank over the four catalog interventions, row-normalised.  Panel (b) is the
    cross-validated harm against intervention rate over the penalty grid.  With
    no stats file the panels are drawn empty and labelled, never filled in.
    """
    import json
    import os

    W, H = 396.0, 190.0
    f = Fig(W, H, "fig3_why_selective")
    stats_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fig3_stats.json")
    stats = None
    if os.path.exists(stats_path):
        with open(stats_path, "r", encoding="utf-8") as fh:
            stats = json.load(fh)

    # ---- (a) rank agreement between the two criteria ----
    f.text(4.0, 9.0, "(a) Reconstruction rank vs realised-utility rank", size=6.0, bold=True)
    ax, ay, aw, ah = 42.0, 30.0, 120.0, 92.0
    f.axes(ax, ay, aw, ah, ylabel="realised utility rank",
           ticks_x=[(0.125, "1"), (0.375, "2"), (0.625, "3"), (0.875, "4")],
           ticks_y=[(0.125, "4"), (0.375, "3"), (0.625, "2"), (0.875, "1")])
    if stats is not None and stats.get("rank_grid"):
        grid = stats["rank_grid"]
        cw, ch = aw / 4.0, ah / 4.0
        for i, row in enumerate(grid):
            total = float(sum(row)) or 1.0
            for j, count in enumerate(row):
                share = count / total
                # Blue saturates towards the row maximum; 0.25 is chance.
                t = max(0.0, min(1.0, share / 0.45))
                fill = (BLUE_L[0] + (BLUE[0] - BLUE_L[0]) * t,
                        BLUE_L[1] + (BLUE[1] - BLUE_L[1]) * t,
                        BLUE_L[2] + (BLUE[2] - BLUE_L[2]) * t)
                f.rect(ax + i * cw, ay + j * ch, cw, ch, fill=fill, stroke=WHITE, lw=0.5)
                f.text(ax + (i + 0.5) * cw, ay + (j + 0.5) * ch + 1.6,
                       "%.2f" % share, size=4.6,
                       color=(WHITE if t > 0.62 else INK), align="c")
        f.line(ax, ay + ah, ax + aw, ay, INK, 0.7, dash=(2.5, 2.0))
        f.text(ax + aw / 2, ay + ah + 20.0, "reconstruction rank within episode",
               size=4.9, color=MUTED, align="c")
        f.text(ax + aw / 2, ay + ah + 29.0,
               "diagonal = the two criteria agree; agreement %.0f%%"
               % (100.0 * stats["winner_agreement"]), size=4.9, color=INK, align="c")
        f.text(ax + aw / 2, ay + ah + 37.0,
               "discordant pairs %.0f%%, within-episode rho %.2f"
               % (100.0 * stats["discordant_rate"], stats["spearman"]),
               size=4.9, color=MUTED, align="c")
    else:
        f.rect(ax + 6.0, ay + 24.0, aw - 12.0, 42.0, fill=None, stroke=FAINT, lw=0.6,
               dash=(2.0, 2.0))
        f.text(ax + aw / 2, ay + 44.0, "from the recorded diagnostics", size=5.0,
               color=MUTED, align="c")

    # ---- (b) harm against intervention rate over the penalty grid ----
    f.text(200.0, 9.0, "(b) Harm against intervention rate", size=6.0, bold=True)
    bx, by, bw, bh = 236.0, 30.0, 150.0, 92.0
    f.axes(bx, by, bw, bh, ylabel="conditional harmful rate",
           ticks_x=[(0.0, "0"), (0.5, "0.5"), (1.0, "1")],
           ticks_y=[(0.0, "0.25"), (0.5, "0.38"), (1.0, "0.50")])
    if stats is not None and stats.get("curve"):
        style = {"bolt": (BLUE, "Bolt"), "timesfm": (AMBER, "TimesFM"),
                 "chronos2": (GREEN, "Chronos-2")}
        lo, hi = 0.25, 0.50
        for backbone, (colour, label) in style.items():
            points = [p for p in stats["curve"] if p["backbone"] == backbone]
            points.sort(key=lambda p: p["intervention_rate"])
            for p in points:
                px = bx + bw * max(0.0, min(1.0, p["intervention_rate"]))
                py = by + bh - bh * max(0.0, min(1.0, (p["conditional_hir"] - lo) / (hi - lo)))
                if p.get("selected"):
                    f.rect(px - 2.4, py - 2.4, 4.8, 4.8, fill=colour, stroke=INK, lw=0.7)
                else:
                    f.rect(px - 1.1, py - 1.1, 2.2, 2.2, fill=colour, stroke=None, lw=0.0)
        y_cap = by + bh - bh * max(0.0, min(1.0, (stats["cap"] - lo) / (hi - lo)))
        f.line(bx, y_cap, bx + bw, y_cap, RED, 0.7, dash=(2.5, 2.0))
        f.text(bx + bw - 2.0, y_cap - 3.0, "harm cap", size=4.6, color=RED, align="r")
        for i, (backbone, (colour, label)) in enumerate(style.items()):
            lx = bx + 4.0 + i * 46.0
            f.rect(lx, by + 4.0, 4.0, 4.0, fill=colour, stroke=None, lw=0.0)
            f.text(lx + 6.0, by + 8.0, label, size=4.8, color=MUTED)
        f.text(bx + bw / 2, by + bh + 20.0, "intervention rate", size=4.9,
               color=MUTED, align="c")
        f.text(bx + bw / 2, by + bh + 29.0,
               "one point per neighbourhood size and penalty strength", size=4.9,
               color=MUTED, align="c")
        f.text(bx + bw / 2, by + bh + 37.0,
               "large marker = the point the cross-validation selected", size=4.9,
               color=MUTED, align="c")
    else:
        f.rect(bx + 8.0, by + 24.0, bw - 16.0, 42.0, fill=None, stroke=FAINT, lw=0.6,
               dash=(2.0, 2.0))
        f.text(bx + bw / 2, by + 44.0, "from the recorded grid", size=5.0,
               color=MUTED, align="c")

    f.text(198.0, 176.0,
           "The two criteria agree barely more often than chance, and moving along the penalty "
           "grid trades intervention rate against accuracy at a nearly fixed harmful rate.",
           size=5.0, color=MUTED, align="c")
    return f


'''


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    i = text.find(START)
    j = text.find(END, i)
    assert i > 0 and j > i, "fig3 block"
    io.open(PATH, "w", encoding="utf-8").write(text[:i] + NEW + text[j:])
    print("fig3 rewritten")


if __name__ == "__main__":
    main()
