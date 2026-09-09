from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Language = Literal[
    "ar",
    "en",
    "ar-en",
    "unknown",
]

DocumentType = Literal[
    "contract",
    "law",
    "court_ruling",
    "pleading",
    "power_of_attorney",
    "correspondence",
    "unknown",
]

ConfidentialityLevel = Literal[
    "public",
    "internal",
    "privileged",
]


class DocumentChunk(BaseModel):
    """
    Shared M1 -> M2 document chunk contract.

    This mirrors the stable fields emitted by M1 and consumed by M2
    for embedding and later indexing.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(
        ...,
        min_length=1,
        description="Stable source document identifier",
    )

    chunk_id: str = Field(
        ...,
        min_length=1,
        description="Chunk identifier unique within the document",
    )

    text: str = Field(
        ...,
        min_length=1,
        description="Normalized chunk text to embed",
    )

    page: int = Field(
        ...,
        ge=1,
        description="1-based page where the chunk starts",
    )

    section: str | None = Field(
        default=None,
        description="Section/article/heading label",
    )

    clause: str | None = Field(
        default=None,
        description="Clause/article identifier when available",
    )

    language: Language = Field(
        default="unknown",
        description="Dominant chunk language",
    )

    document_type: DocumentType = Field(
        default="unknown",
        description="Coarse legal document type",
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional M1 structural/source metadata",
    )

    # ------------------------------------------------------------------
    # Access control.
    #
    # Optional on the wire because M1 is not an authority on who may read
    # a document. The authoritative values are stamped at the M3 ingest
    # boundary from the authenticated caller and overwrite anything set
    # here; indexing refuses a chunk that is still unstamped, so None can
    # never reach Qdrant meaning "unrestricted".
    # ------------------------------------------------------------------

    client_id: str | None = Field(
        default=None,
        description=(
            "Owning tenant/client. Reserved value '_shared' marks the "
            "cross-tenant legal corpus."
        ),
    )

    matter_id: str | None = Field(
        default=None,
        description=(
            "Owning matter. Reserved value '_none' marks a client-level "
            "document not tied to any matter."
        ),
    )

    confidentiality_level: ConfidentialityLevel | None = Field(
        default=None,
        description=(
            "Access ladder: public < internal < privileged. Distinct from "
            "M5's ClauseType.CONFIDENTIALITY, which is a clause topic."
        ),
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "chunk text must not be empty or whitespace-only"
            )

        return value

    @field_validator("document_id", "chunk_id")
    @classmethod
    def validate_ids(cls, value: str) -> str:
        if any(character.isspace() for character in value):
            raise ValueError(
                "document_id and chunk_id must not contain whitespace"
            )

        return value