"""
Clause Library — مكتبة البنود القانونية المعتمدة.

المصدر الوحيد للحقيقة القانونية (Legal Source of Truth)
لكل البنود التعاقدية في M5.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from src.schemas.m5_contract import (
    ApprovedClause,
    ApprovalStatus,
    ClauseType,
    DocumentType,
    Jurisdiction,
)

logger = logging.getLogger(__name__)


class ClauseLibraryError(Exception):
    """خطأ عام في مكتبة البنود."""


class ClauseNotFoundError(ClauseLibraryError):
    """البند المطلوب غير موجود."""


class DuplicateClauseError(ClauseLibraryError):
    """البند موجود بالفعل."""


class ClauseLibrary:
    """
    مكتبة البنود القانونية المعتمدة.

    المسؤوليات:
    - تحميل وحفظ البنود من/إلى JSON
    - البحث عن بنود بمعايير متعددة
    - إضافة وتعديل البنود مع ضمان التحقق
    - ضمان فرادة clause_id
    """

    def __init__(
        self,
        library_path: str | Path | None = None,
    ) -> None:
        self._clauses: dict[str, ApprovedClause] = {}
        self._library_path = (
            Path(library_path) if library_path else None
        )

        if self._library_path and self._library_path.exists():
            self.load_library(self._library_path)

    @property
    def clause_count(self) -> int:
        """عدد البنود في المكتبة."""
        return len(self._clauses)

    def load_library(
        self,
        path: str | Path,
    ) -> dict[str, ApprovedClause]:
        """
        تحميل المكتبة من ملف JSON.

        يستبدل أي بنود محملة مسبقاً.
        """
        path = Path(path)

        if not path.exists():
            raise ClauseLibraryError(
                f"Library file not found: {path}"
            )

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ClauseLibraryError(
                f"Invalid JSON in library file: {exc}"
            ) from exc

        clauses_data = data.get("clauses", [])
        self._clauses.clear()

        for clause_data in clauses_data:
            clause = ApprovedClause.model_validate(clause_data)
            self._clauses[clause.clause_id] = clause

        self._library_path = path

        logger.info(
            "Loaded %d clauses from %s",
            len(self._clauses),
            path,
        )

        return dict(self._clauses)

    def save_library(
        self,
        path: str | Path | None = None,
    ) -> None:
        """حفظ المكتبة إلى ملف JSON."""
        save_path = Path(path) if path else self._library_path

        if save_path is None:
            raise ClauseLibraryError(
                "No save path specified"
            )

        save_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1.0.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "clause_count": len(self._clauses),
            "clauses": [
                json.loads(clause.model_dump_json())
                for clause in self._clauses.values()
            ],
        }

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(
            "Saved %d clauses to %s",
            len(self._clauses),
            save_path,
        )

    def get_clause(
        self,
        clause_id: str,
    ) -> ApprovedClause:
        """استرجاع بند بمعرّفه."""
        clause = self._clauses.get(clause_id)

        if clause is None:
            raise ClauseNotFoundError(
                f"Clause not found: {clause_id}"
            )

        return clause

    def get_clause_or_none(
        self,
        clause_id: str,
    ) -> Optional[ApprovedClause]:
        """استرجاع بند أو None."""
        return self._clauses.get(clause_id)

    def search_clauses(
        self,
        *,
        clause_type: ClauseType | None = None,
        jurisdiction: Jurisdiction | None = None,
        document_type: DocumentType | None = None,
        approval_status: ApprovalStatus | None = None,
        tags: list[str] | None = None,
        active_only: bool = False,
    ) -> list[ApprovedClause]:
        """
        بحث عن بنود بمعايير متعددة.

        كل المعايير اختيارية — يُطبَّق الفلترة
        على المعايير المحددة فقط.
        """
        results: list[ApprovedClause] = []

        for clause in self._clauses.values():
            if clause_type and clause.type != clause_type:
                continue

            if jurisdiction and clause.jurisdiction != jurisdiction:
                continue

            if (
                document_type
                and document_type not in clause.document_types
            ):
                continue

            if (
                approval_status
                and clause.approval_status != approval_status
            ):
                continue

            if tags:
                clause_tags = set(clause.tags)
                if not set(tags).intersection(clause_tags):
                    continue

            if active_only and not clause.is_active():
                continue

            results.append(clause)

        return results

    def get_active_clauses(self) -> list[ApprovedClause]:
        """استرجاع كل البنود السارية والمعتمدة فقط."""
        return [
            clause
            for clause in self._clauses.values()
            if clause.is_active()
        ]

    def get_usable_clauses(self) -> list[ApprovedClause]:
        """استرجاع كل البنود القابلة للاستخدام."""
        return [
            clause
            for clause in self._clauses.values()
            if clause.is_usable()
        ]

    def add_clause(
        self,
        clause: ApprovedClause,
    ) -> ApprovedClause:
        """
        إضافة بند جديد للمكتبة.

        يرفض الإضافة لو clause_id موجود بالفعل.
        """
        if clause.clause_id in self._clauses:
            raise DuplicateClauseError(
                f"Clause already exists: {clause.clause_id}"
            )

        validation_errors = self.validate_clause(clause)
        if validation_errors:
            raise ClauseLibraryError(
                "Clause validation failed: "
                + "; ".join(validation_errors)
            )

        self._clauses[clause.clause_id] = clause

        logger.info(
            "Added clause %s to library",
            clause.clause_id,
        )

        return clause

    def update_clause(
        self,
        clause_id: str,
        **updates,
    ) -> ApprovedClause:
        """
        تعديل بند موجود.

        يقبل أي حقل من حقول ApprovedClause كـ keyword argument.
        """
        existing = self.get_clause(clause_id)

        updates["updated_at"] = datetime.now(timezone.utc)

        updated_data = existing.model_dump()
        updated_data.update(updates)

        updated_clause = ApprovedClause.model_validate(
            updated_data
        )

        validation_errors = self.validate_clause(updated_clause)
        if validation_errors:
            raise ClauseLibraryError(
                "Updated clause validation failed: "
                + "; ".join(validation_errors)
            )

        self._clauses[clause_id] = updated_clause

        logger.info(
            "Updated clause %s",
            clause_id,
        )

        return updated_clause

    def remove_clause(
        self,
        clause_id: str,
    ) -> ApprovedClause:
        """حذف بند من المكتبة."""
        clause = self.get_clause(clause_id)
        del self._clauses[clause_id]

        logger.info(
            "Removed clause %s from library",
            clause_id,
        )

        return clause

    def validate_clause(
        self,
        clause: ApprovedClause,
    ) -> list[str]:
        """
        تحقق من صحة بند.

        يرجع قائمة أخطاء (فاضية = صالح).
        """
        errors: list[str] = []

        if not clause.clause_id.startswith("CLZ-"):
            errors.append(
                "clause_id must start with 'CLZ-' prefix"
            )

        if not clause.text_ar.strip():
            errors.append("text_ar cannot be empty")

        if not clause.text_en.strip():
            errors.append("text_en cannot be empty")

        if not clause.document_types:
            errors.append(
                "At least one document_type is required"
            )

        if (
            clause.expiry_date
            and clause.expiry_date <= clause.effective_date
        ):
            errors.append(
                "expiry_date must be after effective_date"
            )

        if (
            clause.superseded_by
            and clause.approval_status != ApprovalStatus.SUPERSEDED
        ):
            errors.append(
                "Clause with superseded_by must have "
                "SUPERSEDED approval_status"
            )

        return errors

    def get_all_clauses(self) -> list[ApprovedClause]:
        """استرجاع كل البنود."""
        return list(self._clauses.values())

    def get_clauses_by_ids(
        self,
        clause_ids: list[str],
    ) -> list[ApprovedClause]:
        """استرجاع بنود بمعرّفاتها."""
        result = []

        for clause_id in clause_ids:
            clause = self._clauses.get(clause_id)
            if clause:
                result.append(clause)

        return result
