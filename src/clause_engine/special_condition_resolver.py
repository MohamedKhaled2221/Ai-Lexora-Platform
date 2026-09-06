"""
Special Condition Resolver — حلّال الشروط الخاصة.

يحاول إيجاد بند معتمد يطابق شرطاً خاصاً.
لو مفيش بند مطابق → يرجع requires_lawyer_input
بدلاً من توليد نص قانوني جديد.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.clause_engine.clause_library import ClauseLibrary
from src.schemas.m5_contract import (
    ApprovedClause,
    ClauseType,
    DocumentType,
    Jurisdiction,
    SpecialConditionResult,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Condition → ClauseType Mapping
# ──────────────────────────────────────────────

_CONDITION_TYPE_MAP: dict[str, ClauseType] = {
    "termination": ClauseType.TERMINATION,
    "early_termination": ClauseType.TERMINATION,
    "إنهاء": ClauseType.TERMINATION,
    "indemnity": ClauseType.INDEMNITY,
    "تعويض": ClauseType.INDEMNITY,
    "confidentiality": ClauseType.CONFIDENTIALITY,
    "سرية": ClauseType.CONFIDENTIALITY,
    "force_majeure": ClauseType.FORCE_MAJEURE,
    "قوة_قاهرة": ClauseType.FORCE_MAJEURE,
    "governing_law": ClauseType.GOVERNING_LAW,
    "القانون_الحاكم": ClauseType.GOVERNING_LAW,
    "dispute": ClauseType.DISPUTE_RESOLUTION,
    "نزاع": ClauseType.DISPUTE_RESOLUTION,
    "liability": ClauseType.LIABILITY_LIMITATION,
    "مسؤولية": ClauseType.LIABILITY_LIMITATION,
    "payment": ClauseType.PAYMENT_TERMS,
    "دفع": ClauseType.PAYMENT_TERMS,
    "warranty": ClauseType.WARRANTY,
    "ضمان": ClauseType.WARRANTY,
    "ip": ClauseType.INTELLECTUAL_PROPERTY,
    "intellectual_property": ClauseType.INTELLECTUAL_PROPERTY,
    "ملكية_فكرية": ClauseType.INTELLECTUAL_PROPERTY,
    "non_compete": ClauseType.NON_COMPETE,
    "عدم_منافسة": ClauseType.NON_COMPETE,
    "data_protection": ClauseType.DATA_PROTECTION,
    "حماية_بيانات": ClauseType.DATA_PROTECTION,
    "penalty": ClauseType.PENALTY,
    "شرط_جزائي": ClauseType.PENALTY,
    "notice": ClauseType.NOTICE,
    "إخطار": ClauseType.NOTICE,
}


class SpecialConditionResolver:
    """
    حلّال الشروط الخاصة.

    القاعدة الذهبية:
    لو مفيش بند معتمد يطابق الشرط الخاص →
    يرجع requires_lawyer_input=True
    بدلاً من توليد نص قانوني جديد.

    خطوات الحل:
    1. محاولة مطابقة الشرط مع نوع بند (ClauseType)
    2. بحث عن بنود معتمدة نشطة من نفس النوع
    3. تصفية بحسب الولاية القضائية (إن وُجدت)
    4. تصفية بحسب نوع المستند (إن وُجد)
    5. تصفية بحسب الكلمات المفتاحية
    6. لو مفيش نتيجة → requires_lawyer_input
    """

    def __init__(
        self,
        clause_library: ClauseLibrary,
    ) -> None:
        self._clause_library = clause_library

    def resolve(
        self,
        condition: str,
        *,
        jurisdiction: Jurisdiction | None = None,
        document_type: DocumentType | None = None,
    ) -> SpecialConditionResult:
        """
        محاولة حل شرط خاص.

        يبحث عن بند معتمد مطابق.
        لو مفيش → requires_lawyer_input.
        """
        condition_lower = condition.strip().lower()

        if not condition_lower:
            return SpecialConditionResult(
                condition=condition,
                resolved=False,
                requires_lawyer_input=True,
                reason="Empty condition provided",
            )

        # Step 1: Try type-based matching
        matched = self.find_matching_clause(
            condition_lower,
            jurisdiction=jurisdiction,
            document_type=document_type,
        )

        if matched:
            return SpecialConditionResult(
                condition=condition,
                resolved=True,
                matched_clause=matched,
                requires_lawyer_input=False,
                reason=(
                    f"Matched approved clause: {matched.clause_id}"
                ),
            )

        # Step 2: Try keyword-based matching
        keyword_match = self._find_by_keywords(
            condition_lower,
            jurisdiction=jurisdiction,
            document_type=document_type,
        )

        if keyword_match:
            return SpecialConditionResult(
                condition=condition,
                resolved=True,
                matched_clause=keyword_match,
                requires_lawyer_input=False,
                reason=(
                    f"Matched by keyword: {keyword_match.clause_id}"
                ),
            )

        # Step 3: No match → requires_lawyer_input
        logger.warning(
            "No approved clause found for condition: '%s'. "
            "Returning requires_lawyer_input.",
            condition,
        )

        return SpecialConditionResult(
            condition=condition,
            resolved=False,
            requires_lawyer_input=True,
            reason=(
                "No approved clause matches the special condition. "
                "Lawyer input is required."
            ),
        )

    def find_matching_clause(
        self,
        condition: str,
        *,
        jurisdiction: Jurisdiction | None = None,
        document_type: DocumentType | None = None,
    ) -> Optional[ApprovedClause]:
        """
        إيجاد بند معتمد يطابق الشرط بناءً على نوع البند.
        """
        clause_type = self._map_condition_to_type(condition)

        if clause_type is None:
            return None

        candidates = self._clause_library.search_clauses(
            clause_type=clause_type,
            jurisdiction=jurisdiction,
            document_type=document_type,
            active_only=True,
        )

        if not candidates:
            # Fallback: try without jurisdiction filter
            if jurisdiction:
                candidates = self._clause_library.search_clauses(
                    clause_type=clause_type,
                    document_type=document_type,
                    active_only=True,
                )

        if not candidates:
            return None

        # Return the first usable candidate
        for candidate in candidates:
            if candidate.is_usable():
                return candidate

        return candidates[0] if candidates else None

    def find_matching_variant(
        self,
        condition: str,
        clause_type: ClauseType,
    ) -> Optional[ApprovedClause]:
        """
        إيجاد متغير (variant) من نوع بند محدد.
        """
        candidates = self._clause_library.search_clauses(
            clause_type=clause_type,
            active_only=True,
        )

        condition_lower = condition.lower()

        for candidate in candidates:
            # Check if condition words appear in clause tags or text
            tags_text = " ".join(candidate.tags).lower()
            if condition_lower in tags_text:
                return candidate

            keywords = (
                candidate.metadata.keywords_ar
                + candidate.metadata.keywords_en
            )
            keywords_text = " ".join(keywords).lower()
            if condition_lower in keywords_text:
                return candidate

        return None

    def requires_lawyer_input(
        self,
        condition: str,
        *,
        jurisdiction: Jurisdiction | None = None,
        document_type: DocumentType | None = None,
    ) -> bool:
        """
        هل الشرط الخاص يحتاج تدخل محامٍ.
        """
        result = self.resolve(
            condition,
            jurisdiction=jurisdiction,
            document_type=document_type,
        )
        return result.requires_lawyer_input

    def _map_condition_to_type(
        self,
        condition: str,
    ) -> Optional[ClauseType]:
        """محاولة مطابقة شرط مع نوع بند."""
        condition_lower = condition.strip().lower()

        # Direct match
        if condition_lower in _CONDITION_TYPE_MAP:
            return _CONDITION_TYPE_MAP[condition_lower]

        # Partial match
        for key, clause_type in _CONDITION_TYPE_MAP.items():
            if key in condition_lower:
                return clause_type

        return None

    def _find_by_keywords(
        self,
        condition: str,
        *,
        jurisdiction: Jurisdiction | None = None,
        document_type: DocumentType | None = None,
    ) -> Optional[ApprovedClause]:
        """بحث بالكلمات المفتاحية."""
        active_clauses = self._clause_library.search_clauses(
            jurisdiction=jurisdiction,
            document_type=document_type,
            active_only=True,
        )

        condition_words = set(condition.lower().split())

        best_match: Optional[ApprovedClause] = None
        best_score = 0

        for clause in active_clauses:
            keywords = set(
                k.lower()
                for k in (
                    clause.metadata.keywords_ar
                    + clause.metadata.keywords_en
                    + clause.tags
                )
            )

            overlap = len(condition_words & keywords)
            if overlap > best_score:
                best_score = overlap
                best_match = clause

        # Require at least one keyword match
        if best_score > 0:
            return best_match

        return None
