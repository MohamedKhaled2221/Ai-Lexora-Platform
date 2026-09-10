from __future__ import annotations

from dataclasses import dataclass

from src.schemas.m6_knowledge import (
    KnowledgeRecord,
    RelatedRecord,
    RelatedRecordQuery,
)


@dataclass(frozen=True)
class Relationship:
    relationship_id: str
    source_record_id: str
    target_record_id: str
    relationship_type: str


class RelationshipService:
    """In-memory relationship service for the M6 domain layer."""

    def __init__(self) -> None:
        self._relationships: list[Relationship] = []

    def add_relationship(
        self,
        relationship: Relationship,
    ) -> None:
        if relationship not in self._relationships:
            self._relationships.append(relationship)

    def query_related(
        self,
        query: RelatedRecordQuery,
        records: dict[str, KnowledgeRecord],
    ) -> list[RelatedRecord]:
        results: list[RelatedRecord] = []

        for relationship in self._relationships:
            if relationship.source_record_id != query.record_id:
                continue

            target = records.get(relationship.target_record_id)

            if target is None:
                continue

            if (
                query.relationship_types
                and relationship.relationship_type
                not in query.relationship_types
            ):
                continue

            if (
                query.record_types
                and target.record_type not in query.record_types
            ):
                continue

            if (
                not query.include_superseded
                and target.validity_status.value == "superseded"
            ):
                continue

            results.append(
                RelatedRecord(
                    record=target,
                    relationship_type=relationship.relationship_type,
                    relationship_id=relationship.relationship_id,
                )
            )

            if len(results) >= query.limit:
                break

        return results