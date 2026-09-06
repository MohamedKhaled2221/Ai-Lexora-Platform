"""
M5 Clause Service — الخدمة الرئيسية لمكتبة البنود المعتمدة.

تجمع كل مكونات M5 وتوفر الـ handoffs لـ M1 و M4.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.clause_engine.approval_workflow import (
    ApprovalWorkflow,
)
from src.clause_engine.clause_library import ClauseLibrary
from src.clause_engine.compatibility_engine import (
    CompatibilityEngine,
)
from src.clause_engine.required_clause_rules import (
    RequiredClauseEngine,
)
from src.clause_engine.special_condition_resolver import (
    SpecialConditionResolver,
)
from src.clause_engine.traceability import ClauseTraceability
from src.clause_engine.versioning import ClauseVersionManager
from src.schemas.m5_contract import (
    ApprovedClause,
    ClauseCompatibilityRule,
    DocumentType,
    Jurisdiction,
    M5ToM1Handoff,
    M5ToM4Handoff,
    SpecialConditionResult,
    ValidationReport,
)

logger = logging.getLogger(__name__)


class M5ClauseService:
    """
    الخدمة الرئيسية لموديول M5 — مكتبة البنود القانونية المعتمدة.

    تجمع كل المكونات وتوفر:
    - M5 → M1 Handoff: بنود معتمدة + قرارات توافق + metadata
    - M5 → M4 Handoff: قواعد التحقق من المصدر والحالة
    - حل الشروط الخاصة
    - فحص وتحقق من مجموعات البنود
    """

    def __init__(
        self,
        *,
        clause_library: ClauseLibrary | None = None,
        compatibility_engine: CompatibilityEngine | None = None,
        required_clause_engine: RequiredClauseEngine | None = None,
        approval_workflow: ApprovalWorkflow | None = None,
        version_manager: ClauseVersionManager | None = None,
        special_condition_resolver: SpecialConditionResolver | None = None,
        traceability: ClauseTraceability | None = None,
        library_path: str | Path | None = None,
        requirements_path: str | Path | None = None,
    ) -> None:

        self.clause_library = (
            clause_library
            or ClauseLibrary(library_path=library_path)
        )

        self.compatibility_engine = (
            compatibility_engine
            or CompatibilityEngine()
        )

        self.required_clause_engine = (
            required_clause_engine
            or RequiredClauseEngine(
                clause_library=self.clause_library,
                requirements_path=requirements_path,
            )
        )

        self.approval_workflow = (
            approval_workflow
            or ApprovalWorkflow(
                clause_library=self.clause_library,
            )
        )

        self.version_manager = (
            version_manager
            or ClauseVersionManager(
                clause_library=self.clause_library,
            )
        )

        self.special_condition_resolver = (
            special_condition_resolver
            or SpecialConditionResolver(
                clause_library=self.clause_library,
            )
        )

        self.traceability = (
            traceability
            or ClauseTraceability(
                clause_library=self.clause_library,
            )
        )

        logger.info(
            "M5ClauseService initialized with %d clauses",
            self.clause_library.clause_count,
        )

    # ──────────────────────────────────────────
    # M5 → M1 Handoff
    # ──────────────────────────────────────────

    def get_clauses_for_document(
        self,
        document_type: DocumentType,
        jurisdiction: Jurisdiction,
    ) -> M5ToM1Handoff:
        """
        استرجاع البنود المعتمدة لنوع عقد وولاية قضائية.

        يرجع M5ToM1Handoff يحتوي:
        - البنود المطلوبة والاختيارية
        - قرارات التوافق المطبقة
        - البيانات المصدرية
        """

        # Get required and optional clauses
        required = self.required_clause_engine.get_required_clauses(
            document_type, jurisdiction
        )
        optional = self.required_clause_engine.get_optional_clauses(
            document_type, jurisdiction
        )

        all_clauses = required + optional

        # Filter to only usable clauses
        usable_clauses = [
            c for c in all_clauses if c.is_usable()
        ]

        # Get applicable compatibility rules
        compatibility_decisions = self._get_applicable_rules(
            usable_clauses
        )

        # Build source metadata
        source_metadata = {
            "document_type": document_type.value,
            "jurisdiction": jurisdiction.value,
            "total_clauses": len(usable_clauses),
            "required_count": len(
                [c for c in required if c.is_usable()]
            ),
            "optional_count": len(
                [c for c in optional if c.is_usable()]
            ),
        }

        return M5ToM1Handoff(
            clauses=usable_clauses,
            compatibility_decisions=compatibility_decisions,
            source_metadata=source_metadata,
        )

    # ──────────────────────────────────────────
    # M5 → M4 Handoff
    # ──────────────────────────────────────────

    def get_provenance_rules(self) -> M5ToM4Handoff:
        """
        استرجاع قواعد التحقق لـ M4 validator.

        يرجع M5ToM4Handoff يحتوي:
        - قواعد التحقق من المصدر (provenance)
        - قواعد التحقق من الحالة (status)
        - سياق التحقق
        """

        provenance_rules = [
            {
                "rule": "clause_must_be_approved",
                "description": (
                    "كل بند مستخدم في المستند يجب أن يكون "
                    "في حالة APPROVED"
                ),
            },
            {
                "rule": "clause_must_not_be_expired",
                "description": (
                    "لا يمكن استخدام بند منتهي الصلاحية"
                ),
            },
            {
                "rule": "clause_must_not_be_superseded",
                "description": (
                    "لا يمكن استخدام بند تم استبداله"
                ),
            },
            {
                "rule": "lawyer_edited_requires_reapproval",
                "description": (
                    "البند المعدل من محامي يحتاج "
                    "إعادة اعتماد قبل الاستخدام"
                ),
            },
        ]

        status_rules = [
            {
                "allowed_statuses": ["approved"],
                "description": (
                    "فقط البنود المعتمدة يمكن استخدامها"
                ),
            },
        ]

        validation_context = {
            "total_approved_clauses": len(
                self.clause_library.get_active_clauses()
            ),
            "total_clauses": self.clause_library.clause_count,
        }

        return M5ToM4Handoff(
            provenance_rules=provenance_rules,
            status_rules=status_rules,
            validation_context=validation_context,
        )

    # ──────────────────────────────────────────
    # Validation
    # ──────────────────────────────────────────

    def validate_clause_set(
        self,
        clause_ids: list[str],
        document_type: DocumentType,
        jurisdiction: Jurisdiction,
    ) -> ValidationReport:
        """
        فحص شامل لمجموعة بنود.

        يتحقق من:
        - اكتمال البنود الإلزامية
        - عدم وجود بنود ممنوعة
        - عدم وجود تعارضات
        - أن كل البنود سارية
        """

        clauses = self.clause_library.get_clauses_by_ids(
            clause_ids
        )

        errors: list[str] = []
        warnings: list[str] = []

        # Check completeness
        completeness = (
            self.required_clause_engine.validate_completeness(
                clause_ids, document_type, jurisdiction
            )
        )

        if not completeness.is_complete:
            errors.extend(completeness.warnings)

        # Check compatibility
        compat_errors = (
            self.compatibility_engine.validate_clause_set_for_document(
                clauses, document_type, jurisdiction
            )
        )
        errors.extend(compat_errors)

        # Check inactive clauses
        inactive = [
            c.clause_id
            for c in clauses
            if not c.is_active()
        ]

        if inactive:
            errors.append(
                f"Inactive clauses: {', '.join(inactive)}"
            )

        # Check lawyer-edited without reapproval
        lawyer_edited_blocked = [
            c.clause_id
            for c in clauses
            if c.is_lawyer_edited
            and c.requires_separate_approval
        ]

        if lawyer_edited_blocked:
            errors.append(
                "Lawyer-edited clauses awaiting reapproval: "
                + ", ".join(lawyer_edited_blocked)
            )

        # Check for missing clause_ids
        found_ids = {c.clause_id for c in clauses}
        missing_ids = [
            cid for cid in clause_ids
            if cid not in found_ids
        ]
        if missing_ids:
            errors.append(
                "Clauses not found: "
                + ", ".join(missing_ids)
            )

        # Find incompatible pairs
        incompatible = (
            self.compatibility_engine.find_incompatible_pairs(
                clauses
            )
        )

        return ValidationReport(
            valid=not errors,
            completeness=completeness,
            incompatible_pairs=incompatible,
            inactive_clauses=inactive,
            errors=errors,
            warnings=warnings,
        )

    # ──────────────────────────────────────────
    # Special Conditions
    # ──────────────────────────────────────────

    def resolve_special_condition(
        self,
        condition: str,
        *,
        jurisdiction: Jurisdiction | None = None,
        document_type: DocumentType | None = None,
    ) -> SpecialConditionResult:
        """
        حل شرط خاص.

        لو مفيش بند مطابق → requires_lawyer_input.
        """
        return self.special_condition_resolver.resolve(
            condition,
            jurisdiction=jurisdiction,
            document_type=document_type,
        )

    # ──────────────────────────────────────────
    # Internal Helpers
    # ──────────────────────────────────────────

    def _get_applicable_rules(
        self,
        clauses: list[ApprovedClause],
    ) -> list[ClauseCompatibilityRule]:
        """استرجاع قواعد التوافق المطبقة على مجموعة بنود."""
        clause_ids = {c.clause_id for c in clauses}
        all_rules = self.compatibility_engine.get_rules()

        return [
            rule
            for rule in all_rules
            if (
                rule.clause_id_a in clause_ids
                or rule.clause_id_b in clause_ids
            )
        ]
