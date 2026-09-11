from __future__ import annotations

from typing import List

from .clause_library import ClauseLibrary
from .schemas import (
    ApprovedClause,
    ClauseDecision,
    TemplateDefinition,
)


class TemplateClauseResolver:
    def __init__(self, clause_library: ClauseLibrary):
        self.clause_library = clause_library

    def resolve_required(
        self,
        template: TemplateDefinition,
    ) -> List[ApprovedClause]:

        resolved_clauses: List[ApprovedClause] = []

        for clause_id in template.required_clauses:
            clause = self.clause_library.get(clause_id)

            self._validate_clause_for_template(
                clause,
                template,
            )

            resolved_clauses.append(clause)

        return resolved_clauses

    def resolve_optional(
        self,
        template: TemplateDefinition,
    ) -> List[ApprovedClause]:

        resolved_clauses: List[ApprovedClause] = []

        for clause_id in template.optional_clauses:
            clause = self.clause_library.get(clause_id)

            self._validate_clause_for_template(
                clause,
                template,
            )

            resolved_clauses.append(clause)

        return resolved_clauses

    def resolve_all(
        self,
        template: TemplateDefinition,
    ) -> List[ApprovedClause]:

        clauses: List[ApprovedClause] = []

        clauses.extend(
            self.resolve_required(template)
        )

        clauses.extend(
            self.resolve_optional(template)
        )

        return clauses

    def build_decisions(
        self,
        template: TemplateDefinition,
    ) -> List[ClauseDecision]:

        decisions: List[ClauseDecision] = []

        # Required clauses
        for clause_id in template.required_clauses:
            clause = self.clause_library.get(clause_id)

            self._validate_clause_for_template(
                clause,
                template,
            )

            decisions.append(
                ClauseDecision(
                    clause_id=clause.clause_id,
                    decision="required",
                    reason="Required by template",
                )
            )

        # Optional clauses
        for clause_id in template.optional_clauses:
            try:
                clause = self.clause_library.get(clause_id)

                self._validate_clause_for_template(
                    clause,
                    template,
                )

                decisions.append(
                    ClauseDecision(
                        clause_id=clause.clause_id,
                        decision="optional",
                        reason="Optional for template",
                    )
                )

            except ValueError as error:
                decisions.append(
                    ClauseDecision(
                        clause_id=clause_id,
                        decision="incompatible",
                        reason=str(error),
                    )
                )

        # Prohibited clauses
        for clause_id in template.prohibited_clauses:
            decisions.append(
                ClauseDecision(
                    clause_id=clause_id,
                    decision="prohibited",
                    reason="Prohibited by template",
                )
            )

        return decisions

    @staticmethod
    def _validate_clause_for_template(
        clause: ApprovedClause,
        template: TemplateDefinition,
    ) -> None:

        # 1. Approval validation
        if clause.approval_status != "approved":
            raise ValueError(
                f"Clause {clause.clause_id} is not approved"
            )

        # 2. Document type compatibility
        if template.document_type not in clause.document_types:
            raise ValueError(
                f"Clause {clause.clause_id} is not valid "
                f"for document type "
                f"{template.document_type}"
            )

        # 3. Jurisdiction compatibility
        if (
            clause.jurisdiction.lower()
            != template.jurisdiction.lower()
        ):
            raise ValueError(
                f"Clause {clause.clause_id} has jurisdiction "
                f"{clause.jurisdiction}, expected "
                f"{template.jurisdiction}"
            )

        # 4. Prohibited clause validation
        if clause.clause_id in template.prohibited_clauses:
            raise ValueError(
                f"Clause {clause.clause_id} is prohibited "
                f"by template {template.template_id}"
            )

        # 5. Placement validation
        #
        # If the template defines section placeholders,
        # the clause must provide a matching insertion_key.
        if template.section_placeholders:

            if not clause.insertion_key:
                raise ValueError(
                    f"Clause {clause.clause_id} has no insertion_key "
                    f"for template {template.template_id}"
                )

            if clause.insertion_key not in template.section_placeholders:
                raise ValueError(
                    f"Clause {clause.clause_id} has insertion_key "
                    f"{clause.insertion_key}, which is not defined "
                    f"in template {template.template_id}"
                )