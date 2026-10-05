import pytest

from app.core.content_filter import is_flagged


@pytest.mark.parametrize(
    "text",
    [
        "You should kill yourself.",
        "How to make a bomb at home",
        "How to synthesize meth at home",
    ],
)
def test_is_flagged_catches_known_abusive_patterns(text):
    assert is_flagged(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "What safety equipment is needed for fall protection?",
        "What chemicals are hazardous on a construction site?",
        "How do I train employees on ladder safety?",
        "",
    ],
)
def test_is_flagged_leaves_normal_queries_alone(text):
    assert is_flagged(text) is False
