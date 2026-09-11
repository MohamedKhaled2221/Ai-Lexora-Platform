from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .errors import TemplateNotFoundError
from .schemas import ApprovedClause


class ClauseLibrary:
    def __init__(self, clauses: Iterable[ApprovedClause] = ()):
        self._clauses: Dict[tuple[str, str], ApprovedClause] = {}

        for clause in clauses:
            self.register(clause)

    def register(self, clause: ApprovedClause) -> None:
        self._clauses[(clause.clause_id, clause.version)] = clause

    @classmethod
    def from_json(cls, file_path: str | Path) -> "ClauseLibrary":
        """
        Load approved clauses from M5's clause_library.json.
        """

        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(
                f"Clause library file not found: {path}"
            )

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        clauses_data = data.get("clauses", [])

        clauses: List[ApprovedClause] = []

        for clause_data in clauses_data:
            metadata = clause_data.get("metadata", {})

            if not isinstance(metadata, dict):
                metadata = {}

            clause = ApprovedClause(
                clause_id=clause_data["clause_id"],
                type=clause_data["type"],
                jurisdiction=clause_data["jurisdiction"],
                document_types=clause_data.get("document_types", []),
                version=clause_data["version"],
                approval_status=clause_data["approval_status"],
                effective_date=clause_data.get("effective_date"),
                expiry_date=clause_data.get("expiry_date"),
                owner=clause_data.get("owner"),
                source=clause_data.get("source"),
                text_ar=clause_data.get("text_ar"),
                text_en=clause_data.get("text_en"),
                metadata=metadata,
                superseded_by=clause_data.get("superseded_by"),
                supersedes=clause_data.get("supersedes"),
                is_lawyer_edited=clause_data.get(
                    "is_lawyer_edited",
                    False,
                ),
                requires_separate_approval=clause_data.get(
                    "requires_separate_approval",
                    False,
                ),
                tags=clause_data.get("tags", []),
                created_at=clause_data.get("created_at"),
                updated_at=clause_data.get("updated_at"),
                insertion_key=clause_data.get("insertion_key")
                or metadata.get("insertion_key"),
            )

            clauses.append(clause)

        return cls(clauses)

    def get(
        self,
        clause_id: str,
        version: Optional[str] = None,
    ) -> ApprovedClause:

        matches = [
            clause
            for (clause_id_key, _), clause in self._clauses.items()
            if clause_id_key == clause_id
            and clause.approval_status == "approved"
        ]

        if version is not None:
            for clause in matches:
                if clause.version == version:
                    return clause

        if matches:
            return sorted(
                matches,
                key=lambda clause: clause.version,
            )[-1]

        raise TemplateNotFoundError(
            f"Approved clause not found: {clause_id}"
        )

    def list_approved(self) -> List[ApprovedClause]:
        return [
            clause
            for clause in self._clauses.values()
            if clause.approval_status == "approved"
        ]

    def get_for_document(
        self,
        document_type: str,
        jurisdiction: str,
    ) -> List[ApprovedClause]:

        return [
            clause
            for clause in self.list_approved()
            if document_type in clause.document_types
            and clause.jurisdiction == jurisdiction
        ]