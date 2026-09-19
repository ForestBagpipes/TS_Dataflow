"""Appendix subsection: how the two published baselines were configured and run."""
import io

PATH = "latex/IntroActTS_20260919_v46.tex"
ANCHOR = "\\subsubsection{Per-Source Results}"

SECTION = r"""\subsection{Baseline Configuration}
\label{app:baseline-config}
Both published baselines are given the same evidence \introact{} is given, which is the TRAIN
region under the registered missingness protocol, including the realised futures of those
windows. Neither sees a TEST window or a TEST label before its numbers are computed.

\paragraph{SAITS.} One imputer per source, trained on that source's TRAIN bank windows after
the missingness protocol has been injected, so the training distribution is the one the
evaluation produces. The architecture is the packaged implementation~\citep{du2023pypots} with
two layers, model width 128, four heads, feed-forward width 128, dropout $0.1$, batch size 16
and at most \ph{SAITS_EPOCHS} epochs with early stopping. Sources with more channels than
\ph{SAITS_MAXCH} are imputed on the target channel plus the covariates most correlated with it
on TRAIN, which is a budget constant fixed before any run and recorded with the configuration.
The imputed panel is spliced back against the observation mask, so an entry that arrived and is
valid is returned unchanged and only the missing positions carry imputed values. That is the
same integrity constraint every catalog action obeys, and it is what makes the comparison a
comparison of input versions rather than of two different inputs.

\paragraph{TATO.} One transformation pipeline per source and per backbone, searched with the
official implementation over its eight transformation slots. A candidate pipeline is scored by
the mean absolute error of the resulting forecast against the realised future of
\ph{TATO_WINDOWS} TRAIN windows of that source, the same futures the replay bank is built from,
over \ph{TATO_TRIALS} trials seeded with the identity pipeline. The selected pipeline is then
applied unchanged to every TEST request of that source, which is the domain-level unit of
adaptation the method is defined at. The official pipeline expects a context without gaps, so
the adapter fills them by linear interpolation before the pipeline runs; that bridging step is
part of what the row measures, and Section~\ref{sec:exp-main} reads the result with that in
mind. The upstream replacement of non-finite outputs is disabled, so a pipeline that diverges
is recorded as a failed trial instead of being silently repaired.

"""


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert ANCHOR in text, "anchor"
    text = text.replace(ANCHOR, SECTION + ANCHOR, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("baseline configuration appendix added")


if __name__ == "__main__":
    main()
