from src.evaluation.m6_eval import (
    EvaluationCase,
    M6EvaluationSuite,
)
from src.knowledge.ingestion import KnowledgeIngestionService
from src.schemas.m6_knowledge import (
    KnowledgeRecordType,
    ValidityStatus,
)


def make_record(
    record_id: str,
    name: str,
    status: ValidityStatus = ValidityStatus.CURRENT,
):
    record = KnowledgeIngestionService().ingest(
        record_id=record_id,
        record_type=KnowledgeRecordType.CASE,
        canonical_name=name,
    )

    record.validity_status = status
    return record


def test_evaluate_current_record():
    record = make_record("case-001", "Case 001")

    case = EvaluationCase(
        case_id="eval-001",
        expected_record_id="case-001",
        expected_status=ValidityStatus.CURRENT,
    )

    result = M6EvaluationSuite().evaluate_record(
        case,
        record,
    )

    assert result.passed is True


def test_evaluate_wrong_status():
    record = make_record(
        "case-001",
        "Case 001",
        ValidityStatus.SUPERSEDED,
    )

    case = EvaluationCase(
        case_id="eval-002",
        expected_record_id="case-001",
        expected_status=ValidityStatus.CURRENT,
    )

    result = M6EvaluationSuite().evaluate_record(
        case,
        record,
    )

    assert result.passed is False


def test_deduplication_evaluation():
    first = make_record("person-001", "Ahmed Ali")
    duplicate = make_record("person-002", "ahmed ali")

    assert M6EvaluationSuite.evaluate_deduplication(
        first,
        duplicate,
        same_entity=True,
    )


def test_relationship_evaluation():
    assert M6EvaluationSuite.evaluate_relationship(
        "governed_by",
        "governed_by",
    )


def test_evaluation_summary():
    suite = M6EvaluationSuite()

    results = [
        suite.evaluate_record(
            EvaluationCase(
                case_id="1",
                expected_record_id="case-1",
                expected_status=ValidityStatus.CURRENT,
            ),
            make_record("case-1", "Case 1"),
        ),
        suite.evaluate_record(
            EvaluationCase(
                case_id="2",
                expected_record_id="case-2",
                expected_status=ValidityStatus.CURRENT,
            ),
            make_record(
                "case-2",
                "Case 2",
                ValidityStatus.SUPERSEDED,
            ),
        ),
    ]

    summary = suite.summarize(results)

    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["pass_rate"] == 0.5