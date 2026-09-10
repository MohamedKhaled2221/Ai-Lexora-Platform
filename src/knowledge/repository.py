from __future__ import annotations

from abc import ABC, abstractmethod

from src.schemas.m6_knowledge import KnowledgeRecord, ValidityStatus


class KnowledgeRepository(ABC):
    """Authoritative repository interface for canonical legal knowledge."""

    @abstractmethod
    def upsert(self, record: KnowledgeRecord) -> KnowledgeRecord:
        raise NotImplementedError

    @abstractmethod
    def get(self, record_id: str) -> KnowledgeRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_records(
        self,
        *,
        record_type: str | None = None,
        validity_status: ValidityStatus | None = None,
    ) -> list[KnowledgeRecord]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, record_id: str) -> bool:
        raise NotImplementedError


class InMemoryKnowledgeRepository(KnowledgeRepository):
    """
    Deterministic repository used for tests and local development.

    PostgreSQL will implement the same interface as the authoritative store.
    """

    def __init__(self) -> None:
        self._records: dict[str, KnowledgeRecord] = {}

    def upsert(self, record: KnowledgeRecord) -> KnowledgeRecord:
        existing = self._records.get(record.record_id)

        if existing is not None:
            record.version = existing.version + 1

        self._records[record.record_id] = record
        return record

    def get(self, record_id: str) -> KnowledgeRecord | None:
        return self._records.get(record_id)

    def list_records(
        self,
        *,
        record_type: str | None = None,
        validity_status: ValidityStatus | None = None,
    ) -> list[KnowledgeRecord]:
        records = list(self._records.values())

        if record_type is not None:
            records = [
                r for r in records
                if r.record_type.value == record_type
            ]

        if validity_status is not None:
            records = [
                r for r in records
                if r.validity_status == validity_status
            ]

        return records

    def delete(self, record_id: str) -> bool:
        return self._records.pop(record_id, None) is not None