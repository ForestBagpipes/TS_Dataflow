"""The bank-size reading described the opposite of what the current run shows.

Under the earlier selection the held-out backbone did worse with the full bank
than with a quarter of it.  With the neighbourhood and the penalty chosen by the
standard-error rule the held-out backbone improves monotonically with history and
it is the second development backbone that sits flat, so the paragraph is
rewritten around the measured direction.
"""
import io

PATH = "latex/IntroActTS_20260919_v46.tex"

OLD = """On the two development
backbones more history helps or saturates. On the held-out backbone the full bank is worse than
the quarter bank at the frozen neighbourhood size, which says that the neighbourhood size and
the amount of history interact and that a configuration frozen on one backbone's bank does not
automatically sit at the right point on another's."""

NEW = """On Bolt and on the
held-out backbone the macro average falls with every step up in history, from \\ph{BANK_Q_BOLT}
to \\ph{BANK_F_BOLT} and from \\ph{BANK_Q_CH2} to \\ph{BANK_F_CH2}. On TimesFM the three levels
sit within \\ph{BANK_SPREAD_TF} of each other, so history neither helps nor hurts there. The
intervention rate moves with the bank on all three, which is the mechanism behind the trend:
a denser bank changes how many requests clear the conservative threshold, so the amount of
history and the penalty strength are not independent knobs."""


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD in text, "bank size paragraph"
    text = text.replace(OLD, NEW, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("bank-size paragraph rewritten around the measured direction")


if __name__ == "__main__":
    main()
