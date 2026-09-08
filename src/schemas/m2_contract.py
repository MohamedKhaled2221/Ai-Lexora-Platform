from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from .m1_contract import DocumentType, Language


_MIXED_LANGUAGE_ALIASES = {
    "mixed",
    "en-ar",
    "arabic-english",
    "english-arabic",
}


def _normalize_language_value(
    value: Any,
) -> Any:
    """
    Normalize legacy language labels to the canonical M2 values.

    M2 emits:
    - ar
    - en
    - ar-en
    - unknown

    Older callers using "mixed" remain compatible.
    """
    if value is None or not isinstance(value, str):
        return value

    normalized = value.strip().lower()

    if normalized in _MIXED_LANGUAGE_ALIASES:
        return "ar-en"

    return normalized


class QueryFilters(BaseModel):
    """
    Metadata filtering parameters passed from M2 to M3.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    document_type: str | None = Field(
        default=None,
        description=(
            "Legal document type filter understood "
            "by the retrieval layer"
        ),
    )

    jurisdiction: str | None = Field(
        default=None,
        description=(
            "Legal jurisdiction, for example "
            "Egypt, KSA, or UAE"
        ),
    )

    language: Language | None = Field(
        default=None,
        description=(
            "Canonical language filter: "
            "ar, en, ar-en, or unknown"
        ),
    )

    extra_filters: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Custom additional retrieval "
            "filter criteria"
        ),
    )

    document_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Document IDs that define the allowed "
            "retrieval scope for this query"
        ),
    )

    @field_validator(
        "language",
        mode="before",
    )
    @classmethod
    def normalize_language(
        cls,
        value: Any,
    ) -> Any:
        return _normalize_language_value(
            value
        )

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(
        cls,
        values: list[str],
    ) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for value in values:
            cleaned = value.strip()

            if not cleaned:
                raise ValueError(
                    "document_ids must not "
                    "contain empty values"
                )

            if any(
                character.isspace()
                for character in cleaned
            ):
                raise ValueError(
                    "document_ids must not "
                    "contain whitespace"
                )

            if cleaned not in seen:
                normalized.append(
                    cleaned
                )
                seen.add(
                    cleaned
                )

        return normalized


class IdentifierSet(BaseModel):
    """
    Exact legal identifiers extracted by M2 and handed to M3.

    M3 may use these values for exact-identifier retrieval in
    addition to semantic and keyword retrieval.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    article_numbers: list[str] = Field(
        default_factory=list,
    )

    case_numbers: list[str] = Field(
        default_factory=list,
    )

    dates: list[str] = Field(
        default_factory=list,
    )

    monetary_values: list[str] = Field(
        default_factory=list,
    )

    party_names: list[str] = Field(
        default_factory=list,
    )

    named_legal_terms: list[str] = Field(
        default_factory=list,
        description=(
            "Named legal concepts or terms that "
            "should be preserved for exact or "
            "hybrid retrieval"
        ),
    )


class ProcessedQuery(BaseModel):
    """
    Stable M2 -> M3 query handoff contract.

    M2 owns:
    - multilingual processing;
    - exact identifier preservation;
    - controlled query variants;
    - retrieval filters;
    - query embeddings.

    M3 consumes this object for retrieval and should not
    reproduce M2 query-processing logic.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    query_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Unique query identifier"
        ),
    )

    text_original: str = Field(
        ...,
        min_length=1,
        description=(
            "Original user query preserved exactly"
        ),
    )

    normalized_text: str = Field(
        ...,
        min_length=1,
        description=(
            "Conservatively normalized query text"
        ),
    )

    language: Language = Field(
        default="unknown",
        description=(
            "Canonical query language: "
            "ar, en, ar-en, or unknown"
        ),
    )

    embedding: list[float] = Field(
        default_factory=list,
        description=(
            "Dense BGE-M3 embedding vector. "
            "Empty before embedding and populated "
            "before the final M2 -> M3 retrieval handoff."
        ),
    )

    sparse_embedding: (
        dict[str, float] | None
    ) = Field(
        default=None,
        description=(
            "Optional sparse representation retained "
            "for backward compatibility with hybrid "
            "retrieval experiments"
        ),
    )

    filters: QueryFilters = Field(
        default_factory=QueryFilters,
        description=(
            "Metadata filters used to scope "
            "M3 retrieval"
        ),
    )

    query_variants: list[str] = Field(
        default_factory=list,
        description=(
            "Ordered controlled query variants "
            "produced by M2. The original user text "
            "remains available separately."
        ),
    )

    identifiers: IdentifierSet = Field(
        default_factory=IdentifierSet,
        description=(
            "Exact legal identifiers preserved by M2"
        ),
    )

    @field_validator(
        "language",
        mode="before",
    )
    @classmethod
    def normalize_language(
        cls,
        value: Any,
    ) -> Any:
        return _normalize_language_value(
            value
        )

    @field_validator(
        "query_id",
        "text_original",
        "normalized_text",
    )
    @classmethod
    def reject_whitespace_only(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "query identifiers and query text "
                "must not be whitespace-only"
            )

        return value


class EmbeddedDocumentChunk(BaseModel):
    """
    M2 output for one embedded M1 document chunk.

    Source metadata is preserved so M3 can store it in
    Qdrant and later reconstruct trustworthy retrieval
    evidence and citations.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    document_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Source legal document ID"
        ),
    )

    chunk_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Unique chunk ID within the document"
        ),
    )

    text: str = Field(
        ...,
        min_length=1,
        description=(
            "Original M1 chunk text"
        ),
    )

    page: int | None = Field(
        default=None,
        ge=1,
        description=(
            "1-based source page"
        ),
    )

    section: str | None = Field(
        default=None,
        description=(
            "Source section or heading"
        ),
    )

    clause: str | None = Field(
        default=None,
        description=(
            "Source clause/article identifier"
        ),
    )

    language: Language = Field(
        default="unknown",
        description=(
            "Chunk language"
        ),
    )

    document_type: DocumentType = Field(
        default="unknown",
        description=(
            "Legal document type"
        ),
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Preserved M1 metadata"
        ),
    )

    embedding: list[float] = Field(
        ...,
        min_length=1,
        description=(
            "Dense BGE-M3 embedding vector"
        ),
    )

    model: str = Field(
        ...,
        min_length=1,
        description=(
            "Embedding model name"
        ),
    )

    dimension: int = Field(
        ...,
        ge=1,
        description=(
            "Embedding vector dimension"
        ),
    )


class EmbeddedQuery(BaseModel):
    """
    M2 query-processing result before M3 retrieval.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    processed_query: ProcessedQuery = Field(
        ...,
        description=(
            "The processed query"
        ),
    )

    embedding: list[float] = Field(
        ...,
        min_length=1,
        description=(
            "Dense embedding vector"
        ),
    )

    model: str = Field(
        ...,
        min_length=1,
        description=(
            "Embedding model name"
        ),
    )

    dimension: int = Field(
        ...,
        ge=1,
        description=(
            "Embedding vector dimension"
        ),
    )