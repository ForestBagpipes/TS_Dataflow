"""Style pass on the body: fewer contrastive constructions, fewer semicolons.

Each rewrite keeps the same content and says it as a positive statement.
"""
import io

PATH = "latex/IntroActTS_20260918_v45_review.tex"

PAIRS = [
    ("the forecasting model instead~\\citep{chen2024bitgraph,peng2025s4m}. Both lines need to train or\nredesign the predictor, which is what a frozen foundation model takes off the table.",
     "the forecasting model instead~\\citep{chen2024bitgraph,peng2025s4m}. Both lines train or\nredesign the predictor, which a frozen foundation model takes off the table."),

    ("observed look-back windows; here it appears only as the in-context regression backend of two\ncatalog actions, so two of the five actions cost one call to a frozen imputation model on top\nof the forecasting call (\\S\\ref{sec:method-deploy}).",
     "observed look-back windows. It appears here only as the in-context regression backend of two\ncatalog actions, so two of the five actions cost one call to a frozen imputation model on top\nof the forecasting call (\\S\\ref{sec:method-deploy})."),

    ("\\introact{} selects per request, and the pipeline it selects from is a closed catalog rather\nthan a search space.",
     "\\introact{} selects per request, and it selects from a closed catalog."),

    ("The decision layer is also a supervised local estimation problem rather than an off-policy\none~\\citep{dudik2011doubly,swaminathan2015counterfactual}, because replay executes every action\non the same window against the same realised future, so the bank holds full action outcomes and\nno propensity correction arises.",
     "The decision layer is a supervised local estimation problem. Replay executes every action on\nthe same window against the same realised future, so the bank holds full action outcomes and no\npropensity correction arises, which is what separates it from off-policy\nevaluation~\\citep{dudik2011doubly,swaminathan2015counterfactual}."),

    ("We measure it rather than assume it, and \\S\\ref{sec:exp-exists} reports how far the two\ndevelopment backbones diverge on exactly this point.",
     "We measure it, and \\S\\ref{sec:exp-exists} reports how far the two development backbones diverge\non this point."),

    ("The reference forecast is the only forecast that may be computed before the decision, which is a\ncall budget rather than a statement about the future:",
     "The reference forecast is the only forecast that may be computed before the decision. This is a\ncall budget, not a claim about what is knowable:"),

    ("The bank also covers only the missingness protocol registered in advance, which makes it a\ndiscrete grid over patterns and severities rather than a model of missingness.",
     "The bank also covers only the missingness protocol registered in advance, so it is a discrete\ngrid over patterns and severities."),

    ("Chronos-2\nenters only after the configuration is frozen, with the identical algorithm and hyperparameters\nand a replay bank rebuilt with Chronos-2 itself, so the held-out result is transfer of a frozen\nconfiguration across backbone families rather than transfer of a replay bank across backbones.",
     "Chronos-2\nenters only after the configuration is frozen, with the identical algorithm and the same\nselection rule applied to a replay bank rebuilt with Chronos-2 itself, so what transfers is the\nprocedure and not the bank."),
]


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    applied = 0
    for old, new in PAIRS:
        if old in text:
            text = text.replace(old, new)
            applied += 1
        else:
            print("  missed:", old[:60].replace("\n", " "))
    io.open(PATH, "w", encoding="utf-8").write(text)
    print(f"style pass: {applied}/{len(PAIRS)}")


if __name__ == "__main__":
    main()
