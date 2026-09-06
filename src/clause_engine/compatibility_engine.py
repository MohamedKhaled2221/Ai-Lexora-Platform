"""
Compatibility Engine — محرك توافق البنود القانونية.

يتحقق من توافق البنود مع بعضها ومع أنواع المستندات
والولايات القضائية، ويكتشف التعارضات.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.schemas.m5_contract import (
    ApprovedClause,
    ClauseCompatibilityRule,
    ClauseType,
    CompatibilityRelationship,
    CompatibilityResult,
    DocumentType,
    Jurisdiction,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Built-in Incompatibility Rules
# ──────────────────────────────────────────────

_BUILTIN_TYPE_INCOMPATIBILITIES: list[
    tuple[ClauseType, ClauseType, str]
] = [
    (
        ClauseType.LIABILITY_LIMITATION,
        ClauseType.INDEMNITY,
        "Unlimited indemnity contradicts liability limitation",
    ),
    (
        ClauseType.NON_COMPETE,
        ClauseType.ASSIGNMENT,
        "Non-compete may conflict with free assignment rights",
    ),
]


class CompatibilityEngine:
    """
    محرك التوافق بين البنود القانونية.

    المسؤوليات:
    - فحص التوافق بين بندين
    - فحص توافق بند مع نوع مستند
    - فحص توافق بند مع ولاية قضائية
    - اكتشاف كل أزواج التعارض في مجموعة بنود
    """

    def __init__(
        self,
        rules: list[ClauseCompatibilityRule] | None = None,
    ) -> None:
        self._rules: list[ClauseCompatibilityRule] = (
            rules or []
        )

    @property
    def rule_count(self) -> int:
        """عدد القواعد المحملة."""
        return len(self._rules)

    def add_rule(
        self,
        rule: ClauseCompatibilityRule,
    ) -> None:
        """إضافة قاعدة توافق."""
        self._rules.append(rule)

    def add_rules(
        self,
        rules: list[ClauseCompatibilityRule],
    ) -> None:
        """إضافة عدة قواعد توافق."""
        self._rules.extend(rules)

    def get_rules(self) -> list[ClauseCompatibilityRule]:
        """استرجاع كل القواعد."""
        return list(self._rules)

    def check_compatibility(
        self,
        clause_a: ApprovedClause,
        clause_b: ApprovedClause,
    ) -> CompatibilityResult:
        """
        فحص التوافق بين بندين.

        يفحص أولاً القواعد المخصصة (بالـ clause_id)
        ثم القواعد المضمنة (بالـ ClauseType).
        """

        # Check custom rules by clause_id
        custom_result = self._check_custom_rules(
            clause_a.clause_id,
            clause_b.clause_id,
        )
        if custom_result is not None:
            return custom_result

        # Check built-in type incompatibilities
        builtin_result = self._check_builtin_incompatibilities(
            clause_a.type,
            clause_b.type,
        )
        if builtin_result is not None:
            return builtin_result

        # Check jurisdiction mismatch
        if clause_a.jurisdiction != clause_b.jurisdiction:
            if (
                clause_a.jurisdiction != Jurisdiction.INTERNATIONAL
                and clause_b.jurisdiction != Jurisdiction.INTERNATIONAL
            ):
                return CompatibilityResult(
                    compatible=False,
                    relationship=CompatibilityRelationship.INCOMPATIBLE,
                    reason=(
                        f"Jurisdiction mismatch: "
                        f"{clause_a.jurisdiction.value} vs "
                        f"{clause_b.jurisdiction.value}"
                    ),
                )

        return CompatibilityResult(
            compatible=True,
            reason="No incompatibility detected",
        )

    def check_document_compatibility(
        self,
        clause: ApprovedClause,
        document_type: DocumentType,
    ) -> bool:
        """هل البند يصلح لنوع المستند المحدد."""
        return document_type in clause.document_types

    def check_jurisdiction_compatibility(
        self,
        clause: ApprovedClause,
        jurisdiction: Jurisdiction,
    ) -> bool:
        """هل البند يصلح للولاية القضائية المحددة."""
        if clause.jurisdiction == Jurisdiction.INTERNATIONAL:
            return True
        return clause.jurisdiction == jurisdiction

    def find_incompatible_pairs(
        self,
        clauses: list[ApprovedClause],
    ) -> list[tuple[str, str, str]]:
        """
        اكتشاف كل أزواج البنود المتعارضة في مجموعة.

        يرجع قائمة tuples: (clause_id_a, clause_id_b, reason)
        """
        incompatible: list[tuple[str, str, str]] = []

        for i, clause_a in enumerate(clauses):
            for clause_b in clauses[i + 1:]:
                result = self.check_compatibility(
                    clause_a, clause_b
                )
                if not result.compatible:
                    incompatible.append((
                        clause_a.clause_id,
                        clause_b.clause_id,
                        result.reason,
                    ))

        return incompatible

    def validate_clause_set_for_document(
        self,
        clauses: list[ApprovedClause],
        document_type: DocumentType,
        jurisdiction: Jurisdiction,
    ) -> list[str]:
        """
        فحص مجموعة بنود لنوع مستند وولاية قضائية.

        يرجع قائمة أخطاء/تحذيرات.
        """
        errors: list[str] = []

        for clause in clauses:
            if not self.check_document_compatibility(
                clause, document_type
            ):
                errors.append(
                    f"Clause {clause.clause_id} is not compatible "
                    f"with document type {document_type.value}"
                )

            if not self.check_jurisdiction_compatibility(
                clause, jurisdiction
            ):
                errors.append(
                    f"Clause {clause.clause_id} ({clause.jurisdiction.value}) "
                    f"is not compatible with jurisdiction {jurisdiction.value}"
                )

        incompatible = self.find_incompatible_pairs(clauses)
        for id_a, id_b, reason in incompatible:
            errors.append(
                f"Incompatible clauses: {id_a} <-> {id_b}: {reason}"
            )

        return errors

    def _check_custom_rules(
        self,
        clause_id_a: str,
        clause_id_b: str,
    ) -> Optional[CompatibilityResult]:
        """فحص القواعد المخصصة بالـ clause_id."""

        for rule in self._rules:
            ids = {rule.clause_id_a, rule.clause_id_b}
            if {clause_id_a, clause_id_b} == ids:
                if (
                    rule.relationship
                    == CompatibilityRelationship.INCOMPATIBLE
                ):
                    return CompatibilityResult(
                        compatible=False,
                        relationship=rule.relationship,
                        reason=rule.reason,
                    )
                else:
                    return CompatibilityResult(
                        compatible=True,
                        relationship=rule.relationship,
                        reason=rule.reason,
                    )

        return None

    def _check_builtin_incompatibilities(
        self,
        type_a: ClauseType,
        type_b: ClauseType,
    ) -> Optional[CompatibilityResult]:
        """فحص القواعد المضمنة بالـ ClauseType."""

        for (
            incompat_a,
            incompat_b,
            reason,
        ) in _BUILTIN_TYPE_INCOMPATIBILITIES:
            if {type_a, type_b} == {incompat_a, incompat_b}:
                return CompatibilityResult(
                    compatible=False,
                    relationship=(
                        CompatibilityRelationship.INCOMPATIBLE
                    ),
                    reason=reason,
                )

        return None
