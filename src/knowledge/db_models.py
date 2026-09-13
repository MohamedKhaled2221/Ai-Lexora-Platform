from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.knowledge.database import Base


class KnowledgeRecordORM(Base):
    __tablename__ = "knowledge_records"

    record_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    record_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_passages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    validity_status: Mapped[str] = mapped_column(String(30), nullable=False, default="current", index=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    supersedes_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    superseded_by_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    review: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    access: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_knowledge_records_type_status", "record_type", "validity_status"),
    )


class RelationshipORM(Base):
    __tablename__ = "knowledge_relationships"

    relationship_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_record_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_record_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "source_record_id",
            "target_record_id",
            "relationship_type",
            name="uq_knowledge_relationship_edge",
        ),
        Index(
            "ix_relationship_source_type",
            "source_record_id",
            "relationship_type",
        ),
    )
