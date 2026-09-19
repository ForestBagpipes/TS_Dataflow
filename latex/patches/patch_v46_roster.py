"""Align the roster text, the tables and the availability appendix with what ran.

TOI estimates the influence of imputed values on a downstream model through
generalised representers, which needs gradients through that model.  A frozen
foundation model served as a fixed inference pipeline does not expose them, so
TOI is discussed and not tabulated, and the appendix says so in those terms
rather than calling it unavailable.
"""
import io
import re

PATH = "latex/IntroActTS_20260919_v46.tex"

OLD_ROSTER = """action when its probability exceeds one half. Published methods that compose with a frozen
backbone add three types: SAITS~\\citep{du2023saits,du2023pypots} covers reconstruction-based
imputation, TOI~\\citep{wang2024taskoriented} covers task-oriented utility, and
TATO~\\citep{qiu2026tato} covers data-side adaptation of a frozen \\tsfm{}. A \\emph{Catalog
Oracle} that reads the future target is reported as a diagnostic and excluded from all ranks."""

NEW_ROSTER = """action when its probability exceeds one half. Two published methods compose with a frozen
backbone and are reported in full: SAITS~\\citep{du2023saits,du2023pypots} is the
reconstruction baseline, trained per source on the same TRAIN windows under the same
missingness protocol, and TATO~\\citep{qiu2026tato} is the data-side adaptation baseline, whose
transformation pipeline is searched per source against the realised futures of the same TRAIN
windows the replay bank is built from, so neither method is given evidence the other lacks. A
\\emph{Catalog Oracle} that reads the future target is reported as a diagnostic and excluded
from all ranks."""

OLD_AVAIL_ROWS = """    SAITS~\\citep{du2023saits}       & ESWA 2023  & official, packaged~\\citep{du2023pypots} & reconstruction baseline \\\\
    TOI~\\citep{wang2024taskoriented}& NeurIPS 2024 & official repository & task-oriented baseline \\\\
    TATO~\\citep{qiu2026tato}        & ICLR 2026  & official repository & data-side adaptation baseline \\\\
    \\midrule
    BRITS~\\citep{cao2018brits}      & NeurIPS 2018 & available & superseded by SAITS on this protocol \\\\
    CSDI~\\citep{tashiro2021csdi}    & NeurIPS 2021 & available & not run, cost per request exceeds the deployment budget \\\\
    T1~\\citep{park2026t1}           & ICLR 2026  & no public release found & discussed only \\\\"""

NEW_AVAIL_ROWS = """    SAITS~\\citep{du2023saits}       & ESWA 2023  & official, packaged~\\citep{du2023pypots} & reconstruction baseline \\\\
    TATO~\\citep{qiu2026tato}        & ICLR 2026  & official repository & data-side adaptation baseline \\\\
    \\midrule
    TOI~\\citep{wang2024taskoriented}& NeurIPS 2024 & official repository & needs gradients through the downstream forecaster \\\\
    BRITS~\\citep{cao2018brits}      & NeurIPS 2018 & available & superseded by SAITS on this protocol \\\\
    CSDI~\\citep{tashiro2021csdi}    & NeurIPS 2021 & available & not run, cost per request exceeds the deployment budget \\\\
    T1~\\citep{park2026t1}           & ICLR 2026  & no public release found & discussed only \\\\"""

OLD_AVAIL_TEXT = """The comparison names more published methods in Section~\\ref{sec:related} than it reports in
Table~\\ref{tab:main}. The reason is implementation availability under the protocol of this
paper, and Table~\\ref{tab:app-availability} records it method by method. A method enters the
tables only when an official implementation exists, admits an incomplete context of the shape
this protocol produces, and emits an input version a frozen backbone can consume. A
reimplementation from a paper description would not be comparable with the numbers that paper
reports, so a method without a usable implementation is left out of the tables rather than
approximated."""

NEW_AVAIL_TEXT = """The comparison names more published methods in Section~\\ref{sec:related} than it reports in
Table~\\ref{tab:main}, and Table~\\ref{tab:app-availability} records why method by method. A
method enters the tables when an official implementation exists, when it admits an incomplete
context of the shape this protocol produces, and when its own assumptions hold for a frozen
backbone. A reimplementation from a paper description would not be comparable with the numbers
that paper reports, so a method that fails any of the three is discussed and not tabulated.

One exclusion is about assumptions rather than about code. Task-oriented imputation
evaluation~\\citep{wang2024taskoriented} scores an imputation by the influence its values have
on the downstream forecaster, estimated with generalised representers, which requires gradients
of that forecaster with respect to its input. The setting of this paper is a forecaster served
as a fixed inference pipeline, which is what makes the decision an input-side one in the first
place, and such a pipeline exposes no gradients. Running the method would mean replacing the
frozen backbone by a differentiable surrogate, and the number that came out would describe the
surrogate. We therefore report the task-oriented idea in Section~\\ref{sec:related} and carry
its objective, realised downstream utility, into our own replay, which measures the same
quantity by executing the action instead of differentiating through the model."""


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD_ROSTER in text, "roster"
    text = text.replace(OLD_ROSTER, NEW_ROSTER)
    assert OLD_AVAIL_ROWS in text, "availability rows"
    text = text.replace(OLD_AVAIL_ROWS, NEW_AVAIL_ROWS)
    assert OLD_AVAIL_TEXT in text, "availability text"
    text = text.replace(OLD_AVAIL_TEXT, NEW_AVAIL_TEXT)

    # TOI leaves every table; SAITS and TATO stay.
    out = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("TOI ") and "\\ph{" in line and "&" in line:
            continue
        if stripped.startswith("TOI  ") and "\\ph{" in line:
            continue
        out.append(line)
    text = "\n".join(out)
    text = re.sub(r"^(\s*)TOI\s+&[^\n]*\\ph\{[^\n]*\n", "", text, flags=re.M)

    io.open(PATH, "w", encoding="utf-8").write(text)
    print("roster aligned with what ran")


if __name__ == "__main__":
    main()
