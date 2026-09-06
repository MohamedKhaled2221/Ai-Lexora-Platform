"""
Traceability — تتبع استخدام البنود القانونية.

يسجل كل استخدام لبند في مستند مع بيانات كاملة
عن المصدر والإصدار والموقع.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from src.clause_engine.clause_library import ClauseLibrary
from src.schemas.m5_contract import (
    ProvenanceReport,
    TraceRecord,
)

logger = logging.getLogger(__name__)


class ClauseTraceability:
    """
    نظام تتبع استخدام البنود القانونية.

    يسجل كل استخدام لبند مع:
    - معرف البند والإصدار المستخدم
    - معرف المستند والقسم
    - من استخدمه ومتى
    """

    def __init__(
        self,
        clause_library: ClauseLibrary,
    ) -> None:
        self._clause_library = clause_library
        self._traces: list[TraceRecord] = []

    @property
    def trace_count(self) -> int:
        """عدد سجلات التتبع."""
        return len(self._traces)

    def record_usage(
        self,
        clause_id: str,
        document_id: str,
        section: str = "",
        used_by: str = "system",
    ) -> TraceRecord:
        """
        تسجيل استخدام بند في مستند.
        """
        clause = self._clause_library.get_clause(clause_id)

        trace = TraceRecord(
            trace_id=f"TRC-{uuid.uuid4().hex[:12]}",
            clause_id=clause_id,
            clause_version=clause.version,
            document_id=document_id,
            section=section,
            used_by=used_by,
        )

        self._traces.append(trace)

        logger.info(
            "Recorded usage of clause %s (v%s) in document %s",
            clause_id,
            clause.version,
            document_id,
        )

        return trace

    def get_clause_usage(
        self,
        clause_id: str,
    ) -> list[TraceRecord]:
        """استرجاع كل استخدامات بند معين."""
        return [
            trace
            for trace in self._traces
            if trace.clause_id == clause_id
        ]

    def get_document_clauses(
        self,
        document_id: str,
    ) -> list[TraceRecord]:
        """استرجاع كل البنود المستخدمة في مستند."""
        return [
            trace
            for trace in self._traces
            if trace.document_id == document_id
        ]

    def get_clause_usage_count(
        self,
        clause_id: str,
    ) -> int:
        """عدد مرات استخدام بند معين."""
        return len(self.get_clause_usage(clause_id))

    def get_all_traces(self) -> list[TraceRecord]:
        """استرجاع كل سجلات التتبع."""
        return list(self._traces)

    def generate_provenance_report(
        self,
        document_id: str,
    ) -> ProvenanceReport:
        """
        إنشاء تقرير مصدر وتتبع لمستند.
        """
        traces = self.get_document_clauses(document_id)

        return ProvenanceReport(
            document_id=document_id,
            traces=traces,
        )

    def get_usage_between(
        self,
        start: datetime,
        end: datetime,
    ) -> list[TraceRecord]:
        """استرجاع سجلات التتبع في فترة زمنية."""
        return [
            trace
            for trace in self._traces
            if start <= trace.used_at <= end
        ]

    def get_documents_using_clause(
        self,
        clause_id: str,
    ) -> list[str]:
        """قائمة المستندات التي تستخدم بند معين."""
        doc_ids: set[str] = set()
        for trace in self._traces:
            if trace.clause_id == clause_id:
                doc_ids.add(trace.document_id)
        return list(doc_ids)
