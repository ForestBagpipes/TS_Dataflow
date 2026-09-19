"""Cross-validation was picking the argmin of a rough surface.

The grid now runs further out in the neighbourhood size, because the old grid's
largest neighbourhood was selected on two of the three backbones, and the rule
keeps every admissible setting the bank cannot separate from the leader and then
takes the one that intervenes least.
"""
import io

PATH = "latex/IntroActTS_20260919_v46.tex"

OLD = r"""statement about a request the bank has not seen. The grid is
$k \in \{8, 16, 32, 64\}$ and $\beta \in \{0, 0.5, 1, 1.64\}$. Among the grid points whose
cross-validated conditional harmful rate stays at or below a cap, we take the point with the
lowest cross-validated MASE. The cap is not a free number: it is the conditional harmful rate
of the action with the highest mean realised utility on the same bank, so the constraint says
that choosing per request may not be more harmful, given that it intervenes, than always
applying the strongest single intervention. If no grid point satisfies it the configuration
falls back to the largest penalty strength. The anchor, the cap and the selected pair are
recorded before any evaluation record is scored."""

NEW = r"""statement about a request the bank has not seen. The grid is
$k \in \{8, 16, 32, 64, 128, 256\}$ and $\beta \in \{0, 0.5, 1, 1.64\}$, where the largest
penalty is the one-sided $95\%$ normal quantile and the largest neighbourhood is a seventh of
the bank. A setting is admissible when its cross-validated conditional harmful rate stays at or
below a cap. The cap is not a free number: it is the conditional harmful rate of the action
with the highest mean realised utility on the same bank, so the constraint says that choosing
per request may not be more harmful, given that it intervenes, than always applying the
strongest single intervention. If no setting satisfies it the configuration falls back to the
largest penalty strength.

A few requests on which an intervention fails badly move the source macro further than the
ordinary spread between neighbouring settings, so the cross-validated surface is rough and its
minimum carries noise. Selection therefore runs in two steps over the admissible settings.
Each one is compared against the leading setting by a paired difference clustered on the
parent, and those whose gap falls inside one standard error are kept. Among them the rule
takes the setting that intervenes least, on the same reasoning as the cap: where the bank
cannot separate two settings, the one that touches fewer requests carries less exposure to
harm. The anchor, the cap, the retained settings and the selected pair are recorded before any
evaluation record is scored."""

OLD_TAIL = r"""forbids, and it is one reason the neighbourhood size matters: a local estimate over eight
neighbours is exposed to an outlier that an estimate over sixty-four dilutes."""

NEW_TAIL = r"""forbids, and it is one reason the neighbourhood size matters: a local estimate over eight
neighbours is exposed to an outlier that an estimate over two hundred and fifty-six dilutes."""


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD in text, "selection paragraph"
    assert OLD_TAIL in text, "neighbourhood sentence"
    text = text.replace(OLD, NEW, 1)
    text = text.replace(OLD_TAIL, NEW_TAIL, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("selection rule and grid updated")


if __name__ == "__main__":
    main()
