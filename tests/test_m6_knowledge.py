from src.knowledge.entity_resolution import EntityResolutionService
from src.knowledge.ingestion import KnowledgeIngestionService
from src.schemas.m6_knowledge import (
    KnowledgeRecordType,
    ValidityStatus,
)


def test_ingestion_creates_canonical_record():
    service = KnowledgeIngestionService()

    record = service.ingest(
        record_id="case-001",
        record_type=KnowledgeRecordType.CASE,
        canonical_name="Case 001",
        normalized_data={"court": "Cairo"},
    )

    assert record.record_id == "case-001"
    assert record.record_type == KnowledgeRecordType.CASE
    assert record.canonical_name == "Case 001"
    assert record.validity_status == ValidityStatus.CURRENT
    assert record.version == 1


def test_entity_resolution_matches_normalized_names():
    ingestion = KnowledgeIngestionService()
    resolver = EntityResolutionService()

    first = ingestion.ingest(
        record_id="person-001",
        record_type=KnowledgeRecordType.PERSON,
        canonical_name="Ahmed   Ali",
    )

    duplicate = ingestion.ingest(
        record_id="person-002",
        record_type=KnowledgeRecordType.PERSON,
        canonical_name=" ahmed ali ",
    )

    assert resolver.is_same_entity(first, duplicate)


def test_entity_resolution_rejects_different_types():
    ingestion = KnowledgeIngestionService()
    resolver = EntityResolutionService()

    person = ingestion.ingest(
        record_id="person-001",
        record_type=KnowledgeRecordType.PERSON,
        canonical_name="Cairo Court",
    )

    court = ingestion.ingest(
        record_id="court-001",
        record_type=KnowledgeRecordType.COURT,
        canonical_name="Cairo Court",
    )

    assert not resolver.is_same_entity(person, court)