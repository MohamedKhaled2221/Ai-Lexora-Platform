from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeRecordType(str, Enum):
    CASE = "case"
    PARTY = "party"
    PERSON = "person"
    JUDGE = "judge"
    COURT = "court"
    LAW = "law"
    ARTICLE = "article"
    OUTCOME = "outcome"


class ValidityStatus(str, Enum):
    CURRENT = "current"
    SUPERSEDED = "superseded"
    REVIEW_REQUIRED = "review_required"


class AccessLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class SourcePassage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_uri: str | None = None
    passage: str
    page: int | None = Field(default=None, ge=1)
    chunk_id: str | None = None


class AccessMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Secure by default
    access_level: AccessLevel = AccessLevel.RESTRICTED

    # Preserve the original ACL scope from upstream systems
    acl_scope: str | None = None

    client_id: str | None = None
    matter_id: str | None = None
    allowed_roles: list[str] = Field(default_factory=list)


class ReviewMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_outcome: str | None = None
    reviewer: str | None = None
    reviewed_at: datetime | None = None


class KnowledgeRecord(BaseModel):
    """
    Canonical M6 knowledge record.

    PostgreSQL is intended to be the authoritative state store.
    """

    model_config = ConfigDict(extra="forbid")

    record_id: str
    record_type: KnowledgeRecordType

    canonical_name: str
    normalized_data: dict[str, Any] = Field(default_factory=dict)

    source_passages: list[SourcePassage] = Field(default_factory=list)

    validity_status: ValidityStatus = ValidityStatus.CURRENT
    effective_from: date | None = None
    effective_to: date | None = None

    supersedes_record_id: str | None = None
    superseded_by_record_id: str | None = None

    review: ReviewMetadata = Field(default_factory=ReviewMetadata)
    access: AccessMetadata = Field(default_factory=AccessMetadata)

    version: int = Field(default=1, ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RelatedRecordQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
    relationship_types: list[str] = Field(default_factory=list)
    record_types: list[KnowledgeRecordType] = Field(default_factory=list)
    include_superseded: bool = False
    limit: int = Field(default=20, ge=1, le=100)


class RelatedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: KnowledgeRecord
    relationship_type: str
    relationship_id: str | None = None


class IndexUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
    operation: str
    version: int = Field(ge=1)
    embedding_text: str | None = None


class EvidenceSufficiencyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sufficient: bool
    score: float = Field(ge=0.0, le=1.0)
    reason: str
    missing_information: list[str] = Field(default_factory=list)
    requires_follow_up: bool = False

'''
class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str
    source_id: str
    source_uri: str | None = None
    passage: str
    page: int | None = None
    record_id: str | None = None
'''
'''
class AnswerGenerationRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    query: str
    response_language: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    follow_up_context: str | None = None
    evidence_sufficiency: EvidenceSufficiencyResult
'''