"""
Package 4 shared contracts for grounded legal answer generation.

These models define the M6 -> M4 handoff and the validated
M4 output for Package 4.

M6 -> M4:
    AnswerGenerationRequest

M4 -> downstream:
    ValidatedAIResponse

M4 must generate only from trusted RetrievedEvidence.
Conversation context may help interpret the question but must
never be treated as legal evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .m4_contract import (
    Citation,
    M4ModelOutput,
    RetrievedEvidence,
)


# ---------------------------------------------------------
# Response policy
# ---------------------------------------------------------


class ResponseLanguage(str, Enum):
    """
    Language selected upstream by M6 for the final response.
    """

    ARABIC = "ar"
    ENGLISH = "en"
    MIXED = "mixed"

class P4GroundedModelOutput(M4ModelOutput):
    """
    Structured LLM output for Package 4 when M6 has already
    declared the retrieved evidence sufficient.

    Unlike the shared M4ModelOutput contract, a grounded
    Package 4 answer must cite at least one supplied evidence
    alias.
    """

    citation_ids: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "One or more trusted evidence aliases supporting "
            "the answer. Package 4 grounded generation requires "
            "at least one alias, for example ['E1']."
        ),
    )

class SafeContextTurn(BaseModel):
    """
    Conversation context that may be used to interpret a follow-up.

    This is NOT trusted legal evidence. M4 must never use a previous
    model answer as factual/legal support for a new answer.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    role: Literal["user", "assistant"] = Field(
        ...,
        description="Conversation role",
    )

    text: str = Field(
        ...,
        min_length=1,
        description="Conversation text used only as safe context",
    )


# ---------------------------------------------------------
# M6 -> M4
# ---------------------------------------------------------


class AnswerGenerationRequest(BaseModel):
    """
    Final generation request prepared by M6 and consumed by M4.

    Authorization, confidentiality, status, and other retrieval
    filters must already have been applied before evidence enters
    this contract.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    request_id: str = Field(
        ...,
        min_length=1,
        description="Stable ID for this generation request",
    )

    query_id: str = Field(
        ...,
        min_length=1,
        description="Query identifier propagated through the pipeline",
    )

    original_query: str = Field(
        ...,
        min_length=1,
        description="Original user question",
    )

    response_language: ResponseLanguage = Field(
        ...,
        description="Response language selected by M6 policy",
    )

    retrieved_evidence: RetrievedEvidence = Field(
        ...,
        description=(
            "Trusted evidence package created by the retrieval pipeline"
        ),
    )

    evidence_sufficient: bool = Field(
        ...,
        description=(
            "Whether M6 determined that the retrieved evidence "
            "is sufficient for grounded generation"
        ),
    )

    insufficiency_reason: str | None = Field(
        default=None,
        description=(
            "Required when evidence_sufficient is false"
        ),
    )

    safe_context: list[SafeContextTurn] = Field(
        default_factory=list,
        description=(
            "Conversation-safe context for follow-up interpretation. "
            "It must not be treated as legal evidence."
        ),
    )

    response_instructions: list[str] = Field(
        default_factory=list,
        description=(
            "Optional non-evidentiary response policy instructions "
            "supplied by M6"
        ),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Time the generation request was created",
    )

    @model_validator(mode="after")
    def validate_generation_request(
        self,
    ) -> "AnswerGenerationRequest":
        if (
            self.query_id
            != self.retrieved_evidence.query_id
        ):
            raise ValueError(
                "query_id must match "
                "retrieved_evidence.query_id"
            )

        evidence_items = (
            self.retrieved_evidence.retrieved_evidence
        )

        if (
            self.evidence_sufficient
            and not evidence_items
        ):
            raise ValueError(
                "evidence_sufficient cannot be true "
                "when RetrievedEvidence is empty"
            )

        if self.evidence_sufficient:
            if (
                self.insufficiency_reason is not None
                and self.insufficiency_reason.strip()
            ):
                raise ValueError(
                    "insufficiency_reason must be empty "
                    "when evidence_sufficient is true"
                )

        else:
            if (
                self.insufficiency_reason is None
                or not self.insufficiency_reason.strip()
            ):
                raise ValueError(
                    "insufficiency_reason is required "
                    "when evidence_sufficient is false"
                )

        return self


# ---------------------------------------------------------
# M4 -> downstream
# ---------------------------------------------------------


class ValidatedAIResponse(BaseModel):
    """
    Package 4 output produced after M4 generation and validation.

    Citation metadata must come from trusted RetrievedEvidence,
    never directly from LLM-generated metadata.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    request_id: str = Field(
        ...,
        min_length=1,
        description="Generation request identifier",
    )

    query_id: str = Field(
        ...,
        min_length=1,
        description="Original query identifier",
    )

    answer: str = Field(
        ...,
        min_length=1,
        description="Final grounded answer",
    )

    citations: list[Citation] = Field(
        default_factory=list,
        description=(
            "Trusted citations resolved in Python from evidence aliases"
        ),
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Final confidence score",
    )

    insufficient_evidence: bool = Field(
        default=False,
        description=(
            "True when the available trusted evidence "
            "cannot support a legal answer"
        ),
    )

    grounding_valid: bool = Field(
        ...,
        description=(
            "Whether answer claims are grounded in trusted evidence"
        ),
    )

    citations_valid: bool = Field(
        ...,
        description=(
            "Whether every returned citation resolves to "
            "trusted RetrievedEvidence"
        ),
    )

    structured_output_valid: bool = Field(
        ...,
        description="Whether model output satisfied the M4 schema",
    )

    unsupported_claims: list[str] = Field(
        default_factory=list,
        description=(
            "Claims detected as unsupported during validation"
        ),
    )

    validation_errors: list[str] = Field(
        default_factory=list,
        description="Blocking validation problems",
    )

    model_tag: str = Field(
        ...,
        min_length=1,
        description="Exact local Ollama/Qwen model tag used",
    )

    prompt_version: str = Field(
        ...,
        min_length=1,
        description="Version of the generation prompt used",
    )

    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Time generation and validation completed",
    )

    @field_validator("citations")
    @classmethod
    def validate_unique_citations(
        cls,
        citations: list[Citation],
    ) -> list[Citation]:
        evidence_ids = [
            citation.evidence_id
            for citation in citations
        ]

        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError(
                "ValidatedAIResponse cannot contain "
                "duplicate evidence citations"
            )

        return citations

    @model_validator(mode="after")
    def validate_citation_requirements(
        self,
    ) -> "ValidatedAIResponse":
        if (
            not self.insufficient_evidence
            and not self.citations
        ):
            raise ValueError(
                "A grounded answer requires at least one citation"
            )

        return self
