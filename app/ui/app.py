"""Two-tab Gradio demo: Direct RAG (single retrieval pass, no correction) side by side with
Agentic RAG (the full Gatekeeper->Research->Writer->Verifier trace, shown once the graph has
finished -- not streamed step by step), so the value of the correction loop is shown, not just
explained. The Agentic tab runs the graph in-process via `get_graph()` rather than calling the
SSE endpoint. Not a production UI.

AGT-014/AGT-006: a login row lets a visitor authenticate directly against
`enterprise-rag-platform` (this UI never sees or stores a password beyond that one call) and see
their own documents in both tabs, via AGT-013's per-request token support. Logging in is required
-- there is no anonymous/demo-account fallback, so both tabs refuse to query until a session
exists.
"""

import gradio as gr
import httpx

from app.agents.schemas import GraphState, UserSession
from app.api.router import get_graph
from app.core.config import get_settings
from app.rag_client.auth import RagPlatformAuth, RagPlatformAuthError, StaticTokenAuth
from app.rag_client.retrieval import RagPlatformRetrievalClient

_LOGIN_REQUIRED_MESSAGE = "Please log in with your enterprise-rag-platform account above to use this demo."


def _get_retrieval_client(user_session: UserSession) -> RagPlatformRetrievalClient:
    settings = get_settings()
    http_client = httpx.AsyncClient(base_url=settings.rag_platform_base_url, timeout=30.0)
    auth = StaticTokenAuth(user_session.access_token, user_session.csrf_token, http_client, settings.rag_platform_base_url)
    return RagPlatformRetrievalClient(settings.rag_platform_base_url, auth, http_client)


async def login(email: str, password: str) -> tuple[UserSession | None, str]:
    """Log in directly against `enterprise-rag-platform`'s own `/auth/login` -- this UI never
    stores the password past this one call, only the resulting session (held in `gr.State`,
    per-browser-session, never written to disk). The access token is read back out of this one-off
    client's cookie jar (where the platform's `Set-Cookie` landed it) since every later query
    starts a fresh http client and must re-inject it itself via `StaticTokenAuth`.
    """
    if not email or not password:
        return None, "Enter both email and password."
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.rag_platform_base_url, timeout=30.0) as http_client:
        auth = RagPlatformAuth(settings.rag_platform_base_url, email, password, http_client)
        try:
            csrf_token = await auth.get_csrf_token()
        except RagPlatformAuthError:
            return None, "Login failed -- check your email and password."
        access_token = http_client.cookies.get("access_token")
    if not access_token:
        return None, "Login succeeded but no session cookie was issued -- please try again."
    return UserSession(access_token=access_token, csrf_token=csrf_token), f"Logged in as {email}. Both tabs now use your own documents."


async def run_direct_query(query: str, user_session: UserSession | None = None) -> str:
    """Direct-RAG tab: one retrieval pass, top chunk's text returned as-is, no synthesis."""
    if user_session is None:
        return _LOGIN_REQUIRED_MESSAGE
    client = _get_retrieval_client(user_session)
    try:
        result = await client.search(query, top_k=1)
    except Exception as exc:
        if isinstance(exc, RagPlatformAuthError) or "401" in str(exc):
            return "Your session has expired -- please log in again."
        raise
    if not result.results:
        return "No matching results found in the knowledge base."
    top = result.results[0]
    return f"{top.text}\n\n(source: {top.source_filename})"


async def run_agentic_query(query: str, user_session: UserSession | None = None) -> tuple[str, str]:
    """Agentic-RAG tab: run the full graph, render the trace and the final (possibly refused) answer."""
    if user_session is None:
        return "", _LOGIN_REQUIRED_MESSAGE
    graph = get_graph(user_session)
    initial_state: GraphState = {
        "query": query, "user_session": user_session, "gatekeeper_decision": None, "evidence": [],
        "draft": None, "verification": None, "retry_count": 0, "final_answer": None, "refused": False,
        "trace": [],
    }
    final_state = await graph.ainvoke(initial_state)
    trace_lines = [f"{step.get('agent', '?')}: {step}" for step in final_state["trace"]]
    trace_text = "\n".join(trace_lines)
    answer_text = final_state["final_answer"] or "The system could not produce a grounded answer and refused to guess."
    return trace_text, answer_text


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
