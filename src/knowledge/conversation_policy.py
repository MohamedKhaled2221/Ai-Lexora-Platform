from __future__ import annotations

from dataclasses import dataclass

from src.schemas.m6_knowledge import (
    EvidenceSufficiencyResult,
    ValidityStatus,
)
from src.schemas.p4_chat_contract import (
    ResponseLanguage,
)


@dataclass(frozen=True)
class ConversationPolicyDecision:
    response_language: ResponseLanguage
    allow_generation: bool
    requires_follow_up: bool
    use_safe_follow_up_context: bool
    reason: str


class ConversationPolicyService:
    """
    M6 policy layer for:

    - response-language selection;
    - evidence sufficiency;
    - safe follow-up context;
    - legal-record lifecycle status.

    Only CURRENT legal evidence may support a normal
    grounded Package 4 answer.
    """

    def decide(
        self,
        *,
        requested_language: (
            ResponseLanguage
            | str
            | None
        ),
        evidence_result: (
            EvidenceSufficiencyResult
        ),
        record_statuses: list[
            ValidityStatus
        ],
        has_follow_up_context: bool,
    ) -> ConversationPolicyDecision:

        language = self._normalize_language(
            requested_language
        )

        if not evidence_result.sufficient:
            return ConversationPolicyDecision(
                response_language=language,
                allow_generation=False,
                requires_follow_up=True,
                use_safe_follow_up_context=(
                    has_follow_up_context
                ),
                reason=(
                    "Evidence is insufficient for "
                    "a grounded answer."
                ),
            )

        if (
            ValidityStatus.REVIEW_REQUIRED
            in record_statuses
        ):
            return ConversationPolicyDecision(
                response_language=language,
                allow_generation=False,
                requires_follow_up=True,
                use_safe_follow_up_context=(
                    has_follow_up_context
                ),
                reason=(
                    "One or more legal records "
                    "require review."
                ),
            )

        if (
            ValidityStatus.SUPERSEDED
            in record_statuses
        ):
            return ConversationPolicyDecision(
                response_language=language,
                allow_generation=False,
                requires_follow_up=True,
                use_safe_follow_up_context=(
                    has_follow_up_context
                ),
                reason=(
                    "One or more legal records are "
                    "superseded and cannot support "
                    "a current grounded answer."
                ),
            )

        return ConversationPolicyDecision(
            response_language=language,
            allow_generation=True,
            requires_follow_up=False,
            use_safe_follow_up_context=(
                has_follow_up_context
            ),
            reason=(
                "Evidence is sufficient and current."
            ),
        )

    @staticmethod
    def _normalize_language(
        requested_language: (
            ResponseLanguage
            | str
            | None
        ),
    ) -> ResponseLanguage:

        if requested_language is None:
            return ResponseLanguage.ENGLISH

        if isinstance(
            requested_language,
            ResponseLanguage,
        ):
            return requested_language

        value = (
            str(requested_language)
            .strip()
            .lower()
        )

        # M2 uses "ar-en" for mixed Arabic-English
        # queries. Package 4 calls this "mixed".
        if value == "ar-en":
            value = (
                ResponseLanguage.MIXED.value
            )

        try:
            return ResponseLanguage(value)

        except ValueError as exc:
            raise ValueError(
                "Unsupported response language: "
                f"{requested_language!r}"
            ) from exc