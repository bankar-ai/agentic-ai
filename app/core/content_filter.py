"""A basic, keyword/pattern-based filter for abusive or inappropriate content (AGT-057).

Explicitly a heuristic, not a comprehensive ML-based moderation system -- a proportionate first
layer. Applied to the incoming query (before spending an LLM call on it) and, as defense in depth,
to the outgoing answer in case retrieved content itself echoes something flagged.

A real moderation API (OpenAI's moderation endpoint, Perspective API, etc.) would be more
thorough, but is a new paid-dependency decision for the project owner to make explicitly, not
something to default into.
"""

import re

# Deliberately short and conservative: common slurs/explicit-abuse markers, not a broad profanity
# list that would flag normal safety/technical language (a false-positive-heavy filter is its own
# usability problem). \b-bounded so substrings of unrelated words don't match.
_FLAGGED_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bkill\s+yourself\b",
        r"\bhow to (?:make|build) a bomb\b",
        r"\bchild (?:sexual abuse|exploitation) material\b",
        r"\bhow to (?:synthesize|make) (?:meth|methamphetamine|fentanyl)\b",
    ]
]


def is_flagged(text: str) -> bool:
    return any(pattern.search(text) for pattern in _FLAGGED_PATTERNS)
