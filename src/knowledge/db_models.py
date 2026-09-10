from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.knowledge.database import Base


class KnowledgeRecordORM(Base):
    __tablename__ = "knowledge_records"

    record_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    record_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    canonical_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    normalized_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    source_passages: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    validity_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="current",
        index=True,
    )

    effective_from: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    effective_to: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    supersedes_record_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    superseded_by_record_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    review: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    access: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )