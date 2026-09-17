from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class DraftStatus(str, Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"


class FieldDefinition(BaseModel):
    name: str
    label: str
    field_type: Literal[
        "text",
        "date",
        "number",
        "currency",
        "boolean",
        "select",
        "multiline",
    ] = "text"
    required: bool = True
    description: Optional[str] = None
    options: List[str] = Field(default_factory=list)


'''class ConditionalClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_id: str
    condition: str
    description: Optional[str] = None
'''

'''class TemplateDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str
    version: str
    document_type: str
    jurisdiction: str
    language: Literal["ar", "en", "ar-en", "unknown"] = "en"
    file_path: Optional[str] = None

    fields: List[FieldDefinition] = Field(
        default_factory=list
    )

    placeholder_pattern: str = (
        r"\{\{([A-Za-z0-9_.:-]+)\}\}"
    )

    active: bool = True

    required_clauses: List[str] = Field(
        default_factory=list
    )

    optional_clauses: List[str] = Field(
        default_factory=list
    )

    prohibited_clauses: List[str] = Field(
        default_factory=list
    )

    conditional_clauses: List[ConditionalClause] = Field(
        default_factory=list
    )

    # Provided by M5 template_requirements.json.
    # Maps logical section identifiers to their placeholders.
    section_placeholders: Dict[str, str] = Field(
        default_factory=dict
    )

    # Template structure supplied by M5.
    template_structure: Optional[str] = None
'''
class TemplateDefinition(BaseModel):
    """
    M1-owned document template metadata.

    Clause policy and clause placement rules are intentionally
    not stored here. Those are supplied by M5 through
    TemplateClauseRequirement.
    """

    model_config = ConfigDict(extra="forbid")

    template_id: str
    version: str
    document_type: str
    jurisdiction: str

    language: Literal[
        "ar",
        "en",
        "ar-en",
        "unknown",
    ] = "en"

    file_path: Optional[str] = None

    fields: List[FieldDefinition] = Field(
        default_factory=list
    )

    placeholder_pattern: str = (
        r"\{\{([A-Za-z0-9_.:-]+)\}\}"
    )

    active: bool = True
class GuidedDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    document_type: str
    jurisdiction: str

    fields: Dict[str, Any] = Field(
        default_factory=dict
    )

    requested_clause_ids: List[str] = Field(
        default_factory=list
    )

    special_conditions: List[str] = Field(
        default_factory=list
    )


'''class ApprovedClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_id: str
    type: str
    jurisdiction: str

    document_types: List[str] = Field(
        default_factory=list
    )

    version: str

    approval_status: Literal["approved"] = "approved"

    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    owner: Optional[str] = None
    source: Optional[str] = None

    text_ar: Optional[str] = None
    text_en: Optional[str] = None

    metadata: Dict[str, Any] = Field(
        default_factory=dict
    )

    superseded_by: Optional[str] = None
    supersedes: Optional[str] = None

    is_lawyer_edited: bool = False
    requires_separate_approval: bool = False

    tags: List[str] = Field(
        default_factory=list
    )

    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Populated from M5 metadata.insertion_key.
    insertion_key: Optional[str] = None

    sequence: int = 0
    required: bool = False

'''
class ClauseDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_id: str

    decision: Literal[
        "selected",
        "required",
        "optional",
        "prohibited",
        "incompatible",
        "requires_lawyer_input",
    ]

    reason: Optional[str] = None


class AssembledSection(BaseModel):
    section_id: str
    title: Optional[str] = None
    text: str
    order: int

    source_type: Literal[
        "template",
        "approved_clause",
        "user_field",
        "lawyer_edit",
    ]

    source_id: str

    clause_id: Optional[str] = None
    clause_version: Optional[str] = None


class AssembledDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    request_id: str

    template_id: str
    template_version: str

    document_type: str
    jurisdiction: str

    sections: List[AssembledSection]

    plain_text: str

    status: DraftStatus = DraftStatus.DRAFT


class AITransformation(BaseModel):
    used: bool = False

    model_tag: Optional[str] = None
    prompt_version: Optional[str] = None
    description: Optional[str] = None

    allowed_source_ids: List[str] = Field(
        default_factory=list
    )


class GenerationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generation_id: str
    draft_id: str
    request_id: str

    template_id: str
    template_version: str

    clause_refs: List[Dict[str, str]] = Field(
        default_factory=list
    )

    user_fields: Dict[str, Any] = Field(
        default_factory=dict
    )

    timestamps: Dict[str, str] = Field(
        default_factory=dict
    )

    ai_transformation: AITransformation = Field(
        default_factory=AITransformation
    )

    edits: List[Dict[str, Any]] = Field(
        default_factory=list
    )

    @classmethod
    def now(cls, **kwargs: Any) -> "GenerationManifest":
        return cls(
            timestamps={
                "created_at": datetime.now(
                    timezone.utc
                ).isoformat()
            },
            **kwargs,
        )


class DraftValidationResult(BaseModel):
    valid: bool

    errors: List[str] = Field(
        default_factory=list
    )

    warnings: List[str] = Field(
        default_factory=list
    )

    checked_at: str


class ReviewRecord(BaseModel):
    review_id: str
    draft_id: str
    reviewer_id: str

    decision: ReviewDecision

    timestamp: str

    notes: Optional[str] = None

    edited_section_ids: List[str] = Field(
        default_factory=list
    )


class ExportResult(BaseModel):
    success: bool
    format: Literal["docx", "pdf"]

    path: Optional[str] = None
    error: Optional[str] = None

    exported_at: str


class KnowledgePassage(BaseModel):
    passage_id: str
    document_id: str
    text: str

    language: Literal[
        "ar",
        "en",
        "ar-en",
        "unknown",
    ]

    page_start: Optional[int] = None
    page_end: Optional[int] = None

    section: Optional[str] = None
    clause: Optional[str] = None
    heading: Optional[str] = None

    source_uri: Optional[str] = None

    metadata: Dict[str, Any] = Field(
        default_factory=dict
    )


class NormalizedLegalRecord(BaseModel):
    record_id: str
    source_document_id: str

    source_type: Literal[
        "case",
        "law",
        "article",
        "regulation",
        "memo",
        "other",
    ]

    title: Optional[str] = None
    jurisdiction: Optional[str] = None

    language: Literal[
        "ar",
        "en",
        "ar-en",
        "unknown",
    ]

    approved: bool = True

    passages: List[KnowledgePassage]

    metadata: Dict[str, Any] = Field(
        default_factory=dict
    )