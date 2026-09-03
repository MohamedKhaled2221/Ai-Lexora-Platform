from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Language(str, Enum):
    AR = "ar"
    EN = "en"
    AR_EN = "ar-en"
    UNKNOWN = "unknown"


class ClauseType(str, Enum):
    TERMINATION = "termination"
    LIABILITY = "liability"
    PAYMENT = "payment"
    CONFIDENTIALITY = "confidentiality"
    RENEWAL = "renewal"
    PENALTY = "penalty"
    GOVERNING_LAW = "governing_law"
    DISPUTE_RESOLUTION = "dispute_resolution"
    INDEMNITY = "indemnity"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    FORCE_MAJEURE = "force_majeure"
    TERM = "term"
    NOTICE = "notice"
    ASSIGNMENT = "assignment"
    REPRESENTATIONS = "representations"
    WARRANTIES = "warranties"
    DATA_PROTECTION = "data_protection"
    OTHER = "other"
    UNKNOWN = "unknown"


class DeviationType(str, Enum):
    MATCHED = "matched"
    MODIFIED = "modified"
    PROHIBITED = "prohibited"
    UNUSUAL = "unusual"
    NO_REFERENCE = "no_reference"


class SourceLocation(BaseModel):
    """
    Source/provenance information for a clause.

    M1-specific identifiers and additional provenance data that do not
    belong directly to this location model are preserved in metadata.
    """

    model_config = ConfigDict(extra="allow")

    page_start: Optional[int] = None
    page_end: Optional[int] = None

    section: Optional[str] = None
    clause_number: Optional[str] = None

    source_span_start: Optional[int] = None
    source_span_end: Optional[int] = None


class LegalEntity(BaseModel):
    """
    Entity extracted from a legal clause.

    Examples:
        party
        organization
        person
        date
        money
        duration
        legal_identifier
    """

    model_config = ConfigDict(extra="allow")

    entity_type: str
    value: str
    normalized_value: Optional[str] = None

    start: Optional[int] = None
    end: Optional[int] = None

    confidence: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
    )


class ReferenceClause(BaseModel):
    """
    Approved/reference clause used by M5 for comparison.
    """

    model_config = ConfigDict(extra="allow")

    reference_clause_id: str

    clause_type: Optional[ClauseType] = None
    title: Optional[str] = None
    text: str

    language: Language = Language.UNKNOWN

    jurisdiction: Optional[str] = None
    document_type: Optional[str] = None

    approval_status: Optional[str] = None
    version: Optional[str] = None
    effective_date: Optional[str] = None

    metadata: Dict[str, Any] = Field(
        default_factory=dict
    )


class ReferenceMatch(BaseModel):
    """
    Result of comparing a contract clause against a reference clause.

    M5 provides the comparison evidence.
    M6 owns the final risk decision.
    """

    model_config = ConfigDict(extra="allow")

    reference_clause_id: str

    similarity_score: float = Field(
        ge=0.0,
        le=1.0,
    )

    deviation: DeviationType

    comparison_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    reasons: List[str] = Field(
        default_factory=list
    )


class M1ContractSection(BaseModel):
    """
    Internal M5 input model used after adapting M1 output.

    This is NOT the actual M1 DocumentChunk schema.

    adapters.py converts the real M1 payload into this internal
    representation so the rest of M5 does not depend directly on
    M1's JSON structure.
    """

    model_config = ConfigDict(extra="allow")

    document_id: str

    section_id: Optional[str] = None
    section: Optional[str] = None
    title: Optional[str] = None

    text: str

    page_start: Optional[int] = None
    page_end: Optional[int] = None

    language: Language = Language.UNKNOWN

    clause_number: Optional[str] = None

    clauses: Optional[List[Dict[str, Any]]] = None

    # Preserves M1 provenance and structural metadata that is not part
    # of the normalized M5 fields.
    metadata: Dict[str, Any] = Field(
        default_factory=dict
    )

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "M1 section text cannot be empty"
            )

        return value


class ContractClause(BaseModel):
    """
    Stable M5 -> M6 contract.

    M5 is responsible for describing the clause, its classification,
    extracted entities, source evidence, and reference comparison.

    M6 is responsible for final risk assessment.
    """

    model_config = ConfigDict(extra="allow")

    # -------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------

    contract_clause_id: str
    document_id: str

    source_section_id: Optional[str] = None

    # -------------------------------------------------------------
    # Clause information
    # -------------------------------------------------------------

    clause_number: Optional[str] = None
    title: Optional[str] = None

    # Original legal text.
    text: str

    language: Language = Language.UNKNOWN

    # -------------------------------------------------------------
    # Classification
    # -------------------------------------------------------------

    clause_type: ClauseType

    classification_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    # -------------------------------------------------------------
    # Extracted legal entities
    # -------------------------------------------------------------

    entities: List[LegalEntity] = Field(
        default_factory=list
    )

    # -------------------------------------------------------------
    # Source / provenance
    # -------------------------------------------------------------

    source_location: SourceLocation

    # -------------------------------------------------------------
    # Reference comparison
    # -------------------------------------------------------------

    reference_match: Optional[ReferenceMatch] = None

    # -------------------------------------------------------------
    # Integration / audit information
    #
    # M1-specific provenance such as source_chunk_id,
    # source_clause_id, bbox, etc. can be preserved here without
    # coupling the public M5 contract to the exact M1 schema.
    # -------------------------------------------------------------

    metadata: Dict[str, Any] = Field(
        default_factory=dict
    )

    processing: Dict[str, Any] = Field(
        default_factory=dict
    )