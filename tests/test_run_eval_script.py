"""Unit tests for the pure, deterministic pieces of scripts/run_eval.py (AGT-011) -- the
evaluator functions and the fixture KB lookup. Does not run the eval set itself (that needs a
real LLM provider configured; this just checks the scoring logic is correct)."""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_eval.py"
_spec = importlib.util.spec_from_file_location("run_eval", _SCRIPT_PATH)
run_eval = importlib.util.module_from_spec(_spec)
sys.modules["run_eval"] = run_eval
_spec.loader.exec_module(run_eval)


def test_refusal_evaluator_passes_when_refused_matches_expected():
    result = run_eval._refusal_evaluator(
        output={"refused": True, "final_answer": None}, expected_output={"refused": True}
    )
    assert result.value is True


def test_refusal_evaluator_fails_when_refused_does_not_match_expected():
    result = run_eval._refusal_evaluator(
        output={"refused": False, "final_answer": "an answer"}, expected_output={"refused": True}
    )
    assert result.value is False


def test_groundedness_evaluator_passes_when_answer_contains_expected_text():
    result = run_eval._groundedness_evaluator(
        output={"final_answer": "The capital of France is Paris.", "refused": False},
        expected_output={"answer_contains": "paris"},
    )
    assert result.value is True


def test_groundedness_evaluator_fails_when_answer_missing_expected_text():
    result = run_eval._groundedness_evaluator(
        output={"final_answer": "I could not find enough evidence.", "refused": True},
        expected_output={"answer_contains": "paris"},
    )
    assert result.value is False


def test_groundedness_evaluator_passes_with_no_expectation_set():
    result = run_eval._groundedness_evaluator(
        output={"final_answer": None, "refused": True}, expected_output={"refused": True}
    )
    assert result.value is True


@pytest.mark.asyncio
async def test_fixture_retrieval_client_hits_kb_for_known_topic():
    result = await run_eval._FixtureRetrievalClient().search("What is the capital of France?")

    assert len(result.results) > 0
    assert result.results[0].source_filename == "world-facts.pdf"


@pytest.mark.asyncio
async def test_fixture_retrieval_client_misses_for_unrelated_topic():
    result = await run_eval._FixtureRetrievalClient().search("What is the capital of Japan?")

    assert result.results == []
