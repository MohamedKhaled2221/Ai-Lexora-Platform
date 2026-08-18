from src.orchestration.citation_validator import CitationValidator
from src.orchestration.llm_service import M4LLMService
from src.orchestration.prompts import M4PromptBuilder
from src.orchestration.settings import M4Settings
from src.schemas.m2_contract import ProcessedQuery
from src.schemas.m4_contract import AIResponse, RetrievedEvidence


class M4OrchestrationService:
    """
    High-level orchestration service for grounded legal question answering.

    This service owns the complete M4 search-generation workflow:

        ProcessedQuery + RetrievedEvidence
            -> grounded prompt
            -> structured local LLM generation
            -> trusted citation validation
            -> AIResponse

    Retrieval remains an upstream M3 responsibility.
    """

    def __init__(
        self,
        settings: M4Settings | None = None,
        *,
        prompt_builder: M4PromptBuilder | None = None,
        llm_service: M4LLMService | None = None,
        citation_validator: CitationValidator | None = None,
    ) -> None:
        self.settings = settings or M4Settings()

        self.prompt_builder = (
            prompt_builder
            or M4PromptBuilder()
        )

        self.llm_service = (
            llm_service
            or M4LLMService(
                settings=self.settings
            )
        )

        self.citation_validator = (
            citation_validator
            or CitationValidator()
        )

    def answer_search(
        self,
        processed_query: ProcessedQuery,
        retrieved_evidence: RetrievedEvidence,
    ) -> AIResponse:
        """
        Generate a grounded answer synchronously.
        """

        self._validate_query_alignment(
            processed_query=processed_query,
            retrieved_evidence=retrieved_evidence,
        )

        if not retrieved_evidence.retrieved_evidence:
            return self._build_insufficient_evidence_response(
                processed_query
            )

        bundle = self.prompt_builder.build_search_prompt(
            processed_query=processed_query,
            retrieved_evidence=retrieved_evidence,
        )

        model_output = self.llm_service.invoke(
            bundle.messages
        )

        citations = self.citation_validator.validate(
            model_output=model_output,
            evidence_by_id=bundle.evidence_by_id,
        )

        return AIResponse(
            query_id=processed_query.query_id,
            answer=model_output.answer,
            citations=citations,
            confidence=model_output.confidence,
        )

    async def aanswer_search(
        self,
        processed_query: ProcessedQuery,
        retrieved_evidence: RetrievedEvidence,
    ) -> AIResponse:
        """
        Generate a grounded answer asynchronously.
        """

        self._validate_query_alignment(
            processed_query=processed_query,
            retrieved_evidence=retrieved_evidence,
        )

        if not retrieved_evidence.retrieved_evidence:
            return self._build_insufficient_evidence_response(
                processed_query
            )

        bundle = self.prompt_builder.build_search_prompt(
            processed_query=processed_query,
            retrieved_evidence=retrieved_evidence,
        )

        model_output = await self.llm_service.ainvoke(
            bundle.messages
        )

        citations = self.citation_validator.validate(
            model_output=model_output,
            evidence_by_id=bundle.evidence_by_id,
        )

        return AIResponse(
            query_id=processed_query.query_id,
            answer=model_output.answer,
            citations=citations,
            confidence=model_output.confidence,
        )

    def _validate_query_alignment(
        self,
        *,
        processed_query: ProcessedQuery,
        retrieved_evidence: RetrievedEvidence,
    ) -> None:
        if processed_query.query_id != retrieved_evidence.query_id:
            raise ValueError(
                "ProcessedQuery and RetrievedEvidence "
                "must have the same query_id"
            )

    def _build_insufficient_evidence_response(
        self,
        processed_query: ProcessedQuery,
    ) -> AIResponse:
        answer = self._insufficient_evidence_message(
            processed_query.language
        )

        return AIResponse(
            query_id=processed_query.query_id,
            answer=answer,
            citations=[],
            confidence=0.0,
        )

    def _insufficient_evidence_message(
        self,
        language: str,
    ) -> str:
        normalized = language.strip().lower()

        if normalized == "ar":
            return (
                "الأدلة المسترجعة غير كافية للإجابة "
                "عن هذا السؤال."
            )

        if normalized in {
            "mixed",
            "ar-en",
            "en-ar",
            "arabic-english",
            "english-arabic",
        }:
            return (
                "الأدلة المسترجعة غير كافية للإجابة عن السؤال. "
                "The retrieved evidence is insufficient "
                "to answer the question."
            )

        return (
            "The retrieved evidence is insufficient "
            "to answer the question."
        )
