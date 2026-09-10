from src.knowledge.access_control import AccessControlService
from src.knowledge.ingestion import KnowledgeIngestionService
from src.knowledge.repository import InMemoryKnowledgeRepository
from src.schemas.m6_knowledge import (
    AccessLevel,
    AccessMetadata,
    KnowledgeRecordType,
    ValidityStatus,
)


def make_record(record_id: str, name: str):
    return KnowledgeIngestionService().ingest(
        record_id=record_id,
        record_type=KnowledgeRecordType.CASE,
        canonical_name=name,
    )


def test_repository_upsert_and_get():
    repo = InMemoryKnowledgeRepository()
    record = make_record("case-1", "Case One")

    repo.upsert(record)

    stored = repo.get("case-1")

    assert stored is not None
    assert stored.record_id == "case-1"


def test_repository_version_increments():
    repo = InMemoryKnowledgeRepository()
    record = make_record("case-1", "Case One")

    repo.upsert(record)
    assert record.version == 1

    repo.upsert(record)

    assert record.version == 2


def test_repository_filters_by_validity():
    repo = InMemoryKnowledgeRepository()

    current = make_record("case-1", "Current Case")
    review = make_record("case-2", "Review Case")
    review.validity_status = ValidityStatus.REVIEW_REQUIRED

    repo.upsert(current)
    repo.upsert(review)

    results = repo.list_records(
        validity_status=ValidityStatus.CURRENT
    )

    assert len(results) == 1
    assert results[0].record_id == "case-1"


def test_acl_blocks_wrong_client():
    record = make_record("case-1", "Private Case")
    record.access = AccessMetadata(
        access_level=AccessLevel.CONFIDENTIAL,
        client_id="client-1",
    )

    acl = AccessControlService()

    assert not acl.can_access(
        record,
        user_role="confidential",
        client_id="client-2",
    )


def test_acl_allows_correct_client():
    record = make_record("case-1", "Private Case")
    record.access = AccessMetadata(
        access_level=AccessLevel.CONFIDENTIAL,
        client_id="client-1",
    )

    acl = AccessControlService()

    assert acl.can_access(
        record,
        user_role="confidential",
        client_id="client-1",
    )