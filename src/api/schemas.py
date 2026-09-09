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