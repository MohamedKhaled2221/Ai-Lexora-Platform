from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from src.knowledge.db_models import RelationshipORM
from src.schemas.m6_knowledge import KnowledgeRecord, RelatedRecord, RelatedRecordQuery


@dataclass(frozen=True)
class Relationship:
    relationship_id: str
    source_record_id: str
    target_record_id: str
    relationship_type: str


class RelationshipService:
    """Persistent relationship service with an in-memory compatibility mode for tests."""

    def __init__(self, session: Session | None = None) -> None:
        self.session = session
        self._relationships: list[Relationship] = []

    def add_relationship(self, relationship: Relationship) -> None:
        if self.session is None:
            if relationship not in self._relationships:
                self._relationships.append(relationship)
            return

        row = RelationshipORM(
            relationship_id=relationship.relationship_id,
            source_record_id=relationship.source_record_id,
            target_record_id=relationship.target_record_id,
            relationship_type=relationship.relationship_type,
            created_at=datetime.now(timezone.utc),
        )
        try:
            self.session.add(row)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(
                select(RelationshipORM).where(
                    RelationshipORM.source_record_id == relationship.source_record_id,
                    RelationshipORM.target_record_id == relationship.target_record_id,
                    RelationshipORM.relationship_type == relationship.relationship_type,
                )
            )
            if existing is None:
                raise
        except SQLAlchemyError:
            self.session.rollback()
            raise

    def query_related(
        self,
        query: RelatedRecordQuery,
        records: dict[str, KnowledgeRecord],
    ) -> list[RelatedRecord]:
        relationships = self._load_relationships(query.record_id)
        results: list[RelatedRecord] = []

        for relationship in relationships:
            target = records.get(relationship.target_record_id)
            if target is None:
                continue
            if query.relationship_types and relationship.relationship_type not in query.relationship_types:
                continue
            if query.record_types and target.record_type not in query.record_types:
                continue
            if not query.include_superseded and target.validity_status.value == "superseded":
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

    def _load_relationships(self, source_record_id: str) -> list[Relationship]:
        if self.session is None:
            return [r for r in self._relationships if r.source_record_id == source_record_id]

        rows = self.session.scalars(
            select(RelationshipORM)
            .where(RelationshipORM.source_record_id == source_record_id)
            .order_by(RelationshipORM.relationship_id)
        ).all()
        return [
            Relationship(
                relationship_id=row.relationship_id,
                source_record_id=row.source_record_id,
                target_record_id=row.target_record_id,
                relationship_type=row.relationship_type,
            )
            for row in rows
        ]
