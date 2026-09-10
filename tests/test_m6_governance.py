from src.knowledge.governance import KnowledgeGovernanceService
from src.knowledge.relationships import (
    Relationship,
    RelationshipService,
)
from src.schemas.m6_knowledge import (
    KnowledgeRecordType,
    RelatedRecordQuery,
    ValidityStatus,
)
from src.knowledge.ingestion import KnowledgeIngestionService


def make_record(record_id: str, name: str):
    return KnowledgeIngestionService().ingest(
        record_id=record_id,
        record_type=KnowledgeRecordType.CASE,
        canonical_name=name,
    )


def test_mark_for_review():
    record = make_record("case-1", "Case 1")
    service = KnowledgeGovernanceService()

    service.mark_for_review(record, "Potentially outdated")

    assert record.validity_status == ValidityStatus.REVIEW_REQUIRED
    assert record.review.review_outcome == "Potentially outdated"
    assert record.review.reviewer is None


def test_mark_superseded():
    record = make_record("case-1", "Case 1")
    service = KnowledgeGovernanceService()

    service.mark_superseded(record, "case-2")

    assert record.validity_status == ValidityStatus.SUPERSEDED
    assert record.superseded_by_record_id == "case-2"
    assert not service.can_be_used_for_answer(record)


def test_approve_current():
    record = make_record("case-1", "Case 1")
    service = KnowledgeGovernanceService()

    service.mark_for_review(record, "Needs lawyer review")
    service.approve_current(record, "lawyer-001")

    assert record.validity_status == ValidityStatus.CURRENT
    assert record.review.reviewer == "lawyer-001"
    assert record.review.review_outcome == "approved"
    assert record.review.reviewed_at is not None
    assert service.can_be_used_for_answer(record)


def test_related_record_query():
    case = make_record("case-1", "Case 1")
    law = make_record("law-1", "Civil Law")

    relationships = RelationshipService()

    relationships.add_relationship(
        Relationship(
            relationship_id="rel-1",
            source_record_id=case.record_id,
            target_record_id=law.record_id,
            relationship_type="governed_by",
        )
    )

    results = relationships.query_related(
        RelatedRecordQuery(
            record_id="case-1",
            relationship_types=["governed_by"],
        ),
        {
            case.record_id: case,
            law.record_id: law,
        },
    )

    assert len(results) == 1
    assert results[0].record.record_id == "law-1"
    assert results[0].relationship_type == "governed_by"