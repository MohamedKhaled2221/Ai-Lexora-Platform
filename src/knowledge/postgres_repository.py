from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.knowledge.db_models import KnowledgeRecordORM
from src.schemas.m6_knowledge import (
    AccessMetadata,
    KnowledgeRecord,
    KnowledgeRecordType,
    ReviewMetadata,
    SourcePassage,
    ValidityStatus,
)


class PostgresKnowledgeRepository:
    """PostgreSQL-backed authoritative M6 knowledge repository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, record: KnowledgeRecord) -> KnowledgeRecord:
        existing = self.session.get(
            KnowledgeRecordORM,
            record.record_id,
        )

        if existing is not None:
            record.version = existing.version + 1

            existing.record_type = record.record_type.value
            existing.canonical_name = record.canonical_name
            existing.normalized_data = record.normalized_data
            existing.source_passages = [
                passage.model_dump()
                for passage in record.source_passages
            ]
            existing.validity_status = record.validity_status.value
            existing.effective_from = record.effective_from
            existing.effective_to = record.effective_to
            existing.supersedes_record_id = record.supersedes_record_id
            existing.superseded_by_record_id = record.superseded_by_record_id
            existing.review = record.review.model_dump()
            existing.access = record.access.model_dump()
            existing.version = record.version
            existing.updated_at = record.updated_at
        else:
            row = KnowledgeRecordORM(
                record_id=record.record_id,
                record_type=record.record_type.value,
                canonical_name=record.canonical_name,
                normalized_data=record.normalized_data,
                source_passages=[
                    passage.model_dump()
                    for passage in record.source_passages
                ],
                validity_status=record.validity_status.value,
                effective_from=record.effective_from,
                effective_to=record.effective_to,
                supersedes_record_id=record.supersedes_record_id,
                superseded_by_record_id=record.superseded_by_record_id,
                review=record.review.model_dump(),
                access=record.access.model_dump(),
                version=record.version,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )

            self.session.add(row)

        self.session.commit()

        return record

    def get(self, record_id: str) -> KnowledgeRecord | None:
        row = self.session.get(
            KnowledgeRecordORM,
            record_id,
        )

        if row is None:
            return None

        return self._to_schema(row)

    def list_current(self) -> list[KnowledgeRecord]:
        statement = select(KnowledgeRecordORM).where(
            KnowledgeRecordORM.validity_status
            == ValidityStatus.CURRENT.value
        )

        rows = self.session.scalars(statement).all()

        return [
            self._to_schema(row)
            for row in rows
        ]

    @staticmethod
    def _to_schema(
        row: KnowledgeRecordORM,
    ) -> KnowledgeRecord:
        return KnowledgeRecord(
            record_id=row.record_id,
            record_type=KnowledgeRecordType(row.record_type),
            canonical_name=row.canonical_name,
            normalized_data=row.normalized_data,
            source_passages=[
                SourcePassage(**item)
                for item in row.source_passages
            ],
            validity_status=ValidityStatus(row.validity_status),
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            supersedes_record_id=row.supersedes_record_id,
            superseded_by_record_id=row.superseded_by_record_id,
            review=ReviewMetadata(**row.review),
            access=AccessMetadata(**row.access),
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )