from typing import List, Optional
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    """
    Single retrieved passage chunk evidence item passed to M4.
    """
    document_id: str = Field(..., description="Source legal document ID")
    chunk_id: str = Field(..., description="Unique chunk ID within the document")
    text: str = Field(..., description="Extracted legal snippet text")
    page: Optional[int] = Field(default=None, description="Page number for citation validation in M4")
    section: Optional[str] = Field(default=None, description="Document section or article title")
    language: str = Field(default="ar", description="Language of chunk text")
    score: float = Field(..., description="Final reranked relevance score [0.0 - 1.0]")


class RetrievedEvidence(BaseModel):
    """
    Downstream Interface Contract (M3 -> M4).
    Output delivered by M3 (Retrieval Engineer) to M4 (LLM Orchestration Engine).
    """
    query_id: str = Field(..., description="Query ID corresponding to M2 ProcessedQuery")
    retrieved_evidence: List[EvidenceItem] = Field(
        default_factory=list,
        description="Top-K reranked evidence chunks ordered by relevance score descending"
    )
