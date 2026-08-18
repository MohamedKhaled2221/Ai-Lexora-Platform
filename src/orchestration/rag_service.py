import asyncio
from src.orchestration.service import M4OrchestrationService
from src.pipeline import M3RetrievalPipeline
from src.schemas.m2_contract import ProcessedQuery
from src.schemas.m4_contract import AIResponse


class M3M4RAGService:
    """
    Composes the M3 retrieval pipeline with M4 answer generation.

    Flow:
        ProcessedQuery
            -> M3RetrievalPipeline
            -> RetrievedEvidence
            -> M4OrchestrationService
            -> AIResponse

    M3 and M4 remain independently testable components.
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
        retrieved_evidence, _ = self.retrieval_pipeline.run(
            processed_query
        )

        return self.orchestration_service.answer_search(
            processed_query=processed_query,
            retrieved_evidence=retrieved_evidence,
        )

    async def aanswer(
        self,
        processed_query: ProcessedQuery,
    ) -> AIResponse:
        retrieved_evidence, _ = (
            await asyncio.to_thread(
                self.retrieval_pipeline.run,
                processed_query,
            )
        )

        return await (
            self.orchestration_service
            .aanswer_search(
                processed_query=processed_query,
                retrieved_evidence=(
                    retrieved_evidence
                ),
            )
        )