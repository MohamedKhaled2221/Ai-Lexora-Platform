from __future__ import annotations

from datetime import datetime, timezone

from src.schemas.m6_knowledge import (
    KnowledgeRecord,
    ReviewMetadata,
    ValidityStatus,
)


class KnowledgeGovernanceService:
    """Manage legal freshness, supersession, and human review state."""

    def mark_for_review(
        self,
        record: KnowledgeRecord,
        reason: str,
    ) -> KnowledgeRecord:
        record.validity_status = ValidityStatus.REVIEW_REQUIRED
        record.review = ReviewMetadata(
            review_outcome=reason,
            reviewer=None,
            reviewed_at=None,
        )
        record.updated_at = datetime.now(timezone.utc)

        return record

    def mark_superseded(
        self,
        record: KnowledgeRecord,
        superseded_by_record_id: str,
    ) -> KnowledgeRecord:
        record.validity_status = ValidityStatus.SUPERSEDED
        record.superseded_by_record_id = superseded_by_record_id
        record.updated_at = datetime.now(timezone.utc)

        return record

    def approve_current(
        self,
        record: KnowledgeRecord,
        reviewer: str,
        outcome: str = "approved",
    ) -> KnowledgeRecord:
        record.validity_status = ValidityStatus.CURRENT
        record.review = ReviewMetadata(
            review_outcome=outcome,
            reviewer=reviewer,
            reviewed_at=datetime.now(timezone.utc),
        )
        record.updated_at = datetime.now(timezone.utc)

        return record

    def can_be_used_for_answer(
        self,
        record: KnowledgeRecord,
    ) -> bool:
        return record.validity_status == ValidityStatus.CURRENT