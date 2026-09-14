# Issue and email to send, drafted for the user to post

`gh` is not installed in this environment and posting requires authentication,
so this is prepared text rather than a sent message. Two destinations: a GitHub
issue at https://github.com/Syh517/AegisTS/issues/new and an email to the
corresponding author of arXiv 2605.04902.

Date drafted 2026-08-11. If sent today, the 8 working day stop loss expires
2026-08-21.

---

## Title

Missing `Datasets` module blocks running the pipeline

## Body

Hello, and thank you for releasing the code alongside the paper.

We are reproducing AegisTS to use it as a baseline in a paper on time series
data curation, and we intend to cite it. While setting it up we found that the
`Datasets` package is not present in the repository, and every core module
imports from it:

- `Error_Cleaner/RLclean.py:26` — `from Datasets.load_dataset import load_single_dataset, sample_data_by_rate, convert_to_unix_timestamp`
- `Error_Detection/Detector.py:28` — same three functions
- `Error_Detection/Detector.py:30` — `load_single_dataset, sample_data_by_rate`
- `Error_Cleaner/tools/missing.py:139` — `from Datasets.load_dataset import load_single_dataset`
- `Error_Cleaner/tools/anomaly.py:151` — same
- `Error_Cleaner/tools/constraints.py:85` — same

The repository `.gitignore` contains `Datasets/` and `*.csv`, so we suspect the
module was excluded unintentionally along with the data files it loads. Since
`load_single_dataset`, `sample_data_by_rate` and `convert_to_unix_timestamp`
are code rather than data, the four modules above cannot be imported without
them.

Would it be possible to add `Datasets/load_dataset.py`, or alternatively to
share a data preparation script and the expected return contract of
`load_single_dataset`, that is the array shape, dtype and the meaning of the
`rate` and `label` arguments? Either would let us run the pipeline as published
rather than reconstructing the loader ourselves, which we would prefer to avoid
precisely because a reconstructed loader would make any comparison we report
less trustworthy for you as well as for us.

For context on what we are trying to run: `Error_Cleaner/RLclean.py` `main()`
on ETTh1 forecasting, to check our setup against the ETTh1 row of your results
table before using the system as a proposer in our own evaluation.

Thank you for your time.

---

## Notes for the email version

Same body, with a first line stating the paper title and arXiv number so the
author can place the request, and a closing line offering to share our
comparison results before submission if that is of interest. Keep the tone as
above: this is a reproduction request from people who intend to cite the work,
not a defect report.
