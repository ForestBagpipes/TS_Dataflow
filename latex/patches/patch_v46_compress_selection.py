"""Give the body back the lines the new selection rule took.

The rule needs to be in the body, but it does not need eight lines, and the
conclusion has to stay on the ninth page.
"""
import io

PATH = "latex/IntroActTS_20260919_v46.tex"

OLD_GRID = r"""$k \in \{8, 16, 32, 64, 128, 256\}$ and $\beta \in \{0, 0.5, 1, 1.64\}$, where the largest
penalty is the one-sided $95\%$ normal quantile and the largest neighbourhood is a seventh of
the bank. A setting is admissible when its cross-validated conditional harmful rate stays at or
below a cap."""

NEW_GRID = r"""$k \in \{8, 16, 32, 64, 128, 256\}$ and $\beta \in \{0, 0.5, 1, 1.64\}$, whose largest penalty
is the one-sided $95\%$ normal quantile. A setting is admissible when its cross-validated
conditional harmful rate stays at or below a cap."""

OLD_RULE = r"""largest penalty strength.

A few requests on which an intervention fails badly move the source macro further than the
ordinary spread between neighbouring settings, so the cross-validated surface is rough and its
minimum carries noise. Selection therefore runs in two steps over the admissible settings.
Each one is compared against the leading setting by a paired difference clustered on the
parent, and those whose gap falls inside one standard error are kept. Among them the rule
takes the setting that intervenes least, on the same reasoning as the cap: where the bank
cannot separate two settings, the one that touches fewer requests carries less exposure to
harm. The anchor, the cap, the retained settings and the selected pair are recorded before any
evaluation record is scored."""

NEW_RULE = r"""largest penalty strength. A few requests on which an intervention fails badly move the source
macro further than the spread between neighbouring settings, so the cross-validated surface is
rough and its minimum carries noise. Each admissible setting is therefore compared against the
leading one by a paired difference clustered on the parent, and among those whose gap falls
inside one standard error the rule takes the setting that intervenes least, on the same
reasoning as the cap. The anchor, the cap, the retained settings and the selected pair are
recorded before any evaluation record is scored."""


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD_GRID in text, "grid sentence"
    assert OLD_RULE in text, "selection paragraph"
    text = text.replace(OLD_GRID, NEW_GRID, 1)
    text = text.replace(OLD_RULE, NEW_RULE, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("selection paragraph compressed")


if __name__ == "__main__":
    main()
