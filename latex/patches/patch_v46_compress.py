"""Eighth v4.6 patch: compress the body back under the nine-page limit.

The related-work section repeated the introduction almost sentence for
sentence, and the selective-decision subsection repeated an appendix that says
the same thing at more length.  Both are cut to what the body needs, and the
appendix keeps the full argument.
"""
import io

PATH = "latex/IntroActTS_20260918_v45_review.tex"

REPLACEMENTS = [
    # Related work, route one and route three: the introduction already names
    # the representative methods, so the subsection states what each route
    # optimises rather than restating the list.
    ("""Three routes handle an incomplete input. The first reconstructs the missing values.
BRITS~\\citep{cao2018brits} performs bidirectional recurrent imputation,
CSDI~\\citep{tashiro2021csdi} replaces the deterministic mapping with a conditional score-based
diffusion model, GAIN~\\citep{yoon2018gain} and SAITS~\\citep{du2023saits} explore adversarial
and self-attention variants of the same objective, and T1~\\citep{park2026t1} improves
multivariate recovery under heavy and structurally different missingness. Their primary
comparisons are centred on reconstruction accuracy.

The second route forecasts from partially observed inputs without a separate imputation stage.
BiTGraph~\\citep{chen2024bitgraph} points out that imputing first and forecasting afterwards
accumulates error, and handles the missing pattern inside a biased temporal convolutional
network with a variable graph. S4M~\\citep{peng2025s4m} integrates missing-data handling into a
structured state-space architecture, and ChannelTokenFormer~\\citep{jang2026channeltokenformer}
addresses inter-channel dependency, asynchronous sampling, and test-time missing blocks
jointly. Methods on this route are complete forecasting models whose parameters are part of the
contribution.

The third route moves the objective from recovery to downstream utility. Task-oriented
imputation evaluation~\\citep{wang2024taskoriented} estimates how missing or imputed labels at
individual time steps affect the downstream forecasting model and combines imputation methods
according to the estimated gain. TOI-VSF~\\citep{hao2025toivsf} carries the objective into
\\emph{variable subset forecasting}, where whole variables are absent at inference.
GIMCC~\\citep{hao2025gimcc} adds multi-level causal consistency between the generated values and
the target, VIDA~\\citep{liang2025vida} reframes variable subset forecasting as cross-domain
knowledge transfer, and SRDI~\\citep{xu2026srdi} imputes diffusively in a space resilient to the
shift induced by variable absence. The variable subset setting removes whole variables, while
the protocol here removes positions inside the context, so we take from this route the methods
that emit a repaired input on our protocol and report them under that reading.

The three routes recover the missing values, train a predictor that tolerates them, or select
an imputation strategy from corpus-level task performance. \\introact{} keeps the predictor
fixed and addresses the deployment stage, where the request has already arrived, the backbone
is already frozen, the future target is unavailable, and the system selects one input version
from a finite catalog or keeps the reference input.""",
     """Three routes handle an incomplete input, and they differ in what they optimise. The first
reconstructs the hidden values and is scored on how close the reconstruction
is~\\citep{cao2018brits,tashiro2021csdi,yoon2018gain,du2023saits,park2026t1}. The second builds
a forecaster that reads the missing pattern directly, on the argument that imputing first and
forecasting afterwards accumulates error~\\citep{chen2024bitgraph,peng2025s4m,
jang2026channeltokenformer}; these are complete models whose parameters are part of the
contribution. The third replaces the recovery objective with a downstream
one~\\citep{wang2024taskoriented,hao2025toivsf,hao2025gimcc,liang2025vida,xu2026srdi}, mostly in
\\emph{variable subset forecasting}, where whole variables are absent at inference rather than
positions inside the context.

So the three routes recover the hidden values, train a predictor that tolerates them, or pick
an imputation strategy from corpus-level task performance. \\introact{} keeps the predictor fixed
and works at the deployment stage, where the request has arrived, the backbone is frozen, the
future target is unavailable, and the system selects one input version from a finite catalog or
keeps the reference input."""),

    # Selective decision making: the appendix carries the full positioning.
    ("""Selective prediction abstains on part of the input in order to trade coverage for lower
risk~\\citep{chow1970optimum,vovk2005algorithmic,geifman2017selective,lei2018distribution}.
Learning to defer instead routes part of the input to a human or to another decision
maker~\\citep{madras2018predict,mozannar2020consistent}. Both mechanisms change who or what
produces the answer. In \\introact{} the same frozen forecaster returns a forecast in every
case, and what is selected is whether the input is modified first.

The decision layer is a supervised local estimation problem rather than an off-policy one.
Historical replay executes every action in the finite catalog on the same window and evaluates
each against a realised future, so the bank holds full action outcomes rather than bandit
feedback from a logging policy, and no propensity correction is required. Dynamic feature
selection~\\citep{he2024dime} weighs the value of additional information against its cost in a
related sequential-acquisition setting. We make no information-theoretic optimality claim and
report the cost accounting separately (Appendix~\\ref{app:calls}).""",
     """Selective prediction abstains on part of the input to trade coverage for lower
risk~\\citep{chow1970optimum,vovk2005algorithmic,geifman2017selective,lei2018distribution}, and
learning to defer routes it to another decision maker~\\citep{madras2018predict,
mozannar2020consistent}. Both change who or what produces the answer. Here the same frozen
forecaster answers every request and what is selected is whether the input is modified first.
The decision layer is also a supervised local estimation problem rather than an off-policy
one~\\citep{dudik2011doubly,swaminathan2015counterfactual}, because replay executes every action
on the same window against the same realised future, so the bank holds full action outcomes and
no propensity correction arises. Appendix~\\ref{app:ope-positioning} states the positioning in
full."""),

    # The appendix map paragraph duplicates the table below it.
    ("""Table~\\ref{tab:app-map} lists what each appendix section contains. The appendix is organised
by evidence type rather than by individual analysis. Section~A fixes the protocol, the final
evaluation split, and the method details. Sections~B--D carry the evidence behind the
main-text tables. Section~E carries the ablations, the sensitivity grid, and the
mask-realisation stability check, and the replay-size study of our own bank sits in
Section~A with the rest of the bank construction. Sections~F and~G record cost and
reproducibility. A final unnumbered section holds exploratory material that does not support
any claim in the main text.""",
     """Table~\\ref{tab:app-map} lists what each appendix section contains. The appendix is organised
by evidence type rather than by individual analysis, and a final unnumbered section holds
exploratory material that supports no claim in the main text."""),
]


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    for old, new in REPLACEMENTS:
        assert old in text, old[:60]
        text = text.replace(old, new)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("compressed")


if __name__ == "__main__":
    main()
