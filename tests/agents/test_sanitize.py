from app.agents.sanitize import sanitize_evidence_text


def test_strips_html_tags():
    assert sanitize_evidence_text("<b>Paris</b> is the capital") == "Paris is the capital"


def test_strips_control_characters():
    assert sanitize_evidence_text("Paris\x00 is\x07 the capital") == "Paris is the capital"


def test_strips_invisible_and_bidi_characters():
    # Built from chr() rather than literal characters so this test file itself stays free of
    # them -- same reasoning as sanitize.py's own _INVISIBLE_CHARS construction.
    text = f"Pa{chr(0x200b)}ris is{chr(0x202e)} the capital"
    assert sanitize_evidence_text(text) == "Paris is the capital"


def test_unescapes_html_entities_then_still_strips_tags():
    assert sanitize_evidence_text("Paris &amp; France") == "Paris & France"


def test_collapses_whitespace():
    assert sanitize_evidence_text("Paris   is\n\nthe   capital") == "Paris is the capital"


def test_truncates_overly_long_text():
    text = "a" * 5000
    result = sanitize_evidence_text(text)
    assert len(result) == 4000


def test_leaves_ordinary_text_unchanged():
    assert sanitize_evidence_text("Paris is the capital of France.") == "Paris is the capital of France."
