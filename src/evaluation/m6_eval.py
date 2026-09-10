from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.schemas.m6_knowledge import (
    KnowledgeRecord,
    ValidityStatus,
)


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    expected_record_id: str | None
    expected_status: ValidityStatus | None
    expected_relationship: str | None = None


@dataclass(frozen=True)
class EvaluationResult:
    case_id: str
    passed: bool
    checks: dict[str, bool]


class M6EvaluationSuite:
    """Shared evaluation checks for M6 knowledge and governance."""

    def evaluate_record(
        self,
        case: EvaluationCase,
        record: KnowledgeRecord | None,
    ) -> EvaluationResult:

        checks: dict[str, bool] = {
            "record_identity": (
                record is not None
                and record.record_id == case.expected_record_id
            ),
            "validity_status": (
                record is not None
                and (
                    case.expected_status is None
                    or record.validity_status == case.expected_status
                )
            ),
        }

        return EvaluationResult(
            case_id=case.case_id,
            passed=all(checks.values()),
            checks=checks,
        )

    @staticmethod
    def evaluate_deduplication(
        original: KnowledgeRecord,
        duplicate: KnowledgeRecord,
        same_entity: bool,
    ) -> bool:
        return (
            original.record_type == duplicate.record_type
            and same_entity
        )

    @staticmethod
    def evaluate_relationship(
        relationship_type: str | None,
        expected_relationship: str | None,
    ) -> bool:
        if expected_relationship is None:
            return relationship_type is not None

        return relationship_type == expected_relationship

    @staticmethod
    def summarize(
        results: list[EvaluationResult],
    ) -> dict[str, Any]:
        total = len(results)
        passed = sum(result.passed for result in results)

        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": (
                passed / total
                if total
                else 0.0
            ),
        }