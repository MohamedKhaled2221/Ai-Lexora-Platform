"""
Required Clause Rules — قواعد البنود الإلزامية.

يحدد البنود المطلوبة والاختيارية والممنوعة والمشروطة
لكل نوع عقد وولاية قضائية.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from src.clause_engine.clause_library import ClauseLibrary
from src.schemas.m5_contract import (
    ApprovedClause,
    CompletenessReport,
    ConditionalClause,
    DocumentType,
    Jurisdiction,
    TemplateClauseRequirement,
)

logger = logging.getLogger(__name__)


class RequiredClauseEngine:
    """
    محرك قواعد البنود الإلزامية.

    يحدد لكل template (نوع عقد + ولاية قضائية):
    - البنود الإلزامية (required)
    - البنود الاختيارية (optional)
    - البنود الممنوعة (prohibited)
    - البنود المشروطة (conditional)
    """

    def __init__(
        self,
        clause_library: ClauseLibrary,
        requirements_path: str | Path | None = None,
    ) -> None:
        self._clause_library = clause_library
        self._templates: dict[str, TemplateClauseRequirement] = {}

        if requirements_path:
            self.load_requirements(requirements_path)

    @property
    def template_count(self) -> int:
        """عدد النماذج المحملة."""
        return len(self._templates)

    def load_requirements(
        self,
        path: str | Path,
    ) -> None:
        """تحميل متطلبات النماذج من ملف JSON."""
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(
                f"Requirements file not found: {path}"
            )

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        templates = data.get("templates", [])
        self._templates.clear()

        for tmpl_data in templates:
            template = TemplateClauseRequirement.model_validate(
                tmpl_data
            )
            self._templates[template.template_id] = template

        logger.info(
            "Loaded %d template requirements from %s",
            len(self._templates),
            path,
        )

    def add_template(
        self,
        template: TemplateClauseRequirement,
    ) -> None:
        """إضافة نموذج متطلبات."""
        self._templates[template.template_id] = template

    def get_template(
        self,
        template_id: str,
    ) -> Optional[TemplateClauseRequirement]:
        """استرجاع نموذج بمعرّفه."""
        return self._templates.get(template_id)

    def find_template(
        self,
        document_type: DocumentType,
        jurisdiction: Jurisdiction,
    ) -> Optional[TemplateClauseRequirement]:
        """
        البحث عن نموذج بنوع المستند والولاية القضائية.
        """
        for template in self._templates.values():
            if (
                template.document_type == document_type
                and template.jurisdiction == jurisdiction
            ):
                return template

        return None

    def get_template_structure(
        self,
        document_type: DocumentType,
        jurisdiction: Jurisdiction,
    ) -> str:
        """استرجاع الهيكل النصي المرجعي للنموذج بالـ placeholders."""
        template = self.find_template(document_type, jurisdiction)
        return template.template_structure if template else ""

    def get_section_placeholders(
        self,
        document_type: DocumentType,
        jurisdiction: Jurisdiction,
    ) -> dict[str, str]:
        """استرجاع خريطة مواضع الإدراج والـ placeholders المتاحة في النموذج."""
        template = self.find_template(document_type, jurisdiction)
        return dict(template.section_placeholders) if template else {}

    def get_required_clauses(
        self,
        document_type: DocumentType,
        jurisdiction: Jurisdiction,
    ) -> list[ApprovedClause]:
        """استرجاع البنود الإلزامية لنوع عقد وولاية قضائية."""
        template = self.find_template(
            document_type, jurisdiction
        )
        if not template:
            return []

        return self._clause_library.get_clauses_by_ids(
            template.required_clauses
        )

    def get_optional_clauses(
        self,
        document_type: DocumentType,
        jurisdiction: Jurisdiction,
    ) -> list[ApprovedClause]:
        """استرجاع البنود الاختيارية لنوع عقد وولاية قضائية."""
        template = self.find_template(
            document_type, jurisdiction
        )
        if not template:
            return []

        return self._clause_library.get_clauses_by_ids(
            template.optional_clauses
        )

    def get_prohibited_clauses(
        self,
        document_type: DocumentType,
        jurisdiction: Jurisdiction,
    ) -> list[str]:
        """استرجاع قائمة clause_ids الممنوعة."""
        template = self.find_template(
            document_type, jurisdiction
        )
        if not template:
            return []

        return list(template.prohibited_clauses)

    def get_conditional_clauses(
        self,
        document_type: DocumentType,
        jurisdiction: Jurisdiction,
        active_conditions: list[str] | None = None,
    ) -> list[ApprovedClause]:
        """
        استرجاع البنود المشروطة المطبقة.

        active_conditions: قائمة الشروط المتحققة حالياً.
        """
        template = self.find_template(
            document_type, jurisdiction
        )
        if not template:
            return []

        if not active_conditions:
            return []

        matching_ids: list[str] = []
        for cond_clause in template.conditional_clauses:
            if cond_clause.condition in active_conditions:
                matching_ids.append(cond_clause.clause_id)

        return self._clause_library.get_clauses_by_ids(
            matching_ids
        )

    def validate_completeness(
        self,
        clause_ids: list[str],
        document_type: DocumentType,
        jurisdiction: Jurisdiction,
    ) -> CompletenessReport:
        """
        فحص اكتمال البنود لنوع عقد وولاية قضائية.

        يتحقق من:
        - وجود كل البنود الإلزامية
        - عدم وجود أي بند ممنوع
        """
        template = self.find_template(
            document_type, jurisdiction
        )

        if not template:
            return CompletenessReport(
                template_id="unknown",
                is_complete=True,
                warnings=[
                    "No template found for "
                    f"{document_type.value}/{jurisdiction.value}"
                ],
            )

        provided_set = set(clause_ids)

        missing_required = [
            req_id
            for req_id in template.required_clauses
            if req_id not in provided_set
        ]

        included_prohibited = [
            proh_id
            for proh_id in template.prohibited_clauses
            if proh_id in provided_set
        ]

        warnings: list[str] = []
        if missing_required:
            warnings.append(
                f"Missing {len(missing_required)} required clause(s)"
            )
        if included_prohibited:
            warnings.append(
                f"Contains {len(included_prohibited)} prohibited clause(s)"
            )

        is_complete = (
            not missing_required and not included_prohibited
        )

        return CompletenessReport(
            template_id=template.template_id,
            is_complete=is_complete,
            missing_required=missing_required,
            included_prohibited=included_prohibited,
            warnings=warnings,
        )
