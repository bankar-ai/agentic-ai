"""Research agent: gathers evidence for the route the Gatekeeper chose.

For the "kb" route, this connects to the MCP tool server (Task 4) as an MCP client and calls its
`search_knowledge_base` tool -- a real MCP round-trip, not a direct Python function call. For
"web_fallback", it uses the plain web search tool (Task 7) directly, since that fallback is this
project's own capability, not something exposed over MCP. "refuse" does no research at all.

API note: the task plan's original sketch used `pydantic_ai.mcp.MCPServerStdio` and
`Agent(..., toolsets=[MCPServerStdio(...)])`. The installed `pydantic-ai-slim` (2.52.0) has no
`MCPServerStdio` -- its MCP client layer was rebuilt on top of FastMCP. The verified equivalents
are `pydantic_ai.mcp.StdioTransport(command, args)` (a FastMCP stdio transport describing the
subprocess to launch) wrapped in `pydantic_ai.mcp.MCPToolset(transport)`, passed to
`Agent(..., toolsets=[...])` exactly as the plan intended. `Agent` supporting `async with` and
`toolsets=` both verified against the installed version.
"""

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset, StdioTransport
from pydantic_ai.models import Model

from app.agents.schemas import Evidence, GatekeeperDecision, ResearchResult
from app.agents.web_search import search_web

_SYSTEM_PROMPT = """You are the Research agent. You have access to a `search_knowledge_base` tool.
Given the user's question and the requested top_k/rerank settings, call the tool, then return
every relevant result as evidence with its `source_filename` as the citation."""


async def _research_kb(model: Model, mcp_server_command: list[str], decision: GatekeeperDecision, query: str) -> list[Evidence]:
    transport = StdioTransport(command=mcp_server_command[0], args=mcp_server_command[1:])
    mcp_toolset = MCPToolset(transport)
    agent = Agent(model, toolsets=[mcp_toolset], output_type=list[Evidence], system_prompt=_SYSTEM_PROMPT)
    async with agent:
        prompt = f"Question: {query}\nUse top_k={decision.top_k}, rerank={decision.rerank}."
        result = await agent.run(prompt)
    return result.output


async def research(
    model: Model | None, mcp_server_command: list[str], decision: GatekeeperDecision, query: str
) -> ResearchResult:
    """Gather evidence according to the Gatekeeper's chosen route."""
    if decision.route == "refuse":
        return ResearchResult(evidence=[])
    if decision.route == "web_fallback":
        evidence = await search_web(query)
        return ResearchResult(evidence=evidence)
    evidence = await _research_kb(model, mcp_server_command, decision, query)
    return ResearchResult(evidence=evidence)
