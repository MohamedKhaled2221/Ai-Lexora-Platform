from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Protocol
from uuid import uuid4

from .schemas import KnowledgePassage, NormalizedLegalRecord


class ExistingDocumentProcessor(Protocol):
    """Adapter contract for the existing Package 1 document-processing pipeline."""

    def process(self, source_path: str) -> Dict[str, Any]:
        ...


@dataclass
class KnowledgeIngestionAdapter:
    """Convert existing parser/OCR output into the M6-facing normalized contract."""

    processor: ExistingDocumentProcessor

    def ingest(
        self,
        source_path: str,
        *,
        document_id: str,
        source_type: str = "other",
        title: str | None = None,
        jurisdiction: str | None = None,
        approved: bool = True,
    ) -> NormalizedLegalRecord:
        if not approved:
            raise ValueError("Only approved sources may be passed to M6.")

        raw = self.processor.process(source_path)

        passages = self._normalize_passages(
            raw,
            document_id=document_id,
            source_uri=source_path,
        )

        return NormalizedLegalRecord(
            record_id=str(uuid4()),
            source_document_id=document_id,
            source_type=(
                source_type
                if source_type in {
                    "case",
                    "law",
                    "article",
                    "regulation",
                    "memo",
                    "other",
                }
                else "other"
            ),
            title=title,
            jurisdiction=jurisdiction,
            language=self._dominant_language(passages),
            approved=True,
            passages=passages,
            metadata={
                "ingestion_adapter": "m1",
                "source_path": source_path,
            },
        )

    def _normalize_passages(
        self,
        raw: Dict[str, Any],
        *,
        document_id: str,
        source_uri: str,
    ) -> List[KnowledgePassage]:
        items = (
            raw.get("passages")
            or raw.get("sections")
            or raw.get("chunks")
        )

        if items is None:
            raise ValueError(
                "Existing processor returned no passage list."
            )

        if not isinstance(items, list):
            raise ValueError(
                "Existing processor returned no passage list."
            )

        result: List[KnowledgePassage] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            text = str(
                item.get("text")
                or item.get("content")
                or ""
            ).strip()

            if not text:
                continue

            metadata = item.get("metadata")

            if not isinstance(metadata, dict):
                metadata = {}

            structure = metadata.get("structure")

            if not isinstance(structure, dict):
                structure = metadata.get("m1_structure")

            if not isinstance(structure, dict):
                structure = {}

            page = item.get("page")

            page_start = item.get(
                "page_start",
                page,
            )

            page_end = item.get(
                "page_end",
                page,
            )

            page_span = metadata.get("page_span")

            if isinstance(page_span, list) and page_span:
                nums = [
                    int(x)
                    for x in page_span
                    if isinstance(x, (int, float))
                    and not isinstance(x, bool)
                ]

                if nums:
                    page_start = min(nums)
                    page_end = max(nums)

            result.append(
                KnowledgePassage(
                    passage_id=str(
                        item.get("passage_id")
                        or item.get("chunk_id")
                        or uuid4()
                    ),
                    document_id=document_id,
                    text=text,
                    language=self._language(
                        item,
                        text,
                    ),
                    page_start=(
                        int(page_start)
                        if page_start is not None
                        else None
                    ),
                    page_end=(
                        int(page_end)
                        if page_end is not None
                        else None
                    ),
                    section=(
                        item.get("section")
                        or structure.get("section")
                    ),
                    clause=(
                        item.get("clause")
                        or structure.get("clause")
                    ),
                    heading=(
                        item.get("heading")
                        or metadata.get("heading")
                    ),
                    source_uri=source_uri,
                    metadata={
                        **metadata,
                        "structure": structure,
                    },
                )
            )

        return result

    @staticmethod
    def _language(
        item: Dict[str, Any],
        text: str,
    ) -> str:
        explicit = item.get("language")

        if explicit in {
            "ar",
            "en",
            "ar-en",
            "unknown",
        }:
            return explicit

        metadata = item.get("metadata")

        if isinstance(metadata, dict):
            explicit = metadata.get("language")

            if explicit in {
                "ar",
                "en",
                "ar-en",
                "unknown",
            }:
                return explicit

        has_ar = any(
            "\u0600" <= c <= "\u06ff"
            for c in text
        )

        has_en = any(
            ("A" <= c <= "Z")
            or ("a" <= c <= "z")
            for c in text
        )

        if has_ar and has_en:
            return "ar-en"

        if has_ar:
            return "ar"

        if has_en:
            return "en"

        return "unknown"

    @staticmethod
    def _dominant_language(
        passages: Iterable[KnowledgePassage],
    ) -> str:
        counts = {
            "ar": 0,
            "en": 0,
            "ar-en": 0,
            "unknown": 0,
        }

        for passage in passages:
            counts[passage.language] += 1

        return max(
            counts,
            key=counts.get,
        )