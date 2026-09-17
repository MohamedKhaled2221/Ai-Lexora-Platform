from __future__ import annotations

import json
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from src.query_processor import (
    QueryProcessor,
)
from src.schemas.m2_contract import (
    IdentifierSet,
)


class M2EvaluationCase(BaseModel):
    """
    One deterministic M2 query-processing evaluation case.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    case_id: str
    category: str
    query: str

    expected_language: str

    expected_identifiers: IdentifierSet = Field(
        default_factory=IdentifierSet
    )

    expected_variant_contains: list[str] = Field(
        default_factory=list
    )


class M2EvaluationSuite(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    cases: list[M2EvaluationCase]


class M2EvaluationResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    case_id: str
    category: str

    original_preserved: bool
    language_correct: bool
    identifiers_correct: bool
    variants_correct: bool
    exact_identifiers_preserved: bool

    @property
    def passed(
        self,
    ) -> bool:
        return all(
            (
                self.original_preserved,
                self.language_correct,
                self.identifiers_correct,
                self.variants_correct,
                self.exact_identifiers_preserved,
            )
        )


def load_m2_evaluation_suite(
    path: Path,
) -> M2EvaluationSuite:
    data = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    return M2EvaluationSuite.model_validate(
        data
    )


class M2EvaluationRunner:
    """
    Deterministic evaluation for the M2-owned query-processing
    boundary.

    This runner intentionally does not depend on M3 retrieval.
    """

    def __init__(
        self,
        query_processor: QueryProcessor | None = None,
    ) -> None:
        self.query_processor = (
            query_processor
            or QueryProcessor()
        )

    def run_case(
        self,
        case: M2EvaluationCase,
    ) -> M2EvaluationResult:
        processed = (
            self.query_processor.process(
                case.query
            )
        )

        original_preserved = (
            processed.text_original
            == case.query
        )

        language_correct = (
            processed.language
            == case.expected_language
        )

        identifiers_correct = (
            processed.identifiers
            == case.expected_identifiers
        )

        variants_correct = all(
            any(
                expected
                in variant
                for variant
                in processed.query_variants
            )
            for expected
            in case.expected_variant_contains
        )

        exact_values = (
            *processed.identifiers.article_numbers,
            *processed.identifiers.case_numbers,
            *processed.identifiers.dates,
            *processed.identifiers.monetary_values,
            *processed.identifiers.party_names,
            *processed.identifiers.named_legal_terms,
        )

        exact_identifiers_preserved = all(
            all(
                value in variant
                for variant
                in processed.query_variants
            )
            for value
            in exact_values
        )

        return M2EvaluationResult(
            case_id=case.case_id,
            category=case.category,
            original_preserved=(
                original_preserved
            ),
            language_correct=(
                language_correct
            ),
            identifiers_correct=(
                identifiers_correct
            ),
            variants_correct=(
                variants_correct
            ),
            exact_identifiers_preserved=(
                exact_identifiers_preserved
            ),
        )

    def run(
        self,
        suite: M2EvaluationSuite,
    ) -> list[M2EvaluationResult]:
        return [
            self.run_case(
                case
            )
            for case in suite.cases
        ]
