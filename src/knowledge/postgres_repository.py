from __future__ import annotations

from sqlalchemy import delete as sql_delete, select
from sqlalchemy.exc import SQLAlchemyError
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
from src.knowledge.repository import KnowledgeRepository


class PostgresKnowledgeRepository(KnowledgeRepository):
    """Transactional PostgreSQL repository for canonical M6 knowledge records."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, record: KnowledgeRecord) -> KnowledgeRecord:
        try:
            existing = self.session.get(KnowledgeRecordORM, record.record_id)
            if existing is not None:
                record.version = existing.version + 1
                record.created_at = existing.created_at or record.created_at
                self._copy_to_row(existing, record)
            else:
                self.session.add(self._row_from_schema(record))

            self.session.commit()
            self.session.refresh(existing or self.session.get(KnowledgeRecordORM, record.record_id))
            return record
        except SQLAlchemyError:
            self.session.rollback()
            raise

    def get(self, record_id: str) -> KnowledgeRecord | None:
        row = self.session.get(KnowledgeRecordORM, record_id)
        return None if row is None else self._to_schema(row)

    def list_records(
        self,
        *,
        record_type: str | KnowledgeRecordType | None = None,
        validity_status: ValidityStatus | None = None,
    ) -> list[KnowledgeRecord]:
        statement = select(KnowledgeRecordORM)
        if record_type is not None:
            value = record_type.value if isinstance(record_type, KnowledgeRecordType) else record_type
            statement = statement.where(KnowledgeRecordORM.record_type == value)
        if validity_status is not None:
            statement = statement.where(
                KnowledgeRecordORM.validity_status == validity_status.value
            )
        statement = statement.order_by(KnowledgeRecordORM.record_id)
        return [self._to_schema(row) for row in self.session.scalars(statement).all()]

    def list_current(self) -> list[KnowledgeRecord]:
        return self.list_records(validity_status=ValidityStatus.CURRENT)

    def delete(self, record_id: str) -> bool:
        try:
            result = self.session.execute(
                sql_delete(KnowledgeRecordORM).where(
                    KnowledgeRecordORM.record_id == record_id
                )
            )
            self.session.commit()
            return bool(result.rowcount)
        except SQLAlchemyError:
            self.session.rollback()
            raise

    @staticmethod
    def _row_from_schema(record: KnowledgeRecord) -> KnowledgeRecordORM:
        row = KnowledgeRecordORM(record_id=record.record_id)
        PostgresKnowledgeRepository._copy_to_row(row, record)
        return row

    @staticmethod
    def _copy_to_row(row: KnowledgeRecordORM, record: KnowledgeRecord) -> None:
        row.record_type = record.record_type.value
        row.canonical_name = record.canonical_name
        row.normalized_data = record.normalized_data
        row.source_passages = [p.model_dump(mode="json") for p in record.source_passages]
        row.validity_status = record.validity_status.value
        row.effective_from = record.effective_from
        row.effective_to = record.effective_to
        row.supersedes_record_id = record.supersedes_record_id
        row.superseded_by_record_id = record.superseded_by_record_id
        row.review = record.review.model_dump(mode="json")
        row.access = record.access.model_dump(mode="json")
        row.version = record.version
        row.created_at = record.created_at
        row.updated_at = record.updated_at

    @staticmethod
    def _to_schema(row: KnowledgeRecordORM) -> KnowledgeRecord:
        return KnowledgeRecord(
            record_id=row.record_id,
            record_type=KnowledgeRecordType(row.record_type),
            canonical_name=row.canonical_name,
            normalized_data=row.normalized_data or {},
            source_passages=[SourcePassage(**item) for item in (row.source_passages or [])],
            validity_status=ValidityStatus(row.validity_status),
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            supersedes_record_id=row.supersedes_record_id,
            superseded_by_record_id=row.superseded_by_record_id,
            review=ReviewMetadata(**(row.review or {})),
            access=AccessMetadata(**(row.access or {})),
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
