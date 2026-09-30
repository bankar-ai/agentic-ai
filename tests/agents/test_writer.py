import pytest
from pydantic_ai.models.test import TestModel

from app.agents.schemas import DraftAnswer, Evidence
from app.agents.writer import write_answer


@pytest.mark.asyncio
async def test_write_answer_synthesizes_from_evidence():
    evidence = [Evidence(text="Paris is the capital of France.", source="knowledge_base", citation="geo.pdf")]
    model = TestModel(custom_output_args=DraftAnswer(
        text="The capital of France is Paris [geo.pdf].", cited_evidence=evidence,
    ))

    draft = await write_answer(model, "What is the capital of France?", evidence)

    assert isinstance(draft, DraftAnswer)
    assert "Paris" in draft.text


@pytest.mark.asyncio
async def test_write_answer_with_no_evidence_does_not_call_model():
    draft = await write_answer(model=None, query="anything", evidence=[])

    assert draft.cited_evidence == []
    assert "could not" in draft.text.lower()
