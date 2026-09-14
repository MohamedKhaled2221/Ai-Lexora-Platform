from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.schemas.m6_knowledge import (
    AccessLevel,
    AccessMetadata,
    KnowledgeRecord,
    KnowledgeRecordType,
    SourcePassage,
)

try:
    from src.document_generator.schemas import (
        KnowledgePassage,
        NormalizedLegalRecord,
    )
except ImportError:
    from src.schemas.m1_contract import (
        KnowledgePassage,
        NormalizedLegalRecord,
    )


class KnowledgeIngestionService:
    """
    Create canonical M6 knowledge records.

    Supports:
    1. Direct M6 record creation used by M6 services and tests.
    2. Conversion of approved M1 NormalizedLegalRecord objects.
    """

    SOURCE_TYPE_MAPPING: dict[str, KnowledgeRecordType] = {
        "case": KnowledgeRecordType.CASE,
        "law": KnowledgeRecordType.LAW,
        "article": KnowledgeRecordType.ARTICLE,
    }

    def ingest(
        self,
        record: NormalizedLegalRecord | None = None,
        *,
        record_id: str | None = None,
        record_type: KnowledgeRecordType | None = None,
        canonical_name: str | None = None,
        normalized_data: dict[str, Any] | None = None,
        source_passages: list[SourcePassage] | None = None,
        access: AccessMetadata | None = None,
    ) -> KnowledgeRecord:
        """
        Create an M6 canonical record.

        Either provide an approved M1 NormalizedLegalRecord through
        ``record`` or provide the canonical M6 fields directly.
        """

        now = datetime.now(timezone.utc)

        # M1 -> M6 ingestion path
        if record is not None:
            return self._ingest_m1_record(record, now)

        # Direct M6 construction path
        if not record_id:
            raise ValueError("record_id is required.")

        if record_type is None:
            raise ValueError("record_type is required.")

        if not canonical_name or not canonical_name.strip():
            raise ValueError("canonical_name must not be empty.")

        safe_normalized_data = normalized_data or {}

        return KnowledgeRecord(
            record_id=record_id,
            record_type=record_type,
            canonical_name=canonical_name.strip(),
            normalized_data=safe_normalized_data,
            source_passages=source_passages or [],
            access=access
            or self._build_access_metadata(safe_normalized_data),
            created_at=now,
            updated_at=now,
        )

    def _ingest_m1_record(
        self,
        record: NormalizedLegalRecord,
        now: datetime,
    ) -> KnowledgeRecord:
        if not record.approved:
            raise ValueError(
                "Only approved M1 records may be ingested."
            )

        if not record.record_id or not record.record_id.strip():
            raise ValueError(
                "M1 record_id must not be empty."
            )

        if (
            not record.source_document_id
            or not record.source_document_id.strip()
        ):
            raise ValueError(
                "M1 source_document_id must not be empty."
            )

        if not record.passages:
            raise ValueError(
                "M1 record must contain at least one passage."
            )

        record_type = self._map_record_type(record.source_type)

        source_passages = [
            self._convert_passage(
                passage=passage,
                source_document_id=record.source_document_id,
            )
            for passage in record.passages
        ]

        source_metadata = record.metadata or {}

        normalized_data: dict[str, Any] = {
            "source_document_id": record.source_document_id,
            "source_type": record.source_type,
            "title": record.title,
            "jurisdiction": record.jurisdiction,
            "language": record.language,
            "metadata": source_metadata,
            "acl": source_metadata.get("acl"),
            "passage_metadata": [
                {
                    "passage_id": passage.passage_id,
                    "document_id": passage.document_id,
                    "text": passage.text,
                    "language": passage.language,
                    "page_start": passage.page_start,
                    "page_end": passage.page_end,
                    "section": passage.section,
                    "clause": passage.clause,
                    "heading": passage.heading,
                    "source_uri": passage.source_uri,
                    "metadata": passage.metadata,
                }
                for passage in record.passages
            ],
        }

        canonical_name = (
            record.title.strip()
            if record.title and record.title.strip()
            else record.source_document_id
        )

        return KnowledgeRecord(
            record_id=record.record_id,
            record_type=record_type,
            canonical_name=canonical_name,
            normalized_data=normalized_data,
            source_passages=source_passages,
            access=self._build_access_metadata(source_metadata),
            created_at=now,
            updated_at=now,
        )

    def _build_access_metadata(
        self,
        metadata: dict[str, Any] | None,
    ) -> AccessMetadata:
        """
        Convert upstream ACL/access metadata into M6 AccessMetadata.

        Unknown or privileged values are treated as restricted rather than
        being accidentally exposed as public.
        """

        metadata = metadata or {}

        raw_acl = (
            metadata.get("acl")
            or metadata.get("access_control")
            or metadata.get("permissions")
            or metadata.get("access")
        )

        raw_level: Any = None
        client_id = metadata.get("client_id")
        matter_id = metadata.get("matter_id")
        allowed_roles: Any = metadata.get("allowed_roles") or []
        acl_scope: str | None = None

        if isinstance(raw_acl, dict):
            raw_level = (
                raw_acl.get("access_level")
                or raw_acl.get("level")
                or raw_acl.get("visibility")
            )

            client_id = raw_acl.get("client_id", client_id)
            matter_id = raw_acl.get("matter_id", matter_id)

            allowed_roles = (
                raw_acl.get("allowed_roles")
                or raw_acl.get("roles")
                or allowed_roles
            )

            raw_scope = raw_acl.get("scope")
            if raw_scope is not None:
                acl_scope = str(raw_scope)

        elif raw_acl is not None:
            raw_level = raw_acl

        normalized_level = (
            str(raw_level).strip().lower()
            if raw_level is not None
            else None
        )

        if normalized_level == AccessLevel.PUBLIC.value:
            access_level = AccessLevel.PUBLIC
        elif normalized_level == AccessLevel.INTERNAL.value:
            access_level = AccessLevel.INTERNAL
        elif normalized_level == AccessLevel.CONFIDENTIAL.value:
            access_level = AccessLevel.CONFIDENTIAL
        else:
            # Includes restricted, privileged, _none, unknown, and missing
            access_level = AccessLevel.RESTRICTED

        if not isinstance(allowed_roles, list):
            allowed_roles = [allowed_roles]

        return AccessMetadata(
            access_level=access_level,
            acl_scope=acl_scope,
            client_id=client_id,
            matter_id=matter_id,
            allowed_roles=[
                str(role)
                for role in allowed_roles
                if role is not None
            ],
        )

    def _map_record_type(
        self,
        source_type: str,
    ) -> KnowledgeRecordType:
        normalized_source_type = source_type.strip().lower()

        try:
            return self.SOURCE_TYPE_MAPPING[normalized_source_type]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported M1 source_type: {source_type!r}. "
                "A mapping to an M6 KnowledgeRecordType is required."
            ) from exc

    @staticmethod
    def _convert_passage(
        passage: KnowledgePassage,
        source_document_id: str,
    ) -> SourcePassage:
        if (
            passage.page_start is not None
            and passage.page_start < 1
        ):
            raise ValueError(
                "Passage page_start must be greater than or equal to 1."
            )

        if (
            passage.page_start is not None
            and passage.page_end is not None
            and passage.page_end < passage.page_start
        ):
            raise ValueError(
                "Passage page_end cannot be before page_start."
            )

        return SourcePassage(
            source_id=source_document_id,
            source_uri=passage.source_uri,
            passage=passage.text,
            page=passage.page_start,
            chunk_id=passage.passage_id,
        )