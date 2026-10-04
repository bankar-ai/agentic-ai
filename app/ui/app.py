"""Two-tab Gradio demo: Direct RAG (single retrieval pass, no correction) side by side with
Agentic RAG (the full Gatekeeper->Research->Writer->Verifier trace, filled in live as each agent
finishes, AGT-008), so the value of the correction loop is shown, not just explained. The Agentic
tab runs the graph in-process via `get_graph()` rather than calling the SSE endpoint. Not a
production UI.

AGT-014/AGT-006: a login row lets a visitor authenticate directly against
`enterprise-rag-platform` (this UI never sees or stores a password beyond that one call) and see
their own documents in both tabs, via AGT-013's per-request token support. Logging in is required
-- there is no anonymous/demo-account fallback, so both tabs refuse to query until a session
exists.
"""

import gradio as gr
import httpx

from app.agents.direct_query import run_direct_query as _run_direct_query
from app.agents.schemas import GraphState, UserSession
from app.api.router import get_graph
from app.core.config import get_settings
from app.rag_client.auth import (
    RagPlatformAuthError,
    StaticTokenAuth,
    login_and_extract_session,
)
from app.rag_client.retrieval import RagPlatformRetrievalClient
from app.rag_client.shared_client import get_shared_rag_platform_client

_LOGIN_REQUIRED_MESSAGE = "Please log in with your enterprise-rag-platform account above to use this demo."


def _get_retrieval_client(user_session: UserSession) -> RagPlatformRetrievalClient:
    settings = get_settings()
    # AGT-009: one client reused across every query in this process, not a fresh one per call.
    http_client = get_shared_rag_platform_client()
    auth = StaticTokenAuth(user_session.access_token, user_session.csrf_token)
    return RagPlatformRetrievalClient(settings.rag_platform_base_url, auth, http_client)


async def login(email: str, password: str) -> tuple[UserSession | None, str]:
    """Log in directly against `enterprise-rag-platform`'s own `/auth/login` -- this UI never
    stores the password past this one call, only the resulting session (held in `gr.State`,
    per-browser-session, never written to disk).
    """
    if not email or not password:
        return None, "Enter both email and password."
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.rag_platform_base_url, timeout=30.0) as http_client:
        try:
            access_token, csrf_token = await login_and_extract_session(
                settings.rag_platform_base_url, email, password, http_client
            )
        except RagPlatformAuthError:
            return None, "Login failed -- check your email and password."
    return UserSession(access_token=access_token, csrf_token=csrf_token), f"Logged in as {email}. Both tabs now use your own documents."


async def run_direct_query(query: str, user_session: UserSession | None = None) -> str:
    """Direct-RAG tab: one retrieval pass, top chunk's text returned as-is, no synthesis.

    AGT-034: the actual retrieval logic now lives in `app.agents.direct_query`, shared with the
    live `/query/direct` endpoint -- this wraps it with Gradio's own login/formatting concerns.
    """
    if user_session is None:
        return _LOGIN_REQUIRED_MESSAGE
    client = _get_retrieval_client(user_session)
    try:
        result = await _run_direct_query(client, query)
    except Exception as exc:
        if isinstance(exc, RagPlatformAuthError) or "401" in str(exc):
            return "Your session has expired -- please log in again."
        raise
    if result.text is None:
        return "No matching results found in the knowledge base."
    return f"{result.text}\n\n(source: {result.source_filename})"


async def run_agentic_query(query: str, user_session: UserSession | None = None):
    """Agentic-RAG tab: run the full graph, yielding the trace and answer progressively as each
    agent actually finishes (AGT-008) -- an async generator, which Gradio streams to the output
    components on every `yield` rather than waiting for one final return value.
    """
    if user_session is None:
        yield "", _LOGIN_REQUIRED_MESSAGE
        return
    graph = get_graph(user_session)
    initial_state: GraphState = {
        "query": query, "user_session": user_session, "gatekeeper_decision": None, "evidence": [],
        "draft": None, "verification": None, "retry_count": 0, "final_answer": None, "refused": False,
        "trace": [],
    }
    final_state = initial_state
    trace_lines: list[str] = []
    async for chunk in graph.astream(initial_state, stream_mode="updates"):
        for node_state in chunk.values():
            final_state = node_state
            step = node_state["trace"][-1]
            trace_lines.append(f"{step.get('agent', '?')}: {step}")
            yield "\n".join(trace_lines), "(thinking...)"
    answer_text = final_state["final_answer"] or "The system could not produce a grounded answer and refused to guess."
    yield "\n".join(trace_lines), answer_text


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Agentic RAG Orchestration") as demo:
        user_session_state = gr.State(value=None)

        with gr.Accordion("Log in (required -- there is no demo account, bring your own enterprise-rag-platform login)", open=True):
            with gr.Row():
                login_email = gr.Textbox(label="Email")
                login_password = gr.Textbox(label="Password", type="password")
            login_button = gr.Button("Log in")
            login_status = gr.Textbox(label="Status", interactive=False)
            login_button.click(login, inputs=[login_email, login_password], outputs=[user_session_state, login_status])

        with gr.Tab("Direct RAG"):
            direct_input = gr.Textbox(label="Question")
            direct_output = gr.Textbox(label="Answer (single retrieval pass, no correction)")
            direct_input.submit(run_direct_query, inputs=[direct_input, user_session_state], outputs=direct_output)

        with gr.Tab("Agentic RAG"):
            agentic_input = gr.Textbox(label="Question")
            trace_output = gr.Textbox(label="Agent trace", lines=10)
            answer_output = gr.Textbox(label="Final answer")
            agentic_input.submit(
                run_agentic_query, inputs=[agentic_input, user_session_state], outputs=[trace_output, answer_output]
            )

    return demo


if __name__ == "__main__":
    build_ui().launch()
