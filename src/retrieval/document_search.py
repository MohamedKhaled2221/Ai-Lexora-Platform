"""
Turn ranked chunks into a ranked list of documents.

Used by ``POST /api/v1/rag/search``: a search page lists documents, not
chunks, so each document appears once, ranked by its best chunk, with that
chunk as the snippet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

SNIPPET_MAX_CHARS = 300


@dataclass(frozen=True)
class DocumentSearchHit:
    document_id: str
    score: float
    snippet: str
    chunk_id: str
    page: Optional[int]
    section: Optional[str]
    matched_chunks: int


def make_snippet(text: str, max_chars: int = SNIPPET_MAX_CHARS) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0] or text[:max_chars]
    return cut + " …"


def group_by_document(chunks: Iterable[dict[str, Any]]) -> list[DocumentSearchHit]:
    """
    One hit per document, ordered by best chunk score (highest first).

    ``chunks`` must already be ranked; within a document the first chunk seen
    wins ties, so the retrieval order decides the snippet.
    """
    best: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}

    for chunk in chunks:
        document_id = chunk.get("document_id")
        if not document_id:
            continue
        counts[document_id] = counts.get(document_id, 0) + 1
        score = float(chunk.get("score", 0.0))
        current = best.get(document_id)
        if current is None or score > float(current.get("score", 0.0)):
            best[document_id] = chunk

    hits = [
        DocumentSearchHit(
            document_id=document_id,
            score=round(float(chunk.get("score", 0.0)), 6),
            snippet=make_snippet(chunk.get("text", "")),
            chunk_id=str(chunk.get("chunk_id", "")),
            page=chunk.get("page"),
            section=chunk.get("section"),
            matched_chunks=counts[document_id],
        )
        for document_id, chunk in best.items()
    ]
    # Stable sort: equal scores keep retrieval order.
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits
