"""
Versioning & Supersession — إدارة إصدارات البنود واستبدالها.

يدير دورة حياة إصدارات البنود القانونية بما يشمل:
- Semantic Versioning (MAJOR.MINOR.PATCH)
- سلسلة الاستبدال (supersession chain)
- تاريخ الإصدارات والتراجع
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.clause_engine.clause_library import ClauseLibrary
from src.schemas.m5_contract import (
    ApprovalStatus,
    ApprovedClause,
    VersionEntry,
)

logger = logging.getLogger(__name__)


class VersioningError(Exception):
    """خطأ في إدارة الإصدارات."""


class ClauseVersionManager:
    """
    مدير إصدارات البنود القانونية.

    Semantic Versioning:
    - MAJOR: تغيير في المعنى القانوني
    - MINOR: تحسين صياغة بدون تغيير المعنى
    - PATCH: تصحيح إملائي / تنسيقي
    """

    def __init__(
        self,
        clause_library: ClauseLibrary,
    ) -> None:
        self._clause_library = clause_library
        self._version_history: dict[
            str, list[VersionEntry]
        ] = {}

    def create_version(
        self,
        clause_id: str,
        changes: str,
        bump: str = "patch",
        created_by: str = "system",
    ) -> ApprovedClause:
        """
        إنشاء إصدار جديد لبند.

        bump: "major", "minor", or "patch"
        """
        clause = self._clause_library.get_clause(clause_id)

        old_version = clause.version
        new_version = self._bump_version(
            old_version, bump
        )

        # Record the current version in history
        snapshot = clause.model_dump(mode="json")
        entry = VersionEntry(
            version=old_version,
            clause_id=clause_id,
            changes=f"Snapshot before bump to {new_version}",
            created_by=created_by,
            clause_snapshot=snapshot,
        )

        if clause_id not in self._version_history:
            self._version_history[clause_id] = []
        self._version_history[clause_id].append(entry)

        # Update clause with new version
        updated = self._clause_library.update_clause(
            clause_id,
            version=new_version,
        )

        logger.info(
            "Clause %s: version %s → %s (%s)",
            clause_id,
            old_version,
            new_version,
            changes,
        )

        return updated

    def supersede(
        self,
        old_clause_id: str,
        new_clause_id: str,
    ) -> tuple[ApprovedClause, ApprovedClause]:
        """
        استبدال بند قديم ببند جديد.

        يضع البند القديم في حالة SUPERSEDED
        ويربط البندين ببعض.
        """
        old_clause = self._clause_library.get_clause(
            old_clause_id
        )
        new_clause = self._clause_library.get_clause(
            new_clause_id
        )

        if old_clause.approval_status == ApprovalStatus.SUPERSEDED:
            raise VersioningError(
                f"Clause {old_clause_id} is already superseded"
            )

        # Update old clause
        updated_old = self._clause_library.update_clause(
            old_clause_id,
            approval_status=ApprovalStatus.SUPERSEDED,
            superseded_by=new_clause_id,
        )

        # Update new clause
        updated_new = self._clause_library.update_clause(
            new_clause_id,
            supersedes=old_clause_id,
        )

        logger.info(
            "Clause %s superseded by %s",
            old_clause_id,
            new_clause_id,
        )

        return updated_old, updated_new

    def get_version_history(
        self,
        clause_id: str,
    ) -> list[VersionEntry]:
        """استرجاع تاريخ إصدارات بند."""
        return list(
            self._version_history.get(clause_id, [])
        )

    def get_latest_version(
        self,
        clause_id: str,
    ) -> ApprovedClause:
        """
        استرجاع آخر إصدار من البند.

        لو البند superseded، يتتبع السلسلة لآخر بند.
        """
        clause = self._clause_library.get_clause(clause_id)

        max_hops = 20
        hops = 0

        while (
            clause.superseded_by
            and hops < max_hops
        ):
            next_clause = self._clause_library.get_clause_or_none(
                clause.superseded_by
            )
            if next_clause is None:
                break
            clause = next_clause
            hops += 1

        return clause

    def rollback(
        self,
        clause_id: str,
        target_version: str,
    ) -> ApprovedClause:
        """
        التراجع إلى إصدار سابق.

        يبحث في تاريخ الإصدارات عن اللقطة المطلوبة
        ويستعيدها.
        """
        history = self._version_history.get(
            clause_id, []
        )

        target_entry: VersionEntry | None = None
        for entry in history:
            if entry.version == target_version:
                target_entry = entry
                break

        if target_entry is None:
            raise VersioningError(
                f"Version {target_version} not found "
                f"in history for clause {clause_id}"
            )

        if not target_entry.clause_snapshot:
            raise VersioningError(
                f"No snapshot available for version "
                f"{target_version} of clause {clause_id}"
            )

        # Restore from snapshot but keep current clause_id
        snapshot = dict(target_entry.clause_snapshot)
        snapshot["clause_id"] = clause_id
        snapshot["updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        restored_clause = ApprovedClause.model_validate(
            snapshot
        )

        # Save current state before rollback
        current = self._clause_library.get_clause(clause_id)
        current_entry = VersionEntry(
            version=current.version,
            clause_id=clause_id,
            changes=f"Snapshot before rollback to {target_version}",
            created_by="system",
            clause_snapshot=current.model_dump(mode="json"),
        )
        self._version_history[clause_id].append(
            current_entry
        )

        # Replace clause in library
        self._clause_library._clauses[clause_id] = (
            restored_clause
        )

        logger.info(
            "Clause %s rolled back to version %s",
            clause_id,
            target_version,
        )

        return restored_clause

    def compare_versions(
        self,
        clause_id: str,
        version_a: str,
        version_b: str,
    ) -> dict:
        """
        مقارنة إصدارين لبند معين.

        يرجع الفروقات بين الإصدارين.
        """
        history = self._version_history.get(
            clause_id, []
        )

        snapshot_a: dict | None = None
        snapshot_b: dict | None = None

        for entry in history:
            if entry.version == version_a:
                snapshot_a = entry.clause_snapshot
            if entry.version == version_b:
                snapshot_b = entry.clause_snapshot

        if snapshot_a is None:
            raise VersioningError(
                f"Version {version_a} not found for {clause_id}"
            )
        if snapshot_b is None:
            raise VersioningError(
                f"Version {version_b} not found for {clause_id}"
            )

        diffs: dict = {}
        all_keys = set(snapshot_a.keys()) | set(
            snapshot_b.keys()
        )

        for key in all_keys:
            val_a = snapshot_a.get(key)
            val_b = snapshot_b.get(key)
            if val_a != val_b:
                diffs[key] = {
                    "from": val_a,
                    "to": val_b,
                }

        return diffs

    @staticmethod
    def _bump_version(
        version: str,
        bump: str,
    ) -> str:
        """
        زيادة رقم الإصدار.

        version: "1.2.3"
        bump: "major" → "2.0.0"
              "minor" → "1.3.0"
              "patch" → "1.2.4"
        """
        parts = version.split(".")
        if len(parts) != 3:
            raise VersioningError(
                f"Invalid version format: {version}"
            )

        try:
            major, minor, patch = (
                int(parts[0]),
                int(parts[1]),
                int(parts[2]),
            )
        except ValueError as exc:
            raise VersioningError(
                f"Invalid version format: {version}"
            ) from exc

        if bump == "major":
            return f"{major + 1}.0.0"
        elif bump == "minor":
            return f"{major}.{minor + 1}.0"
        elif bump == "patch":
            return f"{major}.{minor}.{patch + 1}"
        else:
            raise VersioningError(
                f"Invalid bump type: {bump}. "
                f"Must be major, minor, or patch"
            )
