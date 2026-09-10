from __future__ import annotations

from src.schemas.m6_knowledge import AccessLevel, AccessMetadata, KnowledgeRecord


class AccessControlService:
    """Apply M6 access rules before knowledge reaches retrieval/generation."""

    ROLE_LEVELS = {
        "public": 0,
        "internal": 1,
        "confidential": 2,
        "restricted": 3,
    }

    def can_access(
        self,
        record: KnowledgeRecord,
        *,
        user_role: str,
        client_id: str | None = None,
        matter_id: str | None = None,
    ) -> bool:
        access = record.access

        if not self._role_allowed(access, user_role):
            return False

        if access.client_id is not None and access.client_id != client_id:
            return False

        if access.matter_id is not None and access.matter_id != matter_id:
            return False

        return True

    def filter_records(
        self,
        records: list[KnowledgeRecord],
        *,
        user_role: str,
        client_id: str | None = None,
        matter_id: str | None = None,
    ) -> list[KnowledgeRecord]:
        return [
            record
            for record in records
            if self.can_access(
                record,
                user_role=user_role,
                client_id=client_id,
                matter_id=matter_id,
            )
        ]

    def _role_allowed(
        self,
        access: AccessMetadata,
        user_role: str,
    ) -> bool:
        if access.allowed_roles and user_role not in access.allowed_roles:
            return False

        required_level = self.ROLE_LEVELS[access.access_level.value]
        user_level = self.ROLE_LEVELS.get(user_role, -1)

        return user_level >= required_level