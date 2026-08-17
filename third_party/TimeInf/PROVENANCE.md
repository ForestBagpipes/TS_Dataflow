# TimeInf, vendored verbatim

Source https://github.com/yzhang511/TimeInf
Commit 941052bcebed88de43f5c37d82e93bc075a7bbba
Commit date 2025-01-18
License MIT, see LICENSE in this directory

Only the `timeinf/` package is vendored. The rest of the upstream repository is
downstream task code this project does not use. **No file here is modified.**
The upstream package ships `_init_.py` with a single underscore, which is an
upstream typo that makes `timeinf` a namespace package rather than a regular
one. It is left as it is and the adapter loads the modules by path.

Adapter lives in `experiments/valuation_timeinf.py` and is ours.
