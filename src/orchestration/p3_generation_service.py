from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.clause_engine.service import (
    M5ClauseService,
)
from src.document_generator.schemas import (
    ExportResult,
    GuidedDocumentRequest,
)
from src.document_generator.service import (
    M1DocumentService,
)
from src.orchestration.p3_contract_adapter import (
    M1ToM4P3ContractAdapter,
    P3ContractAdapterResult,
)
from src.orchestration.p3_m5_service import (
    P3M5ValidationResult,
    P3M5ValidationService,
)
from src.schemas.m5_contract import (
    ApprovedClause,
    DocumentType,
    Jurisdiction,
)
from src.schemas.p3_generation_contract import (
    ValidatedDraft,
)


class P3GenerationIntegrationError(
    RuntimeError
):
    """Package 3 integration failed closed."""


@dataclass(frozen=True)
class P3GenerationResult:
    validated_draft: ValidatedDraft

    selected_clause_ids: tuple[
        str,
        ...
    ]

    export_allowed: bool

    docx_result: ExportResult | None
    pdf_result: ExportResult | None

    m5_resolved_clause_count: int


class P3GenerationService:
    """
    Authoritative Package 3 integration.

    M5 -> M1 -> M4 -> export gate.
    """

    def __init__(
        self,
        *,
        m5_service: M5ClauseService,
        m1_service: M1DocumentService,
        m4_validation_service: (
            P3M5ValidationService
        ),
        contract_adapter: (
            M1ToM4P3ContractAdapter
            | None
        ) = None,
    ) -> None:

        self.m5_service = m5_service
        self.m1_service = m1_service
        self.m4_validation_service = (
            m4_validation_service
        )

        self.contract_adapter = (
            contract_adapter
            or M1ToM4P3ContractAdapter()
        )

    def generate(
        self,
        *,
        request: GuidedDocumentRequest,
        clause_language: str = "en",
        active_conditions: Iterable[
            str
        ] = (),
        optional_clause_ids: Iterable[
            str
        ] = (),
        docx_path: str | None = None,
        pdf_dir: str | None = None,
    ) -> P3GenerationResult:

        if clause_language not in {
            "ar",
            "en",
        }:
            raise P3GenerationIntegrationError(
                "clause_language must be 'ar' or 'en'"
            )

        try:
            document_type = DocumentType(
                request.document_type
            )

            jurisdiction = Jurisdiction(
                request.jurisdiction
            )

        except ValueError as exc:
            raise P3GenerationIntegrationError(
                "The requested document type or "
                "jurisdiction is not supported by M5."
            ) from exc

        active_conditions = list(
            dict.fromkeys(
                active_conditions
            )
        )

        requested_optional = list(
            dict.fromkeys(
                optional_clause_ids
            )
        )

        # -------------------------------------------------
        # M5 authoritative handoff
        # -------------------------------------------------

        handoff = (
            self.m5_service
            .get_clauses_for_document(
                document_type,
                jurisdiction,
                active_conditions=(
                    active_conditions
                ),
            )
        )

        requirement = (
            handoff.template_requirement
        )

        optional_ids = set(
            requirement.optional_clauses
        )

        invalid_optional = sorted(
            set(requested_optional)
            - optional_ids
        )

        if invalid_optional:
            raise P3GenerationIntegrationError(
                "Requested optional clause(s) are "
                "not optional clauses for this "
                "template: "
                + ", ".join(
                    invalid_optional
                )
            )

        active_condition_set = set(
            active_conditions
        )

        active_conditional_ids = {
            conditional.clause_id
            for conditional
            in requirement.conditional_clauses
            if (
                conditional.condition
                in active_condition_set
            )
        }

        selected_ids = {
            *requirement.required_clauses,
            *active_conditional_ids,
            *requested_optional,
        }

        clauses_by_id = {
            clause.clause_id: clause
            for clause in handoff.clauses
        }

        missing = sorted(
            selected_ids
            - clauses_by_id.keys()
        )

        if missing:
            raise P3GenerationIntegrationError(
                "M5 handoff is missing selected "
                "clause(s): "
                + ", ".join(missing)
            )

        selected_clauses = [
            clause
            for clause in handoff.clauses
            if clause.clause_id
            in selected_ids
        ]

        validation = (
            self.m5_service
            .validate_clause_set(
                [
                    clause.clause_id
                    for clause
                    in selected_clauses
                ],
                document_type,
                jurisdiction,
                active_conditions=(
                    active_conditions
                ),
            )
        )

        if not validation.valid:
            raise P3GenerationIntegrationError(
                "M5 rejected the selected clause "
                "set: "
                + " | ".join(
                    validation.errors
                    or validation.warnings
                )
            )

        # -------------------------------------------------
        # M1 language-safe assembly
        # -------------------------------------------------

        m1_clauses = [
            self._for_m1_language(
                clause,
                clause_language,
            )
            for clause in selected_clauses
        ]

        m1_draft, m1_manifest = (
            self.m1_service.build_draft(
                request,
                requirement,
                m1_clauses,
                (),
            )
        )

        template = (
            self.m1_service
            .selector
            .select(request)
        )

        # -------------------------------------------------
        # M1 -> shared Package 3 contracts
        # -------------------------------------------------

        adapted: P3ContractAdapterResult = (
            self.contract_adapter.adapt(
                request=request,
                template=template,
                requirement=requirement,
                clauses=selected_clauses,
                clause_language=(
                    clause_language
                ),
                m1_draft=m1_draft,
                m1_manifest=m1_manifest,
            )
        )

        # -------------------------------------------------
        # M4 validation, with M5 resolving clause truth
        # -------------------------------------------------

        validated: P3M5ValidationResult = (
            self.m4_validation_service
            .validate(
                draft=adapted.draft,
                manifest=adapted.manifest,
                clause_language=(
                    clause_language
                ),
                base_grounding_context=(
                    adapted
                    .grounding_context
                ),
            )
        )

        validated_draft = (
            validated.validated_draft
        )

        export_allowed = (
            validated_draft
            .validation
            .is_valid
            and not (
                validated_draft
                .requires_lawyer_review
            )
        )

        docx_result = None
        pdf_result = None

        # -------------------------------------------------
        # Mandatory validation gate
        # -------------------------------------------------

        if export_allowed and docx_path:

            if pdf_dir:
                (
                    docx_result,
                    pdf_result,
                ) = self.m1_service.export(
                    m1_draft,
                    docx_path=docx_path,
                    pdf_dir=pdf_dir,
                )

            else:
                docx_result = (
                    self.m1_service
                    .docx_exporter
                    .export(
                        m1_draft,
                        docx_path,
                    )
                )

        return P3GenerationResult(
            validated_draft=(
                validated_draft
            ),
            selected_clause_ids=tuple(
                clause.clause_id
                for clause
                in selected_clauses
            ),
            export_allowed=(
                export_allowed
            ),
            docx_result=docx_result,
            pdf_result=pdf_result,
            m5_resolved_clause_count=(
                validated
                .m5_resolved_clause_count
            ),
        )

    @staticmethod
    def _for_m1_language(
        clause: ApprovedClause,
        language: str,
    ) -> ApprovedClause:
        """
        M1 currently selects text_en first.

        Keep M1 unchanged and provide an assembly-only
        copy whose preferred text is the requested exact
        M5 language.

        The canonical M5 object is never modified.
        """

        target_text = (
            clause.text_ar
            if language == "ar"
            else clause.text_en
        )

        return clause.model_copy(
            update={
                "text_en": target_text,
                "text_ar": target_text,
            },
            deep=True,
        )
