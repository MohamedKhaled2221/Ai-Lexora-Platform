from __future__ import annotations

import re
import unicodedata

from src.schemas.m6_knowledge import KnowledgeRecord


class EntityResolutionService:
    """Resolve duplicate entities using deterministic normalization first."""

    @staticmethod
    def normalize_name(name: str) -> str:
        value = unicodedata.normalize("NFKC", name)
        value = value.strip().lower()
        value = re.sub(r"\s+", " ", value)
        return value

    def is_same_entity(
        self,
        left: KnowledgeRecord,
        right: KnowledgeRecord,
    ) -> bool:
        if left.record_type != right.record_type:
            return False

        return (
            self.normalize_name(left.canonical_name)
            == self.normalize_name(right.canonical_name)
        )

    def find_match(
        self,
        record: KnowledgeRecord,
        candidates: list[KnowledgeRecord],
    ) -> KnowledgeRecord | None:
        for candidate in candidates:
            if self.is_same_entity(record, candidate):
                return candidate

        return None