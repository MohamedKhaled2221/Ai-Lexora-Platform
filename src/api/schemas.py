from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from src.orchestration.grounding_validator import (
    P3GroundingContext,
)
from src.schemas.m2_contract import (
    ProcessedQuery,
    QueryFilters,
)
from src.schemas.m4_contract import (
    RetrievedEvidence,
)
from src.schemas.m6_contract import (
    ContractRisk,
)
from src.schemas.p3_generation_contract import (
    AssembledDraft,
    GenerationManifest,
)

from src.document_generator.schemas import (
    GuidedDocumentRequest,
)
from src.schemas.p3_generation_contract import (
    ValidatedDraft,
)
from src.schemas.p4_chat_contract import (
    ResponseLanguage,
    SafeContextTurn,
)


class P3GenerateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    request: GuidedDocumentRequest

    clause_language: Literal[
        "ar",
        "en",
    ] = "en"

    export_docx: bool = True


class P3GenerateResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    validated_draft: ValidatedDraft

    selected_clause_ids: List[str]

    export_allowed: bool

    m5_resolved_clause_count: int

    docx_generated: bool = False

    docx_file_name: str | None = None


class P4ChatRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    question: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=4000,
        ),
    ]

    filters: QueryFilters = Field(
        default_factory=QueryFilters
    )

    response_language: (
        ResponseLanguage | None
    ) = None

    safe_context: List[
        SafeContextTurn
    ] = Field(
        default_factory=list
    )
# =========================================================
# Existing P1/P2 RAG API contracts
# =========================================================


class RawRAGAnswerRequest(BaseModel):
    """
    Frontend-friendly request for the complete
    raw-question M2 -> M3 -> M4 pipeline.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    question: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
        ),
    ]

    filters: QueryFilters = Field(
        default_factory=QueryFilters
    )


class RAGSearchRequest(BaseModel):
    """
    Request for ranked document search (M2 -> M3, no LLM).

    Same ``filters`` shape as ``/ask``, so a caller that already scopes
    ``/ask`` to a user's ``document_ids`` can send the same filters here.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    query: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=4000,
        ),
    ]

    filters: QueryFilters = Field(
        default_factory=QueryFilters
    )

    page: int = Field(default=1, ge=1)

    page_size: int = Field(default=10, ge=1, le=50)


class RAGSearchHit(BaseModel):
    """One document in the results, represented by its best-matching chunk."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    score: float
    snippet: str
    chunk_id: str
    page: int | None = None
    section: str | None = None
    matched_chunks: int = Field(..., ge=1)


class RAGSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str
    hits: List[RAGSearchHit]
    total: int = Field(
        ...,
        ge=0,
        description=(
            "Documents found within the ranked candidate window "
            "(at most 100 chunks), not every document in the corpus."
        ),
    )
    page: int
    page_size: int


class RAGAnswerRequest(BaseModel):
    """
    Request contract for M3 -> M4 RAG generation.

    Embedding/preprocessing is still owned by M2.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    processed_query: ProcessedQuery


class M4AnswerRequest(BaseModel):
    """
    API request for the existing M4 grounded-answer boundary.

    ProcessedQuery is produced upstream by M2.
    RetrievedEvidence is produced upstream by M3.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    processed_query: ProcessedQuery
    retrieved_evidence: RetrievedEvidence


# =========================================================
# Existing M6 contract-risk API contracts
# =========================================================


class M6RiskRequest(BaseModel):
    clauses: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Contract clauses produced by M5",
    )


class M6RiskResponse(BaseModel):
    risks: List[ContractRisk] = Field(
        default_factory=list,
        description="Risks detected by M6",
    )


# =========================================================
# Package 3 M1 -> M5 -> M4 API contract
# =========================================================


class P3ValidationRequest(BaseModel):
    """
    Stable Package 3 validation request.

    Approved-clause text is resolved internally from M5.

    grounding_context is only for trusted sources that are not
    owned by M5, for example:
    - template source text;
    - lawyer-approved edits.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    draft: AssembledDraft

    manifest: GenerationManifest

    clause_language: Literal[
        "ar",
        "en",
    ] = "en"

    grounding_context: P3GroundingContext = Field(
        default_factory=P3GroundingContext
    )

#

class P3TemplateFieldResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    name: str
    label: str
    field_type: str
    required: bool


class P3TemplateSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    template_id: str
    document_type: str
    jurisdiction: str
    fields: List[P3TemplateFieldResponse]


class P3TemplatesResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    templates: List[P3TemplateSummary]
