from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List

from .placeholder_validator import (
    validate_approved_clause_set,
    validate_clause_placement,
    validate_no_unresolved_placeholders,
    validate_required_clauses,
    validate_source_traceability,
)
from .schemas import (
    ApprovedClause,
    AssembledDraft,
    ClauseDecision,
    DraftValidationResult,
    TemplateDefinition,
)


class DraftValidator:
    def validate(
        self,
        draft: AssembledDraft,
        template: TemplateDefinition,
        clauses: Iterable[ApprovedClause],
        decisions: Iterable[ClauseDecision],
    ) -> DraftValidationResult:

        errors: List[str] = []
        warnings: List[str] = []

        clauses = list(clauses)
        decisions = list(decisions)

        checks = (
            lambda: validate_approved_clause_set(
                clauses,
                draft.document_type,
                draft.jurisdiction,
            ),
            lambda: validate_clause_placement(
                clauses,
                template,
            ),
            lambda: validate_required_clauses(
                clauses,
                [
                    d.clause_id
                    for d in decisions
                    if d.decision == "required"
                ],
            ),
            lambda: validate_no_unresolved_placeholders(
                draft.plain_text,
                template,
            ),
            lambda: validate_source_traceability(draft),
        )

        for check in checks:
            try:
                check()
            except Exception as exc:
                errors.append(str(exc))

        selected = {
            clause.clause_id
            for clause in clauses
        }

        for decision in decisions:
            if (
                decision.decision
                in {"incompatible", "prohibited"}
                and decision.clause_id in selected
            ):
                errors.append(
                    "Prohibited/incompatible clause selected: "
                    + decision.clause_id
                )

        return DraftValidationResult(
            valid=not errors,
            errors=errors,
            warnings=warnings,
            checked_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )