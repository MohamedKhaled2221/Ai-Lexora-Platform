from __future__ import annotations

import re

from typing import Iterable, List

from .errors import ValidationError
from .schemas import (
    ApprovedClause,
    AssembledDraft,
    TemplateDefinition,
)


CLAUSE_MARKER_PATTERN = r"\{\{CLAUSE:[^}]+\}\}"


def find_placeholders(
    text: str,
    pattern: str,
) -> List[str]:
    return sorted(set(re.findall(pattern, text)))


def find_clause_markers(text: str) -> List[str]:
    return sorted(
        set(
            re.findall(
                CLAUSE_MARKER_PATTERN,
                text,
            )
        )
    )


def validate_no_unresolved_placeholders(
    text: str,
    template: TemplateDefinition,
) -> None:
    """
    Validate that normal user/input placeholders were resolved.

    Clause markers are handled separately because they represent
    approved-clause insertion points.
    """

    unresolved = find_placeholders(
        text,
        template.placeholder_pattern,
    )

    clause_markers = set(
        find_clause_markers(text)
    )

    unresolved = [
        placeholder
        for placeholder in unresolved
        if not placeholder.startswith("CLAUSE:")
    ]

    if unresolved:
        raise ValidationError(
            "Unresolved placeholders: "
            + ", ".join(unresolved)
        )

    if clause_markers:
        raise ValidationError(
            "Unresolved clause markers: "
            + ", ".join(clause_markers)
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
    """
    Validate that every selected clause is approved and compatible
    with the requested document type and jurisdiction.
    """

    expected_document_type = (
        expected_document_type.lower()
    )

    expected_jurisdiction = (
        expected_jurisdiction.lower()
    )

    for clause in clauses:

        if clause.approval_status != "approved":
            raise ValidationError(
                f"Clause is not approved: "
                f"{clause.clause_id}"
            )

        supported_document_types = {
            document_type.lower()
            for document_type in clause.document_types
        }

        if (
            expected_document_type
            not in supported_document_types
        ):
            raise ValidationError(
                f"Clause {clause.clause_id} incompatible "
                f"with document type "
                f"{expected_document_type}"
            )

        if (
            clause.jurisdiction.lower()
            != expected_jurisdiction
        ):
            raise ValidationError(
                f"Clause {clause.clause_id} incompatible "
                f"with jurisdiction "
                f"{expected_jurisdiction}"
            )


def validate_prohibited_clauses(
    clauses: Iterable[ApprovedClause],
    template: TemplateDefinition,
) -> None:
    """
    Ensure no clause explicitly prohibited by the template
    has been selected for assembly.
    """

    selected_ids = {
        clause.clause_id
        for clause in clauses
    }

    prohibited = [
        clause_id
        for clause_id in template.prohibited_clauses
        if clause_id in selected_ids
    ]

    if prohibited:
        raise ValidationError(
            "Prohibited approved clauses selected: "
            + ", ".join(prohibited)
        )


def validate_clause_placement(
    clauses: Iterable[ApprovedClause],
    template: TemplateDefinition,
) -> None:
    """
    Ensure every selected clause has a valid approved
    insertion point defined by the template.

    The insertion_key comes from the approved clause metadata
    supplied by M5.

    The template defines the available placement points through
    section_placeholders.
    """

    if not template.section_placeholders:
        raise ValidationError(
            f"Template {template.template_id} has no "
            "section_placeholders defined"
        )

    missing_keys = [
        clause.clause_id
        for clause in clauses
        if not clause.insertion_key
    ]

    if missing_keys:
        raise ValidationError(
            "Missing insertion_key for approved clauses: "
            + ", ".join(missing_keys)
        )

    invalid_keys = [
        (
            clause.clause_id,
            clause.insertion_key,
        )
        for clause in clauses
        if clause.insertion_key
        not in template.section_placeholders
    ]

    if invalid_keys:
        details = ", ".join(
            f"{clause_id} -> {insertion_key}"
            for clause_id, insertion_key
            in invalid_keys
        )

        raise ValidationError(
            "Invalid clause insertion_key(s): "
            + details
        )


def validate_source_traceability(
    draft: AssembledDraft,
) -> None:
    """
    Every assembled section must have a source identifier.

    Approved-clause sections must additionally retain their
    clause identity and version.
    """

    for section in draft.sections:

        if not section.source_id:
            raise ValidationError(
                f"Section {section.section_id} "
                "has no source identifier"
            )

        if (
            section.source_type == "approved_clause"
            and not section.clause_id
        ):
            raise ValidationError(
                f"Section {section.section_id} "
                "has no clause_id"
            )

        if (
            section.source_type == "approved_clause"
            and not section.clause_version
        ):
            raise ValidationError(
                f"Section {section.section_id} "
                "has no clause_version"
            )