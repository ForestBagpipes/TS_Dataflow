"""Draw Figures 4 and 5 from the recorded numbers.

Both were skeletons carrying red markers and a tick list of methods that are not
in the evaluated roster.  They now read fig45_stats.json, which is built from the
evaluation records by make_fig45_stats.py.
"""
import io

PATH = "build_figures.py"

OLD_FIG4_START = "def fig4():"
OLD_FIG5_START = "def fig5():"
OLD_FIG5_END = "def main():"

NEW = '''def _load45():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fig45_stats.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def fig4():
    W, H = 396.0, 162.0
    f = Fig(W, H, "fig4_governance_diagnostics")
    stats = _load45()

    # ---- (a) harmful loss per method ----
    f.text(4.0, 9.0, "(a) Harmful loss by method", size=6.0, bold=True)
    ax, ay, aw, ah = 46.0, 32.0, 130.0, 86.0
    rows = (stats or {}).get("harmful_loss") or []
    top = max([r["harmful_loss"] for r in rows] + [0.05]) * 1.12
    ticks_y = [(v / top, ("%.2f" % v)) for v in (0.0, 0.10, 0.20, 0.30) if v <= top]
    n = max(len(rows), 1)
    ticks_x = [(((i + 0.5) / n), r["label"]) for i, r in enumerate(rows)]
    f.axes(ax, ay, aw, ah, xlabel="", ylabel="harmful loss (lower is better)",
           ticks_x=ticks_x, ticks_y=ticks_y)
    slot = aw / n
    for i, row in enumerate(rows):
        height = ah * (row["harmful_loss"] / top)
        ours = row["key"] == "FULL_INTROACT"
        f.rect(ax + i * slot + slot * 0.22, ay + ah - height, slot * 0.56, height,
               fill=(BLUE if ours else GREY_M), stroke=(INK if ours else FAINT), lw=0.6)
        if row["harmful_loss"] > 0:
            f.text(ax + i * slot + slot * 0.5, ay + ah - height - 3.0,
                   "%.3f" % row["harmful_loss"], size=4.4,
                   color=(INK if ours else MUTED), align="c")
    f.text(ax + aw / 2, ay + ah + 20.0,
           "mean over the three backbones; the reference action adds no harmful loss",
           size=4.6, color=MUTED, align="c")

    # ---- (b) realised utility against the score bin ----
    f.text(206.0, 9.0, "(b) Realised utility against the score bin", size=6.0, bold=True)
    bx, by, bw, bh = 250.0, 32.0, 132.0, 86.0
    calib = (stats or {}).get("calibration") or {}
    series = [(b, COLOUR45.get(b, INK)) for b in ("bolt", "timesfm", "chronos2") if b in calib]
    values = [v for b, _ in series for row in calib[b]["bins"] for v in (row["lo"], row["hi"])]
    lo_v = min(values + [-0.05])
    hi_v = max(values + [0.05])
    span = hi_v - lo_v
    lo_v, hi_v = lo_v - span * 0.08, hi_v + span * 0.08
    bins = max((len(calib[b]["bins"]) for b, _ in series), default=8)

    def why(value):
        return by + bh - bh * (value - lo_v) / (hi_v - lo_v)

    f.axes(bx, by, bw, bh, xlabel="conservative score, quantile bin",
           ylabel="realised utility",
           ticks_x=[(((i + 0.5) / bins), str(i + 1)) for i in range(bins)],
           ticks_y=[((v - lo_v) / (hi_v - lo_v), "%.2f" % v)
                    for v in (-0.3, -0.15, 0.0, 0.15) if lo_v <= v <= hi_v])
    f.line(bx, why(0.0), bx + bw, why(0.0), GREY_M, 0.6, dash=(2.0, 2.0))
    for index, (backbone, colour) in enumerate(series):
        offset = (index - (len(series) - 1) / 2.0) * (bw / bins) * 0.22
        points = []
        for row in calib[backbone]["bins"]:
            px = bx + ((row["bin"] - 0.5) / bins) * bw + offset
            points.append((px, why(row["utility"])))
            f.line(px, why(row["lo"]), px, why(row["hi"]), colour, 0.5)
        f.poly(points, colour, 0.9)
        for px, py in points:
            f.rect(px - 1.1, py - 1.1, 2.2, 2.2, fill=colour, stroke=WHITE, lw=0.3)
    for index, (backbone, colour) in enumerate(series):
        lx = bx + 6.0 + index * 44.0
        f.rect(lx, 14.0, 4.0, 4.0, fill=colour, stroke=None)
        f.text(lx + 6.0, 18.0, NAME45.get(backbone, backbone), size=5.0, color=INK)
    f.text(bx + bw / 2, by + bh + 26.0,
           "whiskers are 95% intervals that resample parents", size=4.6,
           color=MUTED, align="c")
    f.text(198.0, 156.0,
           "The score orders actions and the order agrees in sign with what the actions did. "
           "No claim is made that the score is on the scale of the utility.",
           size=5.0, color=MUTED, align="c")
    return f


def fig5():
    W, H = 396.0, 158.0
    f = Fig(W, H, "fig5_robustness_missingness")
    stats = _load45()
    severity = (stats or {}).get("severity") or {}
    panels = [("bolt", "Bolt"), ("timesfm", "TimesFM"), ("chronos2", "Chronos-2")]
    everything = [p["improvement"] for b, _ in panels if b in severity
                  for s in severity[b].values() for p in s["points"]]
    lo_v = min(everything + [0.0]) - 0.03
    hi_v = max(everything + [0.05]) + 0.03
    pw = 118.0
    order = ("FULL_INTROACT", "BEST_FIXED", "R2_CART", "SAITS", "TATO")
    for i, (key, title) in enumerate(panels):
        px = 8.0 + i * 128.0
        f.text(px + pw / 2, 9.0, title, size=6.0, bold=True, align="c")
        ax, ay, aw, ah = px + 26.0, 36.0, pw - 26.0, 84.0

        def why(value, ay=ay, ah=ah):
            return ay + ah - ah * (value - lo_v) / (hi_v - lo_v)

        f.axes(ax, ay, aw, ah, xlabel="missing severity",
               ylabel=("MASE improvement over the untouched input" if i == 0 else ""),
               ticks_x=[(0.0, "10%"), (0.5, "30%"), (1.0, "50%")],
               ticks_y=[((v - lo_v) / (hi_v - lo_v), "%+.0f%%" % (v * 100))
                        for v in (-0.2, -0.1, 0.0, 0.1, 0.2) if lo_v <= v <= hi_v])
        f.line(ax, why(0.0), ax + aw, why(0.0), GREY_M, 0.6, dash=(2.0, 2.0))
        series = severity.get(key, {})
        for name in order:
            entry = series.get(name)
            if not entry:
                continue
            colour = COLOUR45M.get(name, MUTED)
            ours = name == "FULL_INTROACT"
            points = [(ax + aw * j / 2.0, why(p["improvement"]))
                      for j, p in enumerate(entry["points"])]
            f.poly(points, colour, 1.4 if ours else 0.8)
            for cx, cy in points:
                f.rect(cx - 1.3, cy - 1.3, 2.6, 2.6, fill=colour, stroke=WHITE, lw=0.3)
    legend = [(name, COLOUR45M.get(name, MUTED),
               (severity.get("bolt", {}).get(name) or {}).get("label", name))
              for name in order]
    lx = 30.0
    for name, colour, label in legend:
        f.rect(lx, 126.0, 4.0, 4.0, fill=colour, stroke=None)
        f.text(lx + 6.0, 130.0, label, size=5.0, color=INK)
        lx += 24.0 + 3.4 * len(label)
    f.text(198.0, 150.0,
           "Every method reuses the rule frozen on TRAIN, with no retuning between levels.",
           size=5.0, color=MUTED, align="c")
    return f


'''


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    start = text.index(OLD_FIG4_START)
    end = text.index(OLD_FIG5_END)
    assert start < end, "order"
    # The banner comment between the two figures goes with them.
    text = text[:start] + NEW + text[end:]
    colours = ('COLOUR45 = {"bolt": BLUE, "timesfm": AMBER, "chronos2": GREEN}\n'
               'NAME45 = {"bolt": "Bolt", "timesfm": "TimesFM", "chronos2": "Chronos-2"}\n'
               'COLOUR45M = {"FULL_INTROACT": BLUE, "BEST_FIXED": AMBER, "R2_CART": GREEN,\n'
               '             "SAITS": RED, "TATO": FAINT}\n'
               'WHITE = ')
    text = text.replace("WHITE = ", colours, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("figures 4 and 5 now draw the recorded numbers")


if __name__ == "__main__":
    main()
