"""Third trim: shorten the two longest captions and the replay subsection.

Nothing load bearing is removed.  The architecture caption repeated what the
figure already shows, and the replay subsection said the same thing about the
future twice.
"""
import io

PATH = "latex/IntroActTS_20260918_v45_review.tex"

PAIRS = [
    ("""  \\caption{Architecture of \\introact{}. \\textbf{Offline (top)}: historical TRAIN windows are
  turned into incomplete contexts by injecting the registered missingness protocol, every
  catalog action is executed with the frozen forecaster, and the realised utilities populate
  the replay bank. This is the only place where a future is read. \\textbf{Online (bottom)}: a
  request exposes an incomplete context only. The reference forecast is computed, an
  action-conditioned state $z_a$ is formed for each admissible action, and each state is scored
  against the frozen bank. One action is then executed with the same frozen forecaster, and
  neither a future target nor a non-selected candidate's forecast is accessed online.}""",
     """  \\caption{Architecture of \\introact{}. \\textbf{Offline}: TRAIN windows become incomplete
  contexts under the registered missingness protocol, every catalog action is executed with the
  frozen forecaster, and the realised utilities populate the replay bank. This is the only place
  a future is read. \\textbf{Online}: the reference forecast is computed, an action-conditioned
  state $z_a$ is formed per action and scored against the frozen bank, and one action is
  executed with the same frozen forecaster.}"""),

    ("""  \\caption{Selective input governance for a frozen forecaster. \\textbf{(a)}~Measured action
  utility on the evaluation episodes, drawn from the recorded statistics rather than from
  hand-picked examples. The oracle-best action is not constant across requests, so a single
  fixed intervention leaves part of the available improvement unused. \\textbf{(b)}~Historical
  full-action replay. TRAIN windows are replayed under the registered missingness protocol,
  every catalog action is executed with the frozen forecaster, and the realised utilities are
  stored in the replay bank. \\textbf{(c)}~Online decision. The reference forecast is computed,
  each admissible action is scored from the same-action neighbourhood of its action-conditioned
  state, and the best action is executed only when its conservative score is positive.}""",
     """  \\caption{\\textbf{(a)}~Share of held-out episodes on which each catalog action is oracle-best.
  No action holds the role often enough for one fixed choice to serve every request.
  \\textbf{(b)}~Historical full-action replay on TRAIN. \\textbf{(c)}~The online decision, which
  executes an action only when its conservative score is positive.}"""),

    ("""The quantity that decides the action, $g_a$, depends on $Y$ and is not observable online, but
it is computable for a historical window. Take a TRAIN window $i$ whose forecast target $y_i$
is already part of the available history, inject the registered missingness protocol to obtain
$(X_i, M_i)$, materialise every action in the catalog, and execute the frozen pipeline on each
version. The realised utility of action $a$ on window $i$ is""",
     """The quantity that decides the action, $g_a$, depends on $Y$ and is not observable online, but it
is computable for a historical window whose target is already part of the available history.
Take such a window $i$, inject the registered missingness protocol to obtain $(X_i, M_i)$,
materialise every action, and execute the frozen pipeline on each version. The realised utility
of action $a$ on window $i$ is"""),

    ("""This is a measured outcome of an action the deployed system would not otherwise have taken,
recovered by re-executing a historical window rather than by modelling it, and both terms are
evaluated against the same realised future.

The state recorded with each outcome is action conditioned. For window $i$ and action $a$,""",
     """Both terms are evaluated against the same realised future, so this is a measurement rather
than a model of what the action would have done.

The state recorded with each outcome is action conditioned. For window $i$ and action $a$,"""),
]


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    for old, new in PAIRS:
        assert old in text, old[:60]
        text = text.replace(old, new)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print(f"trimmed {len(PAIRS)} passages")


if __name__ == "__main__":
    main()
