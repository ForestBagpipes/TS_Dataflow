"""Update the Figure 3 caption to describe the panels that are now drawn."""
import io

PATH = "latex/IntroActTS_20260918_v45_review.tex"

OLD = """  \\caption{\\textbf{(a)}~Within-episode reconstruction rank against realised-utility rank
  over the four catalog interventions on the held-out episodes. Points off the diagonal are
  episodes where the more accurate reconstruction is not the more useful intervention.
  \\textbf{(b)}~Conditional harmful rate against intervention rate along the penalty grid,
  with the selected operating point marked.}"""

NEW = """  \\caption{\\textbf{(a)}~Joint distribution of the within-episode reconstruction rank and the
  within-episode realised-utility rank over the four catalog interventions, row-normalised over
  the held-out episodes of all three backbones. Off-diagonal mass is episodes on which the more
  accurate reconstruction is not the more useful intervention. \\textbf{(b)}~Cross-validated
  conditional harmful rate against intervention rate over the neighbourhood and penalty grid,
  one point per grid cell per backbone, with the selected point enlarged and the cap marked.}"""


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD in text, "figure 3 caption"
    io.open(PATH, "w", encoding="utf-8").write(text.replace(OLD, NEW))
    print("figure 3 caption updated")


if __name__ == "__main__":
    main()
