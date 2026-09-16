from __future__ import annotations

from sqlalchemy import delete as sql_delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.knowledge.db_models import KnowledgeRecordORM
from src.knowledge.repository import KnowledgeRepository
from src.schemas.m6_knowledge import (
    AccessMetadata,
    KnowledgeRecord,
    KnowledgeRecordType,
    ReviewMetadata,
    SourcePassage,
    ValidityStatus,
)


class PostgresKnowledgeRepository(KnowledgeRepository):
    """
    Transactional PostgreSQL repository for canonical M6 knowledge records.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, record: KnowledgeRecord) -> KnowledgeRecord:
        """
        Insert or update a knowledge record.

        Matching priority:
        1. source_document_id
        2. record_id

        This prevents duplicate records when the same source document is
        ingested again with a different M1 record_id.
        """

        try:
            source_document_id = (
                record.normalized_data or {}
            ).get("source_document_id")

            existing: KnowledgeRecordORM | None = None

            # First try the stable source document identifier.
            if source_document_id:
                existing = self.session.scalar(
                    select(KnowledgeRecordORM).where(
                        KnowledgeRecordORM.source_document_id
                        == source_document_id
                    )
                )

            # Fallback to the canonical record ID.
            if existing is None:
                existing = self.session.get(
                    KnowledgeRecordORM,
                    record.record_id,
                )

            if existing is not None:
                # Keep the original database record ID.
                record.record_id = existing.record_id

                # Increment version on update.
                record.version = existing.version + 1

                # Preserve original creation timestamp.
                record.created_at = (
                    existing.created_at
                    or record.created_at
                )

                self._copy_to_row(existing, record)

            else:
                self.session.add(
                    self._row_from_schema(record)
                )

            self.session.commit()

            saved = self.session.get(
                KnowledgeRecordORM,
                record.record_id,
            )

            if saved is None:
                raise RuntimeError(
                    "Failed to persist knowledge record: "
                    f"{record.record_id}"
                )

            return self._to_schema(saved)

        except SQLAlchemyError:
            self.session.rollback()
            raise

    def get(
        self,
        record_id: str,
    ) -> KnowledgeRecord | None:
        row = self.session.get(
            KnowledgeRecordORM,
            record_id,
        )

        if row is None:
            return None

        return self._to_schema(row)

    def list_records(
        self,
        *,
        record_type: str | KnowledgeRecordType | None = None,
        validity_status: ValidityStatus | None = None,
    ) -> list[KnowledgeRecord]:
        statement = select(KnowledgeRecordORM)

        if record_type is not None:
            value = (
                record_type.value
                if isinstance(record_type, KnowledgeRecordType)
                else record_type
            )

            statement = statement.where(
                KnowledgeRecordORM.record_type == value
            )

        if validity_status is not None:
            statement = statement.where(
                KnowledgeRecordORM.validity_status
                == validity_status.value
            )

        statement = statement.order_by(
            KnowledgeRecordORM.record_id
        )

        rows = self.session.scalars(statement).all()

        return [
            self._to_schema(row)
            for row in rows
        ]

    def list_current(self) -> list[KnowledgeRecord]:
        return self.list_records(
            validity_status=ValidityStatus.CURRENT
        )

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
    def _row_from_schema(
        record: KnowledgeRecord,
    ) -> KnowledgeRecordORM:
        row = KnowledgeRecordORM(
            record_id=record.record_id,
        )

        PostgresKnowledgeRepository._copy_to_row(
            row,
            record,
        )

        return row

    @staticmethod
    def _copy_to_row(
        row: KnowledgeRecordORM,
        record: KnowledgeRecord,
    ) -> None:
        row.source_document_id = (
            record.normalized_data or {}
        ).get("source_document_id")

        row.record_type = record.record_type.value
        row.canonical_name = record.canonical_name
        row.normalized_data = record.normalized_data

        row.source_passages = [
            passage.model_dump(mode="json")
            for passage in record.source_passages
        ]

        row.validity_status = record.validity_status.value
        row.effective_from = record.effective_from
        row.effective_to = record.effective_to

        row.supersedes_record_id = (
            record.supersedes_record_id
        )

        row.superseded_by_record_id = (
            record.superseded_by_record_id
        )

        row.review = record.review.model_dump(
            mode="json"
        )

        row.access = record.access.model_dump(
            mode="json"
        )

        row.version = record.version
        row.created_at = record.created_at
        row.updated_at = record.updated_at

    @staticmethod
    def _to_schema(
        row: KnowledgeRecordORM,
    ) -> KnowledgeRecord:
        normalized_data = dict(
            row.normalized_data or {}
        )

        # Ensure the stable source ID is also available in the JSON payload.
        if row.source_document_id:
            normalized_data.setdefault(
                "source_document_id",
                row.source_document_id,
            )

        return KnowledgeRecord(
            record_id=row.record_id,
            record_type=KnowledgeRecordType(
                row.record_type
            ),
            canonical_name=row.canonical_name,
            normalized_data=normalized_data,
            source_passages=[
                SourcePassage(**item)
                for item in (row.source_passages or [])
            ],
            validity_status=ValidityStatus(
                row.validity_status
            ),
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            supersedes_record_id=(
                row.supersedes_record_id
            ),
            superseded_by_record_id=(
                row.superseded_by_record_id
            ),
            review=ReviewMetadata(
                **(row.review or {})
            ),
            access=AccessMetadata(
                **(row.access or {})
            ),
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )