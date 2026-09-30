from unittest.mock import AsyncMock, patch

import gradio as gr
import pytest

from app.ui.app import build_ui, run_agentic_query, run_direct_query


def test_build_ui_returns_blocks_with_two_tabs():
    demo = build_ui()

    assert isinstance(demo, gr.Blocks)


@pytest.mark.asyncio
async def test_run_direct_query_returns_plain_answer_text():
    fake_client = AsyncMock()
    fake_client.search.return_value = AsyncMock(
        results=[AsyncMock(text="Paris is the capital of France.", source_filename="world-facts.pdf")]
    )

    with patch("app.ui.app._get_retrieval_client", return_value=fake_client):
        answer = await run_direct_query("What is the capital of France?")

    assert "Paris" in answer


@pytest.mark.asyncio
async def test_run_agentic_query_returns_trace_and_answer():
    fake_state = {
        "final_answer": "Paris [world-facts.pdf]", "refused": False,
        "trace": [{"agent": "gatekeeper", "route": "kb", "reasoning": "ok"}],
    }
    fake_graph = AsyncMock()
    fake_graph.ainvoke.return_value = fake_state

    with patch("app.ui.app.get_graph", return_value=fake_graph):
        trace_text, answer_text = await run_agentic_query("What is the capital of France?")

    assert "gatekeeper" in trace_text
    assert "Paris" in answer_text
