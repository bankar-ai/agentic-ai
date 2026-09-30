"""A small, synthetic fixture knowledge base for integration tests -- not real ingested
documents. Mirrors `enterprise-rag-platform`'s `RetrievedChunk` shape exactly.
"""

from app.rag_client.schemas import RetrievedChunk

SAMPLE_KB_CHUNKS = [
    RetrievedChunk(
        chunk_id="c1", document_id="d1", text="Paris is the capital of France.",
        section_path=["Geography", "Europe"], page_start=1, page_end=1,
        source_filename="world-facts.pdf", score=0.95,
    ),
    RetrievedChunk(
        chunk_id="c2", document_id="d1", text="France's population was approximately 68 million in 2023.",
        section_path=["Geography", "Europe"], page_start=2, page_end=2,
        source_filename="world-facts.pdf", score=0.81,
    ),
]
