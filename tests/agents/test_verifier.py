import pytest
from pydantic_ai.models.test import TestModel

from app.agents.schemas import DraftAnswer, Evidence, VerificationResult
from app.agents.verifier import verify_answer


@pytest.mark.asyncio
async def test_verify_answer_grounded():
    evidence = [Evidence(text="Paris is the capital of France.", source="knowledge_base", citation="geo.pdf")]
    draft = DraftAnswer(text="The capital of France is Paris [geo.pdf].", cited_evidence=evidence)
    model = TestModel(custom_output_args=VerificationResult(grounded=True, unsupported_claims=[], reasoning="matches source"))

    result = await verify_answer(model, draft)

    assert result.grounded is True


@pytest.mark.asyncio
async def test_verify_answer_with_no_cited_evidence_is_never_grounded():
    draft = DraftAnswer(text="I could not find enough evidence to answer this question.", cited_evidence=[])

    result = await verify_answer(model=None, draft=draft)

    assert result.grounded is False
    assert result.unsupported_claims == [draft.text]
