from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from src.orchestration.p4_orchestrator import (
    P4OrchestrationResult,
)
from src.orchestration.raw_rag_service import (
    M2EmbeddingContractError,
    M2QueryRuntimeError,
    M2QueryValidationError,
)
from src.schemas.access_control import (
    AccessScopeRequired,
)
from src.schemas.m2_contract import (
    EmbeddedQuery,
    ProcessedQuery,
    QueryFilters,
)
from src.schemas.m4_contract import (
    RetrievedEvidence,
)
from src.schemas.m6_knowledge import (
    ValidityStatus,
)
from src.schemas.p4_chat_contract import (
    AnswerGenerationRequest,
    ResponseLanguage,
    SafeContextTurn,
    ValidatedAIResponse,
)


class P4RetrievalPolicyError(RuntimeError):
    """
    Package 4 retrieval is not configured
    fail-closed for lifecycle.
    """


class P4RetrievalContractError(RuntimeError):
    """
    M3 returned evidence that violates the
    Package 4 retrieval contract.
    """


class M2QueryPipelineProtocol(Protocol):
    def process(
        self,
        raw_query: str,
    ) -> EmbeddedQuery:
        ...


class M3RetrievalPipelineProtocol(Protocol):
    hybrid_searcher: object

    def run(
        self,
        query: ProcessedQuery,
    ) -> tuple[
        RetrievedEvidence,
        float,
    ]:
        ...


class M6KnowledgeIntegrationProtocol(Protocol):
    def build_answer_request(
        self,
        *,
        request_id: str,
        original_query: str,
        response_language: (
            ResponseLanguage
            | str
            | None
        ),
        retrieved_evidence: RetrievedEvidence,
        record_statuses: Sequence[
            ValidityStatus
        ] = (),
        safe_context: Sequence[
            SafeContextTurn
        ] = (),
        response_instructions: Sequence[
            str
        ] = (),
    ) -> AnswerGenerationRequest:
        ...


class P4M4OrchestratorProtocol(Protocol):
    def answer(
        self,
        request: AnswerGenerationRequest,
    ) -> P4OrchestrationResult:
        ...

    async def aanswer(
        self,
        request: AnswerGenerationRequest,
    ) -> P4OrchestrationResult:
        ...


@dataclass(frozen=True)
class P4ChatMetrics:
    retrieval_ms: float
    evidence_count: int
    generation_invoked: bool
    citation_count: int


@dataclass(frozen=True)
class P4ChatResult:
    response: ValidatedAIResponse
    processed_query: ProcessedQuery
    answer_request: AnswerGenerationRequest
    metrics: P4ChatMetrics


class P4ChatService:
    """
    Authoritative Package 4 integration.

    Flow:
        M2 -> M3(current-only) -> M6 -> M4

    Safe conversation context is carried separately
    from trusted legal evidence and is never converted
    into an EvidenceItem.
    """

    _FOLLOW_UP_REFERENCE_RE = re.compile(
        r"\b(?:it|its|this|that|them|their)\b"
        r"|^\s*(?:and|what about|how about)\b",
        re.IGNORECASE,
    )

    # Deliberately narrow document-title extraction.
    #
    # Conversation context may clarify WHICH document a
    # follow-up refers to, but factual statements from
    # conversation history must never become legal evidence.
    _DOCUMENT_TITLE_PATTERNS = (
        re.compile(
            r"\b("
            r"(?:[A-Z][a-z0-9&'/-]*\s+){1,6}"
            r"(?:Agreement|Contract|Document)"
            r")\b"
        ),
        re.compile(
            r"\b("
            r"(?:Agreement|Contract|Document)"
            r"\s+[A-Z0-9][A-Za-z0-9&'/-]*"
            r"(?:\s+[A-Z0-9][A-Za-z0-9&'/-]*){0,2}"
            r")\b"
        ),
    )

    def __init__(
        self,
        *,
        query_pipeline: (
            M2QueryPipelineProtocol
        ),
        retrieval_pipeline: (
            M3RetrievalPipelineProtocol
        ),
        knowledge_service: (
            M6KnowledgeIntegrationProtocol
        ),
        m4_orchestrator: (
            P4M4OrchestratorProtocol
        ),
        expected_embedding_dimension: int = 1024,
    ) -> None:

        if expected_embedding_dimension < 1:
            raise ValueError(
                "expected_embedding_dimension "
                "must be positive"
            )

        self.query_pipeline = (
            query_pipeline
        )

        self.retrieval_pipeline = (
            retrieval_pipeline
        )

        self.knowledge_service = (
            knowledge_service
        )

        self.m4_orchestrator = (
            m4_orchestrator
        )

        self.expected_embedding_dimension = (
            expected_embedding_dimension
        )

        self._validate_retrieval_policy()

    def answer(
        self,
        *,
        question: str,
        filters: QueryFilters,
        request_id: str | None = None,
        response_language: (
            ResponseLanguage
            | str
            | None
        ) = None,
        safe_context: Sequence[
            SafeContextTurn
        ] = (),
        response_instructions: Sequence[
            str
        ] = (),
    ) -> P4ChatResult:

        processed_query = (
            self._prepare_processed_query(
                question=question,
                filters=filters,
                safe_context=safe_context,
            )
        )

        evidence, retrieval_ms = (
            self.retrieval_pipeline.run(
                processed_query
            )
        )

        self._validate_retrieved_evidence(
            processed_query=processed_query,
            evidence=evidence,
        )

        answer_request = (
            self._build_answer_request(
                question=question,
                request_id=request_id,
                response_language=(
                    response_language
                ),
                processed_query=(
                    processed_query
                ),
                evidence=evidence,
                safe_context=safe_context,
                response_instructions=(
                    response_instructions
                ),
            )
        )

        orchestration = (
            self.m4_orchestrator.answer(
                answer_request
            )
        )

        return self._result(
            processed_query=processed_query,
            answer_request=answer_request,
            evidence=evidence,
            retrieval_ms=retrieval_ms,
            orchestration=orchestration,
        )

    async def aanswer(
        self,
        *,
        question: str,
        filters: QueryFilters,
        request_id: str | None = None,
        response_language: (
            ResponseLanguage
            | str
            | None
        ) = None,
        safe_context: Sequence[
            SafeContextTurn
        ] = (),
        response_instructions: Sequence[
            str
        ] = (),
    ) -> P4ChatResult:

        (
            processed_query,
            evidence,
            retrieval_ms,
        ) = await asyncio.to_thread(
            self._prepare_and_retrieve,
            question,
            filters,
            safe_context,
        )

        answer_request = (
            self._build_answer_request(
                question=question,
                request_id=request_id,
                response_language=(
                    response_language
                ),
                processed_query=(
                    processed_query
                ),
                evidence=evidence,
                safe_context=safe_context,
                response_instructions=(
                    response_instructions
                ),
            )
        )

        orchestration = (
            await self.m4_orchestrator.aanswer(
                answer_request
            )
        )

        return self._result(
            processed_query=processed_query,
            answer_request=answer_request,
            evidence=evidence,
            retrieval_ms=retrieval_ms,
            orchestration=orchestration,
        )

    def _prepare_and_retrieve(
        self,
        question: str,
        filters: QueryFilters,
        safe_context: Sequence[
            SafeContextTurn
        ] = (),
    ) -> tuple[
        ProcessedQuery,
        RetrievedEvidence,
        float,
    ]:

        processed_query = (
            self._prepare_processed_query(
                question=question,
                filters=filters,
                safe_context=safe_context,
            )
        )

        evidence, retrieval_ms = (
            self.retrieval_pipeline.run(
                processed_query
            )
        )

        self._validate_retrieved_evidence(
            processed_query=processed_query,
            evidence=evidence,
        )

        return (
            processed_query,
            evidence,
            retrieval_ms,
        )

    def _prepare_processed_query(
        self,
        *,
        question: str,
        filters: QueryFilters,
        safe_context: Sequence[
            SafeContextTurn
        ] = (),
    ) -> ProcessedQuery:

        # The injected M3 searcher is mutable, so enforce
        # Package 4 lifecycle policy on every request.
        self._validate_retrieval_policy()

        if (
            filters is None
            or filters.access is None
        ):
            raise AccessScopeRequired(
                "Package 4 requires QueryFilters "
                "carrying a server-derived AccessScope "
                "before M2/M3 retrieval can run."
            )

        retrieval_question = (
            self._resolve_retrieval_question(
                question=question,
                safe_context=safe_context,
            )
        )

        try:
            embedded = (
                self.query_pipeline.process(
                    retrieval_question
                )
            )

        except ValueError as exc:
            raise M2QueryValidationError(
                "M2 rejected the Package 4 query."
            ) from exc

        except Exception as exc:
            raise M2QueryRuntimeError(
                "The local M2 query runtime failed "
                "for Package 4."
            ) from exc

        self._validate_m2_handoff(
            embedded
        )

        # Filters are supplied by the trusted caller
        # boundary. Never trust filters embedded by M2.
        return (
            embedded
            .processed_query
            .model_copy(
                update={
                    "filters": (
                        filters.model_copy(
                            deep=True
                        )
                    ),
                },
                deep=True,
            )
        )

    @classmethod
    def _resolve_retrieval_question(
        cls,
        *,
        question: str,
        safe_context: Sequence[
            SafeContextTurn
        ],
    ) -> str:
        """
        Resolve only a narrow conversational document reference.

        Conversation history may contribute a document TITLE for
        retrieval clarification. It must never contribute factual
        or legal claims to trusted evidence.

        Access control, matter scope, confidentiality, lifecycle,
        and evidence validation remain downstream and unchanged.
        """

        cleaned_question = " ".join(
            question.split()
        )

        if (
            not safe_context
            or not cls._FOLLOW_UP_REFERENCE_RE.search(
                cleaned_question
            )
        ):
            return question

        for turn in reversed(
            safe_context
        ):
            title = (
                cls._extract_context_document_title(
                    turn.text
                )
            )

            if title is None:
                continue

            if (
                title.casefold()
                in cleaned_question.casefold()
            ):
                return question

            return (
                f"{cleaned_question} "
                f"Referenced document: {title}."
            )

        return question

    @classmethod
    def _extract_context_document_title(
        cls,
        text: str,
    ) -> str | None:
        """
        Extract a narrow title-like document reference only.

        Numbers, deadlines, amounts, instructions, and other
        conversational claims are intentionally discarded.
        """

        for pattern in (
            cls._DOCUMENT_TITLE_PATTERNS
        ):
            matches = list(
                pattern.finditer(text)
            )

            if not matches:
                continue

            title = " ".join(
                matches[-1]
                .group(1)
                .split()
            )

            if title.startswith(
                "The "
            ):
                title = title[4:]

            return title

        return None

    def _validate_m2_handoff(
        self,
        embedded: EmbeddedQuery,
    ) -> None:

        vector_length = len(
            embedded.embedding
        )

        if vector_length == 0:
            raise M2EmbeddingContractError(
                "M2 returned an empty embedding."
            )

        if (
            embedded.dimension
            != vector_length
        ):
            raise M2EmbeddingContractError(
                "M2 embedding dimension metadata "
                "does not match the vector length."
            )

        if (
            vector_length
            != self.expected_embedding_dimension
        ):
            raise M2EmbeddingContractError(
                "M2 returned an embedding with an "
                "unexpected dimension."
            )

        if (
            embedded
            .processed_query
            .embedding
            != embedded.embedding
        ):
            raise M2EmbeddingContractError(
                "ProcessedQuery.embedding must mirror "
                "EmbeddedQuery.embedding for the "
                "M2 -> M3 handoff."
            )

        if (
            embedded
            .processed_query
            .sparse_embedding
            != embedded.sparse_embedding
        ):
            raise M2EmbeddingContractError(
                "ProcessedQuery.sparse_embedding must "
                "mirror EmbeddedQuery.sparse_embedding "
                "for the M2 -> M3 handoff."
            )

    def _validate_retrieval_policy(
        self,
    ) -> None:

        searcher = getattr(
            self.retrieval_pipeline,
            "hybrid_searcher",
            None,
        )

        if searcher is None:
            raise P4RetrievalPolicyError(
                "Package 4 requires an M3 pipeline "
                "exposing HybridSearcher lifecycle "
                "policy."
            )

        statuses = getattr(
            searcher,
            "allowed_validity_statuses",
            None,
        )

        normalized = {
            str(status).strip().lower()
            for status in (statuses or [])
            if str(status).strip()
        }

        if normalized != {
            ValidityStatus.CURRENT.value
        }:
            raise P4RetrievalPolicyError(
                "Package 4 M3 retrieval must allow "
                "only validity_status='current'."
            )

        if (
            getattr(
                searcher,
                "include_unversioned_points",
                None,
            )
            is not False
        ):
            raise P4RetrievalPolicyError(
                "Package 4 M3 retrieval must exclude "
                "unversioned points."
            )

    @staticmethod
    def _validate_retrieved_evidence(
        *,
        processed_query: ProcessedQuery,
        evidence: RetrievedEvidence,
    ) -> None:

        if (
            evidence.query_id
            != processed_query.query_id
        ):
            raise P4RetrievalContractError(
                "M3 RetrievedEvidence.query_id must "
                "match the M2 ProcessedQuery.query_id."
            )

    def _build_answer_request(
        self,
        *,
        question: str,
        request_id: str | None,
        response_language: (
            ResponseLanguage
            | str
            | None
        ),
        processed_query: ProcessedQuery,
        evidence: RetrievedEvidence,
        safe_context: Sequence[
            SafeContextTurn
        ],
        response_instructions: Sequence[
            str
        ],
    ) -> AnswerGenerationRequest:

        selected_language = (
            response_language
        )

        if selected_language is None:
            if processed_query.language in {
                "ar",
                "en",
                "ar-en",
            }:
                selected_language = (
                    processed_query.language
                )

            else:
                # M6 maps None to English.
                selected_language = None

        record_statuses: list[
            ValidityStatus
        ] = []

        if evidence.retrieved_evidence:
            # All evidence crossing this boundary is
            # CURRENT because the M3 configuration above
            # is enforced fail-closed.
            record_statuses = [
                ValidityStatus.CURRENT
            ]

        return (
            self.knowledge_service
            .build_answer_request(
                request_id=(
                    request_id
                    or (
                        "p4_"
                        + uuid.uuid4().hex[:12]
                    )
                ),
                original_query=question,
                response_language=(
                    selected_language
                ),
                retrieved_evidence=evidence,
                record_statuses=(
                    record_statuses
                ),
                safe_context=list(
                    safe_context
                ),
                response_instructions=list(
                    response_instructions
                ),
            )
        )

    @staticmethod
    def _result(
        *,
        processed_query: ProcessedQuery,
        answer_request: (
            AnswerGenerationRequest
        ),
        evidence: RetrievedEvidence,
        retrieval_ms: float,
        orchestration: P4OrchestrationResult,
    ) -> P4ChatResult:

        return P4ChatResult(
            response=(
                orchestration.response
            ),
            processed_query=(
                processed_query
            ),
            answer_request=(
                answer_request
            ),
            metrics=P4ChatMetrics(
                retrieval_ms=retrieval_ms,
                evidence_count=len(
                    evidence.retrieved_evidence
                ),
                generation_invoked=(
                    orchestration
                    .metrics
                    .generation_invoked
                ),
                citation_count=(
                    orchestration
                    .metrics
                    .citation_count
                ),
            ),
        )
