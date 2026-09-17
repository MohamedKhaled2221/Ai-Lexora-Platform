from __future__ import annotations

import re
from typing import Iterable, List

from src.schemas.m5_contract import (
    ApprovalStatus,
    ApprovedClause,
    DocumentType,
    Jurisdiction,
    TemplateClauseRequirement,
)

from .errors import ValidationError
from .schemas import (
    AssembledDraft,
    TemplateDefinition,
)


def find_placeholders(
    text: str,
    pattern: str,
) -> List[str]:

    return sorted(
        set(
            re.findall(
                pattern,
                text,
            )
        )
    )


def validate_no_unresolved_placeholders(
    text: str,
    template: TemplateDefinition,
) -> None:

    unresolved = find_placeholders(
        text,
        template.placeholder_pattern,
    )

    if unresolved:
        raise ValidationError(
            "Unresolved placeholders: "
            + ", ".join(unresolved)
        )


def validate_required_clauses(
    selected_clauses: Iterable[ApprovedClause],
    required_clause_ids: Iterable[str],
) -> None:

    selected = {
        clause.clause_id
        for clause in selected_clauses
    }

    missing = [
        clause_id
        for clause_id in required_clause_ids
        if clause_id not in selected
    ]

    if missing:
        raise ValidationError(
            "Missing required approved clauses: "
            + ", ".join(missing)
        )


def validate_approved_clause_set(
    clauses: Iterable[ApprovedClause],
    expected_document_type: str,
    expected_jurisdiction: str,
) -> None:

    try:
        document_type = DocumentType(
            expected_document_type
        )
    except ValueError as exc:
        raise ValidationError(
            "Unsupported M5 document type: "
            + expected_document_type
        ) from exc

    try:
        jurisdiction = Jurisdiction(
            expected_jurisdiction
        )
    except ValueError as exc:
        raise ValidationError(
            "Unsupported M5 jurisdiction: "
            + expected_jurisdiction
        ) from exc

    for clause in clauses:

        if (
            clause.approval_status
            != ApprovalStatus.APPROVED
        ):
            raise ValidationError(
                "Clause is not approved: "
                + clause.clause_id
            )

        if not clause.is_usable():
            raise ValidationError(
                "Clause is not currently usable: "
                + clause.clause_id
            )

        if document_type not in clause.document_types:
            raise ValidationError(
                f"Clause {clause.clause_id} incompatible "
                f"with document type "
                f"{expected_document_type}"
            )

        if clause.jurisdiction not in {
            jurisdiction,
            Jurisdiction.INTERNATIONAL,
        }:
            raise ValidationError(
                f"Clause {clause.clause_id} incompatible "
                f"with jurisdiction "
                f"{expected_jurisdiction}"
            )


def validate_prohibited_clauses(
    clauses: Iterable[ApprovedClause],
    requirement: TemplateClauseRequirement,
) -> None:

    selected_ids = {
        clause.clause_id
        for clause in clauses
    }

    prohibited = [
        clause_id
        for clause_id
        in requirement.prohibited_clauses
        if clause_id in selected_ids
    ]

    if prohibited:
        raise ValidationError(
            "Prohibited approved clauses selected: "
            + ", ".join(prohibited)
        )


def validate_clause_placement(
    clauses: Iterable[ApprovedClause],
    requirement: TemplateClauseRequirement,
) -> None:

    if not requirement.section_placeholders:
        raise ValidationError(
            f"Template requirement "
            f"{requirement.template_id} has no "
            "section_placeholders defined"
        )

    valid_markers = set(
        requirement.section_placeholders.values()
    )

    for clause in clauses:

        insertion_key = (
            clause.metadata.insertion_key
        )

        if not insertion_key:
            raise ValidationError(
                "Missing insertion_key for approved clause: "
                + clause.clause_id
            )

        if (
            insertion_key
            in requirement.section_placeholders
        ):
            continue

        if insertion_key in valid_markers:
            continue

        raise ValidationError(
            f"Invalid clause insertion_key: "
            f"{clause.clause_id} -> "
            f"{insertion_key}"
        )


def validate_source_traceability(
    draft: AssembledDraft,
) -> None:

    for section in draft.sections:

        if not section.source_id:
            raise ValidationError(
                f"Section {section.section_id} "
                "has no source identifier"
            )

        if (
            section.source_type
            == "approved_clause"
            and not section.clause_id
        ):
            raise ValidationError(
                f"Section {section.section_id} "
                "has no clause_id"
            )

        if (
            section.source_type
            == "approved_clause"
            and not section.clause_version
        ):
            raise ValidationError(
                f"Section {section.section_id} "
                "has no clause_version"
            )