"""
Approval Workflow — سير عمل اعتماد البنود القانونية.

يدير دورة حياة اعتماد البند من Draft إلى Approved
مع دعم تعديلات المحامين وإعادة الاعتماد.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from src.clause_engine.clause_library import (
    ClauseLibrary,
)
from src.schemas.m5_contract import (
    ApprovalEvent,
    ApprovalStatus,
    ApprovedClause,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Valid State Transitions
# ──────────────────────────────────────────────

_VALID_TRANSITIONS: dict[
    ApprovalStatus, set[ApprovalStatus]
] = {
    ApprovalStatus.DRAFT: {
        ApprovalStatus.PENDING_REVIEW,
    },
    ApprovalStatus.PENDING_REVIEW: {
        ApprovalStatus.APPROVED,
        ApprovalStatus.REJECTED,
    },
    ApprovalStatus.APPROVED: {
        ApprovalStatus.SUPERSEDED,
        ApprovalStatus.EXPIRED,
        ApprovalStatus.LAWYER_EDITED,
    },
    ApprovalStatus.REJECTED: {
        ApprovalStatus.DRAFT,
    },
    ApprovalStatus.LAWYER_EDITED: {
        ApprovalStatus.PENDING_REVIEW,
    },
    ApprovalStatus.SUPERSEDED: set(),
    ApprovalStatus.EXPIRED: set(),
}


class ApprovalWorkflowError(Exception):
    """خطأ في سير عمل الاعتماد."""


class InvalidTransitionError(ApprovalWorkflowError):
    """انتقال غير صالح بين حالات الاعتماد."""


class ApprovalWorkflow:
    """
    سير عمل اعتماد البنود القانونية.

    State Machine:
        DRAFT → PENDING_REVIEW → APPROVED → (SUPERSEDED | EXPIRED)
                               ↘ REJECTED → DRAFT
        APPROVED → LAWYER_EDITED → PENDING_REVIEW → APPROVED

    القواعد:
    - البند المعدل من محامي يحتاج إعادة اعتماد قبل إعادة الاستخدام
    - لا يمكن استخدام بند في حالة DRAFT أو REJECTED أو SUPERSEDED
    - كل تغيير حالة يُسجَّل في سجل الأحداث
    """

    def __init__(
        self,
        clause_library: ClauseLibrary,
    ) -> None:
        self._clause_library = clause_library
        self._history: list[ApprovalEvent] = []

    @property
    def history(self) -> list[ApprovalEvent]:
        """سجل الأحداث."""
        return list(self._history)

    def submit_for_review(
        self,
        clause_id: str,
        actor: str = "system",
    ) -> ApprovedClause:
        """
        تقديم بند للمراجعة.

        DRAFT → PENDING_REVIEW
        """
        return self._transition(
            clause_id=clause_id,
            to_status=ApprovalStatus.PENDING_REVIEW,
            action="submit",
            actor=actor,
            reason="Submitted for review",
        )

    def approve(
        self,
        clause_id: str,
        approver: str,
        reason: str = "",
    ) -> ApprovedClause:
        """
        اعتماد بند.

        PENDING_REVIEW → APPROVED
        """
        clause = self._transition(
            clause_id=clause_id,
            to_status=ApprovalStatus.APPROVED,
            action="approve",
            actor=approver,
            reason=reason or "Approved",
        )

        return clause

    def reject(
        self,
        clause_id: str,
        actor: str,
        reason: str,
    ) -> ApprovedClause:
        """
        رفض بند.

        PENDING_REVIEW → REJECTED
        """
        if not reason.strip():
            raise ApprovalWorkflowError(
                "Rejection reason is required"
            )

        return self._transition(
            clause_id=clause_id,
            to_status=ApprovalStatus.REJECTED,
            action="reject",
            actor=actor,
            reason=reason,
        )

    def mark_as_expired(
        self,
        clause_id: str,
        actor: str = "system",
    ) -> ApprovedClause:
        """
        تعليم بند كمنتهي الصلاحية.

        APPROVED → EXPIRED
        """
        return self._transition(
            clause_id=clause_id,
            to_status=ApprovalStatus.EXPIRED,
            action="expire",
            actor=actor,
            reason="Clause expired",
        )

    def mark_as_lawyer_edited(
        self,
        clause_id: str,
        editor: str,
        reason: str = "",
    ) -> ApprovedClause:
        """
        تعليم بند كمعدَّل من محامٍ.

        APPROVED → LAWYER_EDITED

        البند المعدل لا يمكن إعادة استخدامه
        إلا بعد إعادة اعتماد منفصلة.
        """
        clause = self._transition(
            clause_id=clause_id,
            to_status=ApprovalStatus.LAWYER_EDITED,
            action="lawyer_edit",
            actor=editor,
            reason=reason or "Edited by lawyer",
        )

        # Mark clause as requiring separate approval
        clause = self._clause_library.update_clause(
            clause_id,
            is_lawyer_edited=True,
            requires_separate_approval=True,
        )

        return clause

    def request_reapproval(
        self,
        clause_id: str,
        actor: str = "system",
    ) -> ApprovedClause:
        """
        طلب إعادة اعتماد بند معدَّل.

        LAWYER_EDITED → PENDING_REVIEW
        """
        return self._transition(
            clause_id=clause_id,
            to_status=ApprovalStatus.PENDING_REVIEW,
            action="reapproval_request",
            actor=actor,
            reason="Reapproval requested for lawyer-edited clause",
        )

    def return_to_draft(
        self,
        clause_id: str,
        actor: str = "system",
        reason: str = "",
    ) -> ApprovedClause:
        """
        إرجاع بند مرفوض إلى مسودة.

        REJECTED → DRAFT
        """
        return self._transition(
            clause_id=clause_id,
            to_status=ApprovalStatus.DRAFT,
            action="return_to_draft",
            actor=actor,
            reason=reason or "Returned to draft for revision",
        )

    def get_pending_reviews(self) -> list[ApprovedClause]:
        """استرجاع البنود المعلقة للمراجعة."""
        return self._clause_library.search_clauses(
            approval_status=ApprovalStatus.PENDING_REVIEW
        )

    def get_approval_history(
        self,
        clause_id: str,
    ) -> list[ApprovalEvent]:
        """استرجاع سجل اعتماد بند معين."""
        return [
            event
            for event in self._history
            if event.clause_id == clause_id
        ]

    def _transition(
        self,
        *,
        clause_id: str,
        to_status: ApprovalStatus,
        action: str,
        actor: str,
        reason: str,
    ) -> ApprovedClause:
        """
        تنفيذ انتقال حالة.

        يتحقق من صلاحية الانتقال ويسجل الحدث.
        """
        clause = self._clause_library.get_clause(clause_id)
        from_status = clause.approval_status

        self._validate_transition(
            from_status=from_status,
            to_status=to_status,
        )

        updated_clause = self._clause_library.update_clause(
            clause_id,
            approval_status=to_status,
        )

        event = ApprovalEvent(
            event_id=f"EVT-{uuid.uuid4().hex[:12]}",
            clause_id=clause_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            reason=reason,
        )
        self._history.append(event)

        logger.info(
            "Clause %s: %s → %s (by %s)",
            clause_id,
            from_status.value,
            to_status.value,
            actor,
        )

        return updated_clause

    def _validate_transition(
        self,
        *,
        from_status: ApprovalStatus,
        to_status: ApprovalStatus,
    ) -> None:
        """التحقق من صلاحية انتقال الحالة."""
        valid_targets = _VALID_TRANSITIONS.get(
            from_status, set()
        )

        if to_status not in valid_targets:
            raise InvalidTransitionError(
                f"Invalid transition: "
                f"{from_status.value} → {to_status.value}. "
                f"Valid targets: "
                f"{[s.value for s in valid_targets]}"
            )
