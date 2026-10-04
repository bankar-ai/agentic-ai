"""Direct RAG: one retrieval pass, top chunk's text returned as-is, no synthesis (AGT-034).

Shared between the local Gradio demo (`app/ui/app.py`) and the live `/query/direct` endpoint --
this is the baseline the full Gatekeeper->Research->Writer->Verifier pipeline is compared against,
so both surfaces must run the exact same logic, not two copies that could drift apart.
"""

from pydantic import BaseModel

from app.rag_client.retrieval import RagPlatformRetrievalClient


class DirectQueryResult(BaseModel):
    """The single top-ranked chunk, or `None` if nothing matched -- never synthesized, so there's
    nothing here to verify or cite beyond the chunk's own source file.

    `duration_seconds` (AGT-036) is left unset by `run_direct_query` itself -- the Gradio demo has
    no use for it, so only `POST /query/direct` populates it, after this result comes back.
    """

    text: str | None
    source_filename: str | None
    duration_seconds: float | None = None


async def run_direct_query(client: RagPlatformRetrievalClient, query: str) -> DirectQueryResult:
    """Run one retrieval pass and return the top chunk verbatim, or an empty result."""
    result = await client.search(query, top_k=1)
    if not result.results:
        return DirectQueryResult(text=None, source_filename=None)
    top = result.results[0]
    return DirectQueryResult(text=top.text, source_filename=top.source_filename)
