"""Compress the introduction's survey paragraphs, which Section 2 repeats.

The introduction needs to name the three routes and say why each is closed for
a frozen forecaster.  Naming every representative method twice is what made it
long.
"""
import io

PATH = "latex/IntroActTS_20260918_v45_review.tex"

OLD = """The usual response to missing data is imputation. Reconstruction-oriented methods recover the
missing entries as accurately as possible and are scored on reconstruction error. BRITS uses
bidirectional recurrent dynamics~\\citep{cao2018brits}, CSDI models the conditional
distribution of the missing values with a score-based diffusion
process~\\citep{tashiro2021csdi}, and SAITS attacks the same objective with self-attention and
a joint reconstruction and imputation loss~\\citep{du2023saits}. A second line handles
missingness inside the forecasting model, where BiTGraph couples biased temporal convolution
with a graph over variables~\\citep{chen2024bitgraph} and S4M folds the missing pattern into a
structured state-space model~\\citep{peng2025s4m}. Both lines need to train or redesign the
predictor, which is what a frozen foundation model takes off the table.

A third line moves the objective from recovery to downstream utility. Task-oriented imputation
evaluation estimates how imputed values at different time steps affect a downstream
forecasting model and combines imputation strategies according to the estimated
gain~\\citep{wang2024taskoriented}, and later work carries that objective into variable subset
forecasting~\\citep{hao2025toivsf,hao2025gimcc,xu2026srdi}. TATO adapts a frozen \\tsfm{} to
heterogeneous domains through transformation pipelines selected from historical task
performance~\\citep{qiu2026tato}. These methods decide at training time, over a corpus, which
strategy or transformation to use. The decision studied here is made at deployment time, for
one request."""

NEW = """The usual response is imputation, and it is scored on how accurately the missing entries come
back~\\citep{cao2018brits,tashiro2021csdi,du2023saits}. A second line handles missingness inside
the forecasting model instead~\\citep{chen2024bitgraph,peng2025s4m}. Both lines need to train or
redesign the predictor, which is what a frozen foundation model takes off the table. A third
line moves the objective from recovery to downstream utility, estimating how imputed values
affect the forecaster and combining strategies by the estimated
gain~\\citep{wang2024taskoriented,hao2025toivsf,xu2026srdi}, and TATO adapts a frozen \\tsfm{} to
a domain through transformation pipelines selected from historical task
performance~\\citep{qiu2026tato}. These methods decide at training time, over a corpus, which
strategy or transformation to use. The decision studied here is made at deployment time, for
one request."""


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD in text, "intro survey"
    io.open(PATH, "w", encoding="utf-8").write(text.replace(OLD, NEW))
    print("introduction compressed")


if __name__ == "__main__":
    main()
