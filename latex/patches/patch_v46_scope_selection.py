"""The scope section lists three assumptions and should list the fourth.

Selection reads one bank, and the measured sensitivity to that bank belongs
where the other assumptions are stated rather than only in the appendix that
measures it.
"""
import io

PATH = "latex/IntroActTS_20260919_v46.tex"

OLD = r"""Three further assumptions are worth stating explicitly. First, the action catalog is closed and
given."""

NEW = r"""Four further assumptions are worth stating explicitly. First, the action catalog is closed and
given."""

OLD_TAIL = r"""Every replay record is tied to the exact model revision that produced it, and a model update
invalidates the bank rather than silently degrading it."""

NEW_TAIL = r"""Every replay record is tied to the exact model revision that produced it, and a model update
invalidates the bank rather than silently degrading it. Fourth, the neighbourhood size and the
penalty strength are read off one bank. Appendix~\ref{app:selstability} measures how far that
choice travels, and the pair a subsample selects is usually a different one, so the reported
configuration should be read as one admissible point rather than as the only one the rule
would ever pick."""


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD in text, "assumption count"
    assert OLD_TAIL in text, "assumption tail"
    text = text.replace(OLD, NEW, 1)
    text = text.replace(OLD_TAIL, NEW_TAIL, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("scope section now names the selection assumption")


if __name__ == "__main__":
    main()
