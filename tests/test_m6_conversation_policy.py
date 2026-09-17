import pytest

from src.knowledge.conversation_policy import (
    ConversationPolicyService,
)
from src.schemas.m6_knowledge import (
    EvidenceSufficiencyResult,
    ValidityStatus,
)
from src.schemas.p4_chat_contract import (
    ResponseLanguage,
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
        missing_information=[
            "Relevant article"
        ],
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

    assert (
        decision.response_language
        == ResponseLanguage.ARABIC
    )

    assert (
        decision.allow_generation
        is False
    )

    assert (
        decision.requires_follow_up
        is True
    )


def test_policy_requires_review_for_review_required_records():
    service = ConversationPolicyService()

    decision = service.decide(
        requested_language="en",
        evidence_result=sufficient(),
        record_statuses=[
            ValidityStatus.REVIEW_REQUIRED
        ],
        has_follow_up_context=False,
    )

    assert (
        decision.allow_generation
        is False
    )

    assert (
        decision.requires_follow_up
        is True
    )


def test_policy_blocks_superseded_reference():
    service = ConversationPolicyService()

    decision = service.decide(
        requested_language="en",
        evidence_result=sufficient(),
        record_statuses=[
            ValidityStatus.SUPERSEDED
        ],
        has_follow_up_context=False,
    )

    assert (
        decision.allow_generation
        is False
    )

    assert (
        decision.requires_follow_up
        is True
    )

    assert (
        "superseded"
        in decision.reason.lower()
    )


def test_policy_preserves_language_preference():
    service = ConversationPolicyService()

    decision = service.decide(
        requested_language=" ar ",
        evidence_result=sufficient(),
        record_statuses=[],
        has_follow_up_context=False,
    )

    assert (
        decision.response_language
        == ResponseLanguage.ARABIC
    )


def test_policy_maps_m2_mixed_language():
    service = ConversationPolicyService()

    decision = service.decide(
        requested_language="ar-en",
        evidence_result=sufficient(),
        record_statuses=[],
        has_follow_up_context=False,
    )

    assert (
        decision.response_language
        == ResponseLanguage.MIXED
    )


def test_policy_rejects_unsupported_language():
    service = ConversationPolicyService()

    with pytest.raises(
        ValueError,
        match=(
            "Unsupported response language"
        ),
    ):
        service.decide(
            requested_language="fr",
            evidence_result=sufficient(),
            record_statuses=[],
            has_follow_up_context=False,
        )