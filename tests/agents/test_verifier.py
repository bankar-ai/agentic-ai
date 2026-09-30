from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.models.test import TestModel

from app.agents.schemas import DraftAnswer, Evidence, VerificationResult
from app.agents.verifier import verify_answer

RETRIEVED = [Evidence(text="Paris is the capital of France.", source="knowledge_base", citation="geo.pdf")]


@pytest.mark.asyncio
async def test_verify_answer_grounded():
    draft = DraftAnswer(text="The capital of France is Paris [geo.pdf].", cited_evidence=RETRIEVED)
    model = TestModel(custom_output_args=VerificationResult(grounded=True, unsupported_claims=[], reasoning="matches source"))

    result = await verify_answer(model, draft, RETRIEVED)

    assert result.grounded is True


@pytest.mark.asyncio
async def test_verify_answer_with_no_cited_evidence_is_never_grounded():
    draft = DraftAnswer(text="I could not find enough evidence to answer this question.", cited_evidence=[])

    result = await verify_answer(model=None, draft=draft, evidence=RETRIEVED)

    assert result.grounded is False
    assert result.unsupported_claims == [draft.text]


@pytest.mark.asyncio
async def test_verify_answer_rejects_citation_not_in_retrieved_evidence_without_llm():
    """A Writer that invents a citation must not be checked against its own invention: the draft
    is rejected in code, before any model is consulted, even if the model would say grounded."""
    invented = Evidence(text="Paris has 40 million residents.", source="knowledge_base", citation="made-up.pdf")
    draft = DraftAnswer(text="Paris has 40 million residents [made-up.pdf].", cited_evidence=[invented])
    model = TestModel(custom_output_args=VerificationResult(grounded=True, unsupported_claims=[], reasoning="looks fine"))

    with patch("app.agents.verifier.Agent") as mock_agent_cls:
        result = await verify_answer(model, draft, RETRIEVED)

    assert result.grounded is False
    assert result.unsupported_claims == ["[knowledge_base] made-up.pdf"]
    mock_agent_cls.assert_not_called()


@pytest.mark.asyncio
async def test_verify_answer_rejects_web_evidence_relabeled_as_knowledge_base():
    retrieved = [Evidence(text="Sunny, 28C", source="web", citation="https://weather.example")]
    relabeled = Evidence(text="Sunny, 28C", source="knowledge_base", citation="https://weather.example")
    draft = DraftAnswer(text="It is sunny.", cited_evidence=[relabeled])

    result = await verify_answer(model=None, draft=draft, evidence=retrieved)

    assert result.grounded is False


@pytest.mark.asyncio
async def test_verify_answer_prompts_with_retrieved_evidence_not_writer_copy():
    """The LLM check sees the real retrieved text, not the (possibly altered) text the Writer cited."""
    writer_copy = Evidence(text="Paris is the capital of Germany.", source="knowledge_base", citation="geo.pdf")
    draft = DraftAnswer(text="Paris is the capital of Germany [geo.pdf].", cited_evidence=[writer_copy])
    fake_agent = MagicMock()
    captured: list[str] = []

    async def fake_run(prompt: str) -> MagicMock:
        captured.append(prompt)
        return MagicMock(output=VerificationResult(grounded=False, unsupported_claims=["Germany"], reasoning="x"))

    fake_agent.run = fake_run
    with patch("app.agents.verifier.Agent", return_value=fake_agent):
        await verify_answer(MagicMock(), draft, RETRIEVED)

    assert "Paris is the capital of France." in captured[0]
    assert "capital of Germany." not in captured[0].split("Retrieved evidence:")[1]
