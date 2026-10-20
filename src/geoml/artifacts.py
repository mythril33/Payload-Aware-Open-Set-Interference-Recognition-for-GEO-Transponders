"""Stable identities for JSON-compatible experiment and artifact metadata."""
from __future__ import annotations

import hashlib
import json


def fingerprint(value) -> str:
    """SHA-256 of canonical JSON; tuple/list representations have the same identity.

    Reject non-finite numbers rather than persisting nonstandard JSON identities.
    This identifies declared configuration/provenance, not arbitrary Python objects.
    """
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
