from src.knowledge.conversation_policy import ConversationPolicyService
from src.schemas.m6_knowledge import (
    EvidenceSufficiencyResult,
    ValidityStatus,
)


def sufficient():
    return EvidenceSufficiencyResult(
        sufficient=True,
        score=0.9,
        reason="Enough evidence.",
    )


def insufficient():
    return EvidenceSufficiencyResult(
        sufficient=False,
        score=0.2,
        reason="Not enough evidence.",
        missing_information=["Relevant article"],
        requires_follow_up=True,
    )


def test_policy_blocks_generation_when_evidence_is_insufficient():
    service = ConversationPolicyService()

    decision = service.decide(
        requested_language="ar",
        evidence_result=insufficient(),
        record_statuses=[],
        has_follow_up_context=True,
    )

    assert decision.response_language == "ar"
    assert decision.allow_generation is False
    assert decision.requires_follow_up is True


def test_policy_requires_review_for_review_required_records():
    service = ConversationPolicyService()

    decision = service.decide(
        requested_language="en",
        evidence_result=sufficient(),
        record_statuses=[ValidityStatus.REVIEW_REQUIRED],
        has_follow_up_context=False,
    )

    assert decision.allow_generation is False
    assert decision.requires_follow_up is True


def test_policy_handles_superseded_reference():
    service = ConversationPolicyService()

    decision = service.decide(
        requested_language="en",
        evidence_result=sufficient(),
        record_statuses=[ValidityStatus.SUPERSEDED],
        has_follow_up_context=False,
    )

    assert decision.allow_generation is True
    assert "Superseded" in decision.reason


def test_policy_preserves_language_preference():
    service = ConversationPolicyService()

    decision = service.decide(
        requested_language=" ar ",
        evidence_result=sufficient(),
        record_statuses=[],
        has_follow_up_context=False,
    )

    assert decision.response_language == "ar"