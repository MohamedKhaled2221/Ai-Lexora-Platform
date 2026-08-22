from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from src.schemas.m2_contract import (
    ProcessedQuery,
    QueryFilters,
)
from src.schemas.m4_contract import RetrievedEvidence

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
    API request for the M4 grounded-answer boundary.

    ProcessedQuery is produced upstream by M2.
    RetrievedEvidence is produced upstream by M3.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    processed_query: ProcessedQuery
    retrieved_evidence: RetrievedEvidence
