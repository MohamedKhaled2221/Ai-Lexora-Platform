from __future__ import annotations

from dataclasses import dataclass

from src.schemas.m6_knowledge import (
    EvidenceSufficiencyResult,
    ValidityStatus,
)


@dataclass(frozen=True)
class ConversationPolicyDecision:
    response_language: str
    allow_generation: bool
    requires_follow_up: bool
    use_safe_follow_up_context: bool
    reason: str


class ConversationPolicyService:
    """
    M6 policy layer for language preference, evidence sufficiency,
    follow-up context, and outdated legal references.
    """

    def decide(
        self,
        *,
        requested_language: str | None,
        evidence_result: EvidenceSufficiencyResult,
        record_statuses: list[ValidityStatus],
        has_follow_up_context: bool,
    ) -> ConversationPolicyDecision:

        language = (
            requested_language.strip()
            if requested_language
            else "en"
        )

        if not evidence_result.sufficient:
            return ConversationPolicyDecision(
                response_language=language,
                allow_generation=False,
                requires_follow_up=True,
                use_safe_follow_up_context=has_follow_up_context,
                reason="Evidence is insufficient for a grounded answer.",
            )

        if ValidityStatus.REVIEW_REQUIRED in record_statuses:
            return ConversationPolicyDecision(
                response_language=language,
                allow_generation=False,
                requires_follow_up=True,
                use_safe_follow_up_context=has_follow_up_context,
                reason="One or more legal records require review.",
            )

        if ValidityStatus.SUPERSEDED in record_statuses:
            return ConversationPolicyDecision(
                response_language=language,
                allow_generation=True,
                requires_follow_up=False,
                use_safe_follow_up_context=has_follow_up_context,
                reason="Superseded references must not be treated as current.",
            )

        return ConversationPolicyDecision(
            response_language=language,
            allow_generation=True,
            requires_follow_up=False,
            use_safe_follow_up_context=has_follow_up_context,
            reason="Evidence is sufficient and current.",
        )