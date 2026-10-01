"""Research agent: gathers evidence for the route the Gatekeeper chose.

For the "kb" route, this connects to the MCP tool server (Task 4) as an MCP client and calls its
`search_knowledge_base` tool -- a real MCP round-trip, not a direct Python function call. For
"web_fallback", it uses the plain web search tool (Task 7) directly, since that fallback is this
project's own capability, not something exposed over MCP. "refuse" does no research at all.

Groundedness note: the KB route builds `Evidence` objects in code from the MCP tool's structured
result -- no LLM sits between retrieval and evidence. The Gatekeeper has already chosen the route
and the search parameters, so there is nothing left for a model to decide here, and letting one
re-author the results would let it paraphrase, invent, or mislabel evidence (including the
`source` label, which must always be "knowledge_base" on this route).

API note (verified against the installed `pydantic-ai-slim` 2.52.0 / `fastmcp` 4.0.10 / `mcp`
2.2.0): `pydantic_ai.mcp.StdioTransport` is FastMCP's stdio transport, accepting
`command, args, env, cwd`. `MCPToolset(transport).direct_call_tool(name, args)` opens the session,
calls the tool, and returns the tool's raw return value (the `list[dict]` unwrapped from MCP's
`{"result": ...}` structured-content envelope) without going through an `Agent`.

Subprocess environment: the `mcp` SDK launches the child with
`get_default_environment() | (env or {})`, where `get_default_environment()` is a small OS-level
allow-list (PATH, TEMP, USERPROFILE, ...) that excludes `RAG_PLATFORM_*`. So credentials exported
only as environment variables must be forwarded explicitly, or the child's `Settings()` fails.
"""

import os
from pathlib import Path

from pydantic_ai.mcp import MCPToolset, StdioTransport

from app.agents.schemas import Evidence, GatekeeperDecision, ResearchResult, UserSession
from app.agents.web_search import search_web

_KB_TOOL_NAME = "search_knowledge_base"
_FORWARDED_ENV_PREFIXES = ("RAG_PLATFORM_",)
# app/agents/research.py -> repo root, so the child resolves `app.*` and finds `.env` regardless
# of the parent process's working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class KnowledgeBaseToolError(RuntimeError):
    """The MCP knowledge-base tool returned something other than a list of result chunks."""


def _mcp_subprocess_env(user_session: UserSession | None = None) -> dict[str, str]:
    """Environment variables to forward to the MCP server subprocess, on top of the MCP SDK's
    default allow-list: every `RAG_PLATFORM_*` credential/config the server's `Settings` needs.

    AGT-013: when `user_session` is supplied (a logged-in end user, not the fixed service
    account), it's forwarded as `RAG_PLATFORM_ACCESS_TOKEN`/`RAG_PLATFORM_CSRF_TOKEN`, overriding
    the parent process's own forwarded email/password for just this one subprocess call -- the
    subprocess then retrieves as that user, not the service account (see
    `app/mcp_server/server.py`'s `_build_auth`).
    """
    env = {key: value for key, value in os.environ.items() if key.upper().startswith(_FORWARDED_ENV_PREFIXES)}
    if user_session:
        env["RAG_PLATFORM_ACCESS_TOKEN"] = user_session.access_token
        env["RAG_PLATFORM_CSRF_TOKEN"] = user_session.csrf_token
    return env


async def _research_kb(
    mcp_server_command: list[str], decision: GatekeeperDecision, query: str, user_session: UserSession | None = None
) -> list[Evidence]:
    transport = StdioTransport(
        command=mcp_server_command[0],
        args=mcp_server_command[1:],
        env=_mcp_subprocess_env(user_session),
        cwd=str(_REPO_ROOT),
    )
    # tool_error_behavior="error": outside an Agent run there is no model to retry, so a
    # server-side failure (e.g. the RAG platform being down) must raise, not become a ModelRetry.
    mcp_toolset = MCPToolset(transport, tool_error_behavior="error")
    raw = await mcp_toolset.direct_call_tool(
        _KB_TOOL_NAME, {"query": query, "top_k": decision.top_k, "rerank": decision.rerank}
    )
    if not isinstance(raw, list):
        raise KnowledgeBaseToolError(f"{_KB_TOOL_NAME} returned {type(raw).__name__}, expected a list of chunks")
    return [Evidence(text=chunk["text"], source="knowledge_base", citation=chunk["source_filename"]) for chunk in raw]


async def research(
    mcp_server_command: list[str], decision: GatekeeperDecision, query: str, user_session: UserSession | None = None
) -> ResearchResult:
    """Gather evidence according to the Gatekeeper's chosen route.

    `user_session` (AGT-013): the logged-in end user's RAG-platform session, if any -- only
    relevant to the "kb" route, which is the only one that calls the RAG platform.
    """
    if decision.route == "refuse":
        return ResearchResult(evidence=[])
    if decision.route == "web_fallback":
        evidence = await search_web(query)
        return ResearchResult(evidence=evidence)
    evidence = await _research_kb(mcp_server_command, decision, query, user_session)
    return ResearchResult(evidence=evidence)
