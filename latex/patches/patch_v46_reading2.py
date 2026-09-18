"""Aggregate the rank and simple-selector sentences over every backbone, and
reword the main-comparison question so it names the controls the table holds.
"""
import io

READING = "latex/fill_v46_reading.py"
TEX = "latex/IntroActTS_20260918_v45_review.tex"

OLD_BLOCK = '''    r2 = comp.get("FULL_INTROACT_vs_R2_CART")
    if r2 is not None:
        tail = ("and the interval excludes zero" if r2["excludes_zero"]
                else "and the interval contains zero, so accuracy alone does not separate the "
                     "two and the difference between them is in Table~\\\\ref{tab:harm}")
        out["MAIN_R2CART"] = f"Against the simple selector the paired difference is {ci(r2)} {tail}"
    best_rank = min(ranks.items(), key=lambda kv: kv[1])
    if best_rank[0] == "FULL_INTROACT":
        out["MAIN_RANK"] = (
            f"Average rank over the evaluation cells is {ranks['FULL_INTROACT']:.2f} for "
            f"{INTRO}, the best of the {len(ranks)} rows that carry one, so the aggregate is not "
            f"driven by a few cells")
    else:
        out["MAIN_RANK"] = (
            f"Average rank over the evaluation cells is {ranks['FULL_INTROACT']:.2f} for "
            f"{INTRO} against {best_rank[1]:.2f} for the best row")
'''

NEW_BLOCK = '''    order = [b for b in ("bolt", "timesfm", "chronos2") if b in evals]
    parts = [f"{BACKBONE_NAME[b]} {ci(evals[b]['comparisons']['FULL_INTROACT_vs_R2_CART'])}"
             for b in order if "FULL_INTROACT_vs_R2_CART" in evals[b]["comparisons"]]
    if parts:
        sig = [b for b in order
               if evals[b]["comparisons"]["FULL_INTROACT_vs_R2_CART"]["excludes_zero"]]
        if not sig:
            tail = ("and no interval excludes zero, so accuracy alone does not separate the two "
                    "and what does is in Table~\\\\ref{tab:harm}")
        elif len(sig) == len(order):
            tail = "and every interval excludes zero"
        else:
            tail = ("and the interval excludes zero on "
                    + ", ".join(BACKBONE_NAME[b] for b in sig))
        out["MAIN_R2CART"] = ("Against the simple selector the paired difference is "
                              + "; ".join(parts) + ", " + tail)
    per_rank = {b: evals[b]["average_rank"] for b in order}
    ours_best = all(min(r.items(), key=lambda kv: kv[1])[0] == "FULL_INTROACT"
                    for r in per_rank.values())
    rank_parts = ", ".join(f"{BACKBONE_NAME[b]} {per_rank[b]['FULL_INTROACT']:.2f}"
                           for b in order)
    if ours_best:
        out["MAIN_RANK"] = (
            f"Average rank over the evaluation cells is {rank_parts}, the best of the "
            f"{len(ranks)} rows that carry one on every backbone, so the aggregate is not driven "
            f"by a handful of cells")
    else:
        out["MAIN_RANK"] = (
            f"Average rank over the evaluation cells is {rank_parts}, against "
            + ", ".join(f"{BACKBONE_NAME[b]} {min(per_rank[b].values()):.2f}" for b in order)
            + " for the best row on each")
'''

OLD_Q = ("\\emph{How does \\introact{} compare with published incomplete-input forecasting "
         "methods across\nsources and frozen \\tsfm{} backbones?}")
NEW_Q = ("\\emph{Does deciding per request beat doing nothing, applying one repair everywhere, "
         "and\nlearning a simple selector, across sources and frozen \\tsfm{} backbones?}")


def main() -> None:
    text = io.open(READING, encoding="utf-8").read()
    assert OLD_BLOCK in text, "reading block"
    io.open(READING, "w", encoding="utf-8").write(text.replace(OLD_BLOCK, NEW_BLOCK))

    tex = io.open(TEX, encoding="utf-8").read()
    assert OLD_Q in tex, "main question"
    io.open(TEX, "w", encoding="utf-8").write(tex.replace(OLD_Q, NEW_Q))
    print("reading aggregated and question reworded")


if __name__ == "__main__":
    main()
