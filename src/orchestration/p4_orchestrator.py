"""
Package 4 M4 orchestration.

Implements:

    AnswerGenerationRequest
        ->
    grounded Qwen generation
        ->
    trusted citation resolution
        ->
    semantic claim grounding validation
        ->
    ValidatedAIResponse

The existing Packages 1/2 M4OrchestrationService remains unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.orchestration.citation_validator import (
    CitationValidationError,
    CitationValidator,
)
from src.orchestration.llm_service import (
    M4LLMService,
)
from src.orchestration.p4_grounding_validator import (
    P4GroundingValidator,
)
from src.orchestration.p4_prompt_builder import (
    P4PromptBuilder,
)
from src.orchestration.settings import M4Settings
from src.schemas.p4_chat_contract import (
    AnswerGenerationRequest,
    ResponseLanguage,
    ValidatedAIResponse,
)


@dataclass(frozen=True)
class P4OrchestrationMetrics:
    generation_invoked: bool
    grounding_validation_invoked: bool

    evidence_count: int
    citation_count: int


@dataclass(frozen=True)
class P4OrchestrationResult:
    response: ValidatedAIResponse
    metrics: P4OrchestrationMetrics

class P4GroundingValidationError(
    RuntimeError
):
    """
    Raised when generated Package 4 content
    fails semantic grounding validation.
    """
class P4M4Orchestrator:
    """
    Package 4 M4 generation and validation service.
    """

    def __init__(
        self,
        settings: M4Settings | None = None,
        *,
        prompt_builder: P4PromptBuilder | None = None,
        llm_service: M4LLMService | None = None,
        citation_validator: CitationValidator | None = None,
        grounding_validator: (
            P4GroundingValidator | None
        ) = None,
    ) -> None:
        self.settings = settings or M4Settings()

        self.prompt_builder = (
            prompt_builder
            or P4PromptBuilder()
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

        self.grounding_validator = (
            grounding_validator
            or P4GroundingValidator()
        )

    def answer(
        self,
        request: AnswerGenerationRequest,
    ) -> P4OrchestrationResult:
        """
        Generate and validate a Package 4 answer synchronously.
        """

        if not request.evidence_sufficient:
            return self._insufficient_response(
                request
            )

        bundle = self.prompt_builder.build(
            request
        )

        model_output = self.llm_service.invoke(
            bundle.messages
        )

        citations = self.citation_validator.validate(
            model_output=model_output,
            evidence_by_id=bundle.evidence_by_id,
        )

        if not citations:
            raise CitationValidationError(
                "A Package 4 grounded answer requires "
                "at least one trusted citation."
            )

        grounding = (
            self.grounding_validator.validate(
                model_output=model_output,
                evidence_by_id=(
                    bundle.evidence_by_id
                ),
            )
        )
        if not grounding.grounded:
            raise P4GroundingValidationError(
                "The generated answer failed "
                "semantic grounding validation."
            )

        response = ValidatedAIResponse(
            request_id=request.request_id,
            query_id=request.query_id,
            answer=model_output.answer,
            citations=citations,
            confidence=model_output.confidence,
            insufficient_evidence=False,
            grounding_valid=grounding.grounded,
            citations_valid=True,
            structured_output_valid=True,
            unsupported_claims=list(
                grounding.unsupported_claims
            ),
            validation_errors=list(
                grounding.errors
            ),
            model_tag=self.settings.model_name,
            prompt_version=(
                bundle.prompt_version
            ),
        )

        return P4OrchestrationResult(
            response=response,
            metrics=P4OrchestrationMetrics(
                generation_invoked=True,
                grounding_validation_invoked=True,
                evidence_count=len(
                    request
                    .retrieved_evidence
                    .retrieved_evidence
                ),
                citation_count=len(citations),
            ),
        )

    async def aanswer(
        self,
        request: AnswerGenerationRequest,
    ) -> P4OrchestrationResult:
        """
        Generate and validate a Package 4 answer asynchronously.
        """

        if not request.evidence_sufficient:
            return self._insufficient_response(
                request
            )

        bundle = self.prompt_builder.build(
            request
        )

        model_output = (
            await self.llm_service.ainvoke(
                bundle.messages
            )
        )

        citations = self.citation_validator.validate(
            model_output=model_output,
            evidence_by_id=bundle.evidence_by_id,
        )

        if not citations:
            raise CitationValidationError(
                "A Package 4 grounded answer requires "
                "at least one trusted citation."
            )

        grounding = (
            await self.grounding_validator.avalidate(
                model_output=model_output,
                evidence_by_id=(
                    bundle.evidence_by_id
                ),
            )
        )
        if not grounding.grounded:
            raise P4GroundingValidationError(
                "The generated answer failed "
                "semantic grounding validation."
            )

        response = ValidatedAIResponse(
            request_id=request.request_id,
            query_id=request.query_id,
            answer=model_output.answer,
            citations=citations,
            confidence=model_output.confidence,
            insufficient_evidence=False,
            grounding_valid=grounding.grounded,
            citations_valid=True,
            structured_output_valid=True,
            unsupported_claims=list(
                grounding.unsupported_claims
            ),
            validation_errors=list(
                grounding.errors
            ),
            model_tag=self.settings.model_name,
            prompt_version=(
                bundle.prompt_version
            ),
        )

        return P4OrchestrationResult(
            response=response,
            metrics=P4OrchestrationMetrics(
                generation_invoked=True,
                grounding_validation_invoked=True,
                evidence_count=len(
                    request
                    .retrieved_evidence
                    .retrieved_evidence
                ),
                citation_count=len(citations),
            ),
        )

    def _insufficient_response(
        self,
        request: AnswerGenerationRequest,
    ) -> P4OrchestrationResult:
        """
        Deterministic abstention.

        No Qwen call occurs when M6 has already determined that
        evidence is insufficient.
        """

        answer = self._insufficient_message(
            request.response_language
        )

        response = ValidatedAIResponse(
            request_id=request.request_id,
            query_id=request.query_id,
            answer=answer,
            citations=[],
            confidence=0.0,
            insufficient_evidence=True,
            grounding_valid=True,
            citations_valid=True,
            structured_output_valid=True,
            unsupported_claims=[],
            validation_errors=[],
            model_tag=self.settings.model_name,
            prompt_version=(
                self.prompt_builder
                .prompt
                .version
            ),
        )

        return P4OrchestrationResult(
            response=response,
            metrics=P4OrchestrationMetrics(
                generation_invoked=False,
                grounding_validation_invoked=False,
                evidence_count=len(
                    request
                    .retrieved_evidence
                    .retrieved_evidence
                ),
                citation_count=0,
            ),
        )

    def _insufficient_message(
        self,
        language: ResponseLanguage,
    ) -> str:
        if language == ResponseLanguage.ARABIC:
            return (
                "الأدلة القانونية المعتمدة المتاحة "
                "غير كافية للإجابة عن هذا السؤال."
            )

        if language == ResponseLanguage.MIXED:
            return (
                "الأدلة القانونية المعتمدة غير كافية "
                "للإجابة عن السؤال. "
                "The available trusted legal evidence "
                "is insufficient to answer."
            )

        return (
            "The available trusted legal evidence is "
            "insufficient to answer this question."
        )
