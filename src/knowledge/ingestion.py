from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.schemas.m6_knowledge import (
    KnowledgeRecord,
    KnowledgeRecordType,
    SourcePassage,
)


class KnowledgeIngestionService:
    """Normalize approved M1 records into canonical M6 KnowledgeRecords."""

    def ingest(
        self,
        *,
        record_id: str,
        record_type: KnowledgeRecordType,
        canonical_name: str,
        normalized_data: dict[str, Any] | None = None,
        source_passages: list[SourcePassage] | None = None,
    ) -> KnowledgeRecord:
        now = datetime.now(timezone.utc)

        return KnowledgeRecord(
            record_id=record_id,
            record_type=record_type,
            canonical_name=canonical_name.strip(),
            normalized_data=normalized_data or {},
            source_passages=source_passages or [],
            created_at=now,
            updated_at=now,
        )