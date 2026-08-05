"""Backwards-compatible facade over :mod:`introact_ts.backends`.

The backend layer grew from one offline surrogate into a registry of real
checkpoints; this module keeps the original import paths working.
"""

from .backends import (
    SurrogateTSFM,
    TSFMBackend,
    make_backend,
    make_model_pool,
    make_pool,
    make_reference_corpus,
    probe_report,
)
from .backends.surrogate import CONTEXT_LEN, HIDDEN_DIM, N_LAYERS

__all__ = [
    "CONTEXT_LEN",
    "HIDDEN_DIM",
    "N_LAYERS",
    "SurrogateTSFM",
    "TSFMBackend",
    "make_backend",
    "make_model_pool",
    "make_pool",
    "make_reference_corpus",
    "probe_report",
]
