import asyncio
import time
from dataclasses import dataclass

from src.orchestration.service import M4OrchestrationService
from src.pipeline import M3RetrievalPipeline
from src.schemas.m2_contract import ProcessedQuery
from src.schemas.m4_contract import AIResponse


@dataclass(frozen=True)
class RAGExecutionMetrics:
    """
    Internal execution metrics for one M3 -> M4 RAG request.

    These metrics are for observability only and are
    intentionally not part of the public AIResponse contract.
    """

    retrieval_ms: float
    generation_ms: float
    total_rag_ms: float
    retrieved_chunk_count: int
    citation_count: int


@dataclass(frozen=True)
class RAGExecutionResult:
    """
    Internal result wrapper containing the normal AIResponse
    together with execution metrics.
    """

    response: AIResponse
    metrics: RAGExecutionMetrics


class M3M4RAGService:
    """
    Compose M3 retrieval with M4 grounded answer generation.

    Flow:
        ProcessedQuery
            -> M3RetrievalPipeline
            -> RetrievedEvidence
            -> M4OrchestrationService
            -> AIResponse

    The normal answer()/aanswer() methods preserve the existing
    public behavior.

    The answer_with_metrics()/aanswer_with_metrics() methods are
    used internally when observability information is required.
    """

    def __init__(
        self,
        *,
        retrieval_pipeline: M3RetrievalPipeline,
        orchestration_service: M4OrchestrationService,
    ) -> None:
        self.retrieval_pipeline = retrieval_pipeline
        self.orchestration_service = orchestration_service

    def answer(
        self,
        processed_query: ProcessedQuery,
    ) -> AIResponse:
        """
        Run the synchronous RAG pipeline and return only
        the public AIResponse.
        """

        result = self.answer_with_metrics(
            processed_query
        )

        return result.response

    def answer_with_metrics(
        self,
        processed_query: ProcessedQuery,
    ) -> RAGExecutionResult:
        """
        Run synchronous M3 retrieval followed by M4 generation
        and collect internal execution metrics.
        """

        total_start = time.perf_counter()

        (
            retrieved_evidence,
            retrieval_ms,
        ) = self.retrieval_pipeline.run(
            processed_query
        )

        generation_start = time.perf_counter()

        response = (
            self.orchestration_service
            .answer_search(
                processed_query=processed_query,
                retrieved_evidence=retrieved_evidence,
            )
        )

        generation_ms = (
            time.perf_counter()
            - generation_start
        ) * 1000.0

        total_rag_ms = (
            time.perf_counter()
            - total_start
        ) * 1000.0

        metrics = RAGExecutionMetrics(
            retrieval_ms=round(
                retrieval_ms,
                2,
            ),
            generation_ms=round(
                generation_ms,
                2,
            ),
            total_rag_ms=round(
                total_rag_ms,
                2,
            ),
            retrieved_chunk_count=len(
                retrieved_evidence.retrieved_evidence
            ),
            citation_count=len(
                response.citations
            ),
        )

        return RAGExecutionResult(
            response=response,
            metrics=metrics,
        )

    async def aanswer(
        self,
        processed_query: ProcessedQuery,
    ) -> AIResponse:
        """
        Run the asynchronous RAG pipeline and return only
        the public AIResponse.
        """

        result = await self.aanswer_with_metrics(
            processed_query
        )

        return result.response

    async def aanswer_with_metrics(
        self,
        processed_query: ProcessedQuery,
    ) -> RAGExecutionResult:
        """
        Run M3 retrieval outside the asyncio event loop,
        then asynchronously execute M4 generation while
        collecting internal execution metrics.
        """

        total_start = time.perf_counter()

        (
            retrieved_evidence,
            retrieval_ms,
        ) = await asyncio.to_thread(
            self.retrieval_pipeline.run,
            processed_query,
        )

        generation_start = time.perf_counter()

        response = await (
            self.orchestration_service
            .aanswer_search(
                processed_query=processed_query,
                retrieved_evidence=retrieved_evidence,
            )
        )

        generation_ms = (
            time.perf_counter()
            - generation_start
        ) * 1000.0

        total_rag_ms = (
            time.perf_counter()
            - total_start
        ) * 1000.0

        metrics = RAGExecutionMetrics(
            retrieval_ms=round(
                retrieval_ms,
                2,
            ),
            generation_ms=round(
                generation_ms,
                2,
            ),
            total_rag_ms=round(
                total_rag_ms,
                2,
            ),
            retrieved_chunk_count=len(
                retrieved_evidence.retrieved_evidence
            ),
            citation_count=len(
                response.citations
            ),
        )

        return RAGExecutionResult(
            response=response,
            metrics=metrics,
        )
