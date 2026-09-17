"""Hash helpers for v4.4.

Byte-identical to the canonical project implementation in
``introact_ts.v43.schemas`` so that cache identities computed by v4.4 code
agree with identities computed by the frozen r5 code and with any artifact
already on disk.  Re-exported rather than re-implemented on purpose: a second
implementation that drifts by one byte would silently invalidate every cache
key in the project.
"""

from __future__ import annotations

from ..v43.schemas import ContractError, array_hash, frozen_array, json_hash, require

__all__ = ["ContractError", "array_hash", "frozen_array", "json_hash", "require"]
