from .m1_contract import DocumentChunk
from .m2_contract import (
    EmbeddedDocumentChunk,
    EmbeddedQuery,
    IdentifierSet,
    ProcessedQuery,
    QueryFilters,
)
from .m4_contract import (
    AIResponse,
    Citation,
    EvidenceItem,
    M4ModelOutput,
    RetrievedEvidence,
)
from .m5_contract import (
    ApprovalEvent,
    ApprovalStatus,
    ApprovedClause,
    ClauseCompatibilityRule,
    ClauseMetadata,
    ClauseRequirement,
    ClauseType,
    CompletenessReport,
    CompatibilityRelationship,
    CompatibilityResult,
    ConditionalClause,
    DocumentType,
    Jurisdiction,
    M5ToM1Handoff,
    M5ToM4Handoff,
    ProvenanceReport,
    SpecialConditionResult,
    TemplateClauseRequirement,
    TraceRecord,
    ValidationReport,
    VersionEntry,
)
from .p3_generation_contract import (
    AITransformationRecord,
    AssembledDraft,
    ClauseReference,
    DraftSection,
    DraftSourceType,
    DraftValidationResult,
    GenerationManifest,
    LawyerEditReference,
    SourceReference,
    ValidatedDraft,
)
from .p4_chat_contract import (
    AnswerGenerationRequest,
    ResponseLanguage,
    SafeContextTurn,
    ValidatedAIResponse,
)


__all__ = [
    "DocumentChunk",
    "ProcessedQuery",
    "QueryFilters",
    "IdentifierSet",
    "EmbeddedDocumentChunk",
    "EmbeddedQuery",

    # Existing M4 / P1-P2
    "EvidenceItem",
    "RetrievedEvidence",
    "M4ModelOutput",
    "Citation",
    "AIResponse",

    # M5
    "ClauseType",
    "Jurisdiction",
    "DocumentType",
    "ApprovalStatus",
    "ClauseRequirement",
    "CompatibilityRelationship",
    "ClauseMetadata",
    "ApprovedClause",
    "ClauseCompatibilityRule",
    "ConditionalClause",
    "TemplateClauseRequirement",
    "SpecialConditionResult",
    "ApprovalEvent",
    "TraceRecord",
    "VersionEntry",
    "CompatibilityResult",
    "CompletenessReport",
    "ValidationReport",
    "ProvenanceReport",
    "M5ToM1Handoff",
    "M5ToM4Handoff",

    # Package 3
    "DraftSourceType",
    "SourceReference",
    "DraftSection",
    "AssembledDraft",
    "ClauseReference",
    "LawyerEditReference",
    "AITransformationRecord",
    "GenerationManifest",
    "DraftValidationResult",
    "ValidatedDraft",

    # Package 4
    "ResponseLanguage",
    "SafeContextTurn",
    "AnswerGenerationRequest",
    "ValidatedAIResponse",
]