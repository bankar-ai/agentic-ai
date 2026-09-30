"""Two-tab Gradio demo: Direct RAG (single retrieval pass, no correction) side by side with
Agentic RAG (the full Gatekeeper->Research->Writer->Verifier trace, streamed live), so the
value of the correction loop is shown, not just explained. Not a production UI.
"""

import gradio as gr
import httpx

from app.agents.schemas import GraphState
from app.api.router import get_graph
from app.core.config import get_settings
from app.rag_client.auth import RagPlatformAuth
from app.rag_client.retrieval import RagPlatformRetrievalClient


def _get_retrieval_client() -> RagPlatformRetrievalClient:
    settings = get_settings()
    http_client = httpx.AsyncClient(base_url=settings.rag_platform_base_url, timeout=30.0)
    auth = RagPlatformAuth(settings.rag_platform_base_url, settings.rag_platform_email, settings.rag_platform_password, http_client)
    return RagPlatformRetrievalClient(settings.rag_platform_base_url, auth, http_client)


async def run_direct_query(query: str) -> str:
    """Direct-RAG tab: one retrieval pass, top chunk's text returned as-is, no synthesis."""
    client = _get_retrieval_client()
    result = await client.search(query, top_k=1)
    if not result.results:
        return "No matching results found in the knowledge base."
    top = result.results[0]
    return f"{top.text}\n\n(source: {top.source_filename})"


async def run_agentic_query(query: str) -> tuple[str, str]:
    """Agentic-RAG tab: run the full graph, render the trace and the final (possibly refused) answer."""
    graph = get_graph()
    initial_state: GraphState = {
        "query": query, "gatekeeper_decision": None, "evidence": [], "draft": None,
        "verification": None, "retry_count": 0, "final_answer": None, "refused": False, "trace": [],
    }
    final_state = await graph.ainvoke(initial_state)
    trace_lines = [f"{step.get('agent', '?')}: {step}" for step in final_state["trace"]]
    trace_text = "\n".join(trace_lines)
    answer_text = final_state["final_answer"] or "The system could not produce a grounded answer and refused to guess."
    return trace_text, answer_text


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Agentic RAG Orchestration") as demo:
        with gr.Tab("Direct RAG"):
            direct_input = gr.Textbox(label="Question")
            direct_output = gr.Textbox(label="Answer (single retrieval pass, no correction)")
            direct_input.submit(run_direct_query, inputs=direct_input, outputs=direct_output)

        with gr.Tab("Agentic RAG"):
            agentic_input = gr.Textbox(label="Question")
            trace_output = gr.Textbox(label="Agent trace", lines=10)
            answer_output = gr.Textbox(label="Final answer")
            agentic_input.submit(run_agentic_query, inputs=agentic_input, outputs=[trace_output, answer_output])

    return demo


if __name__ == "__main__":
    build_ui().launch()
