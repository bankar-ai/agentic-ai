"""Scans a generated answer for well-known secret formats before it reaches the caller (AGT-056).

The Verifier's `grounded` check is a factual-accuracy check -- does each claim trace back to real
retrieved evidence -- not a safety check. If an ingested document (or web result) happened to
contain a real secret and the Writer quoted it accurately, the Verifier would call that "grounded"
and let it through, since grounded only means "supported by evidence," not "safe to show." This is
a separate, final check specifically for that gap.

Pattern-based, not exhaustive: catches well-known, well-structured secret formats (cloud provider
keys, platform tokens, PEM headers, JWTs, generic bearer/API-key-shaped strings), not every
conceivable secret -- a proportionate first layer, not a claim of completeness.
"""

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Private key block", re.compile(r"-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    # Generic "api_key: <long-opaque-value>" / "Bearer <long-opaque-value>" shapes -- deliberately
    # conservative (20+ char unbroken token) to avoid flagging ordinary prose.
    ("Generic API key assignment", re.compile(r"\b(?:api[_-]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?", re.IGNORECASE)),
    ("Bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9_\-.]{20,}\b")),
]


def find_likely_secret(text: str) -> str | None:
    """Returns the name of the first matched pattern, or `None` if nothing matched."""
    for name, pattern in _PATTERNS:
        if pattern.search(text):
            return name
    return None
