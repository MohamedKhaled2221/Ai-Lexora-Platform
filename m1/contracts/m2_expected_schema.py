from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Language = Literal["ar", "en", "ar-en", "unknown"]

# Mirrors M1's DocumentType enum values exactly (src/document_chunk_schema.py:46-81).
DocumentType = Literal[
    "contract",
    "law",
    "court_ruling",
    "pleading",
    "power_of_attorney",
    "correspondence",
    "unknown",
]


class DocumentChunk(BaseModel):
    """Input contract received from M1.
    ...
    """

    model_config = ConfigDict(extra="forbid")  # <-- ADDED

    document_id: str
    chunk_id: str
    text: str = Field(min_length=1)
    page: int = Field(ge=1)
    section: str | None = None
    clause: str | None = None
    language: Language = "unknown"
    document_type: DocumentType = "unknown"  # <-- CHANGED from str | None
    metadata: dict = Field(default_factory=dict)


class IdentifierSet(BaseModel):
    """Legal identifiers preserved during query processing."""

    article_numbers: list[str] = Field(default_factory=list)
    case_numbers: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    monetary_values: list[str] = Field(default_factory=list)
    party_names: list[str] = Field(default_factory=list)


class ProcessedQuery(BaseModel):
    """Normalized query contract handed from M2 to M3.

    The object preserves the original query and exposes the processed
    representation without destroying legal identifiers.
    """

    original_text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    language: Language
    query_variants: list[str] = Field(default_factory=list)
    identifiers: IdentifierSet = Field(default_factory=IdentifierSet)


class EmbeddedText(BaseModel):
    """Embedding result for one text item."""

    text_id: str
    embedding: list[float]
    model: str
    dimension: int


class EmbeddedDocumentChunk(BaseModel):
    """M2 output for a document chunk."""

    document_id: str
    chunk_id: str
    embedding: list[float]
    model: str
    dimension: int


class EmbeddedQuery(BaseModel):
    """M2 output for a processed user query."""

    processed_query: ProcessedQuery
    embedding: list[float]
    model: str
    dimension: int
