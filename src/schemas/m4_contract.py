from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


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

class M4ModelOutput(BaseModel):
    """
    Raw structured output produced by the local LLM.

    The LLM is allowed to reference evidence only through trusted aliases
    such as E1, E2, E3. It must never generate document IDs, chunk IDs,
    page numbers, or section metadata directly.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    answer: str = Field(
        ...,
        min_length=1,
        description="Grounded natural-language answer generated from retrieved evidence",
    )

    citation_ids: List[str] = Field(
        default_factory=list,
        description="Evidence aliases cited by the model, for example E1 or E2",
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence score between 0.0 and 1.0",
    )

    @field_validator("citation_ids")
    @classmethod
    def validate_citation_ids(cls, citation_ids: List[str]) -> List[str]:
        seen = set()

        for citation_id in citation_ids:
            if (
                not citation_id.startswith("E")
                or not citation_id[1:].isdigit()
                or citation_id[1:].startswith("0")
            ):
                raise ValueError(
                    "Citation IDs must use the format E1, E2, E3, ..."
                )

            if citation_id in seen:
                raise ValueError(
                    f"Duplicate citation ID: {citation_id}"
                )

            seen.add(citation_id)

        return citation_ids

class Citation(BaseModel):
    """
    Validated citation returned to the application.

    Citation metadata is resolved by Python from RetrievedEvidence.
    It is never trusted directly from LLM output.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    evidence_id: str = Field(
        ...,
        pattern=r"^E[1-9][0-9]*$",
        description="Evidence alias exposed to the LLM, for example E1",
    )

    document_id: str = Field(
        ...,
        min_length=1,
        description="Trusted source document ID",
    )

    chunk_id: str = Field(
        ...,
        min_length=1,
        description="Trusted source chunk ID",
    )

    page: Optional[int] = Field(
        default=None,
        description="Trusted source page number",
    )

    section: Optional[str] = Field(
        default=None,
        description="Trusted source section or article title",
    )

class AIResponse(BaseModel):
    """
    Final validated output returned by the M4 orchestration layer.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    query_id: str = Field(
        ...,
        min_length=1,
        description="Query identifier propagated from the upstream pipeline",
    )

    answer: str = Field(
        ...,
        min_length=1,
        description="Final grounded answer",
    )

    citations: List[Citation] = Field(
        default_factory=list,
        description="Trusted citations resolved from retrieved evidence",
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Final response confidence score",
    )

    @field_validator("citations")
    @classmethod
    def validate_unique_citations(
        cls,
        citations: List[Citation],
    ) -> List[Citation]:
        evidence_ids = [citation.evidence_id for citation in citations]

        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError(
                "AIResponse cannot contain duplicate evidence citations"
            )

        return citations
