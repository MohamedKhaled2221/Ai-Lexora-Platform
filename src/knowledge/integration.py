from __future__ import annotations

import re
from collections.abc import Sequence

from src.knowledge.access_control import (
    AccessControlService,
)
from src.knowledge.conversation_policy import (
    ConversationPolicyService,
)
from src.knowledge.governance import (
    KnowledgeGovernanceService,
)
from src.knowledge.relationships import (
    RelationshipService,
)
from src.knowledge.repository import (
    KnowledgeRepository,
)
from src.schemas.m4_contract import (
    RetrievedEvidence,
)
from src.schemas.m6_knowledge import (
    EvidenceSufficiencyResult,
    RelatedRecordQuery,
    ValidityStatus,
)
from src.schemas.p4_chat_contract import (
    AnswerGenerationRequest,
    ResponseLanguage,
    SafeContextTurn,
)


class KnowledgeIntegrationService:
    """
    M6 integration layer between canonical knowledge,
    M3 RetrievedEvidence, conversation policy, and the
    shared Package 4 M6 -> M4 contract.

    M6 does not create final citation metadata.
    M4 resolves citations from trusted RetrievedEvidence.
    """

    def __init__(
        self,
        repository: KnowledgeRepository,
        relationship_service: (
            RelationshipService
        ),
        access_control: AccessControlService,
        governance: KnowledgeGovernanceService,
        conversation_policy: (
            ConversationPolicyService
            | None
        ) = None,
    ) -> None:
        self.repository = repository
        self.relationship_service = (
            relationship_service
        )
        self.access_control = access_control
        self.governance = governance
        self.conversation_policy = (
            conversation_policy
            or ConversationPolicyService()
        )

    def retrieve_related(
        self,
        query: RelatedRecordQuery,
        *,
        user_role: str,
        client_id: str | None = None,
        matter_id: str | None = None,
    ):
        source = self.repository.get(
            query.record_id
        )

        if source is None:
            return []

        if not self.governance.can_be_used_for_answer(
            source
        ):
            return []

        if not self.access_control.can_access(
            source,
            user_role=user_role,
            client_id=client_id,
            matter_id=matter_id,
        ):
            return []

        records = {
            record.record_id: record
            for record
            in self.repository.list_records()
        }

        records = {
            record_id: record
            for record_id, record
            in records.items()
            if self.access_control.can_access(
                record,
                user_role=user_role,
                client_id=client_id,
                matter_id=matter_id,
            )
            and (
                self.governance
                .can_be_used_for_answer(
                    record
                )
            )
        }

        return (
            self.relationship_service
            .query_related(
                query,
                records,
            )
        )

    def evaluate_evidence(
        self,
        evidence: RetrievedEvidence,
        *,
        original_query: str | None = None,
    ) -> EvidenceSufficiencyResult:
        """
        Evaluate the trusted M3 evidence package.

        M6 does not convert RetrievedEvidence into
        dictionaries and does not manufacture citations.
        """

        items = evidence.retrieved_evidence

        if not items:
            return EvidenceSufficiencyResult(
                sufficient=False,
                score=0.0,
                reason=(
                    "No evidence was retrieved."
                ),
                missing_information=[
                    "Relevant legal evidence"
                ],
                requires_follow_up=True,
            )

        valid_evidence = [
            item
            for item in items
            if item.text.strip()
        ]

        if not valid_evidence:
            return EvidenceSufficiencyResult(
                sufficient=False,
                score=0.0,
                reason=(
                    "Retrieved evidence contains "
                    "no usable passages."
                ),
                missing_information=[
                    "Usable source passages"
                ],
                requires_follow_up=True,
            )

        requested_titles = (
            self._explicit_document_titles(
                original_query
            )
        )

        if requested_titles:
            available_titles = {
                self._normalize_document_title(
                    item.title
                )
                for item in valid_evidence
                if (
                    item.title is not None
                    and item.title.strip()
                )
            }

            missing_titles = [
                title
                for title in requested_titles
                if (
                    self._normalize_document_title(
                        title
                    )
                    not in available_titles
                )
            ]

            if missing_titles:
                return EvidenceSufficiencyResult(
                    sufficient=False,
                    score=0.0,
                    reason=(
                        "Retrieved evidence does not "
                        "contain the explicitly requested "
                        "document."
                    ),
                    missing_information=[
                        f"Requested document: {title}"
                        for title in missing_titles
                    ],
                    requires_follow_up=True,
                )

        score = min(
            1.0,
            len(valid_evidence) / 3,
        )

        return EvidenceSufficiencyResult(
            sufficient=True,
            score=score,
            reason=(
                "Usable legal evidence is "
                "available."
            ),
            missing_information=[],
            requires_follow_up=False,
        )

    @staticmethod
    def _normalize_document_title(
        value: str,
    ) -> str:
        return " ".join(
            value.casefold().split()
        )

    @staticmethod
    def _explicit_document_titles(
        query: str | None,
    ) -> list[str]:
        """
        Extract only strong English title-like references.

        This is intentionally narrow. It is a safety/sufficiency
        control, not general entity extraction.

        Examples:
        - Current Employment Agreement
        - Internal Test Document
        - Injection Resistance Document
        - Agreement Pending Review
        - Contract A

        Generic lowercase descriptions such as
        "Arabic test contract" are deliberately not treated as
        canonical-title requirements.
        """
        if query is None or not query.strip():
            return []

        patterns = (
            (
                r"\b("
                r"(?:[A-Z][A-Za-z0-9'&./-]*\s+){1,6}"
                r"(?:Agreement|Contract|Document)"
                r")\b"
            ),
            (
                r"\b("
                r"(?:Agreement|Contract|Document)"
                r"(?:\s+[A-Z][A-Za-z0-9'&./-]*){1,6}"
                r")\b"
            ),
        )

        titles: list[str] = []
        seen: set[str] = set()

        for pattern in patterns:
            for match in re.finditer(
                pattern,
                query,
            ):
                title = match.group(1).strip()

                normalized = (
                    KnowledgeIntegrationService
                    ._normalize_document_title(
                        title
                    )
                )

                if normalized in seen:
                    continue

                seen.add(normalized)
                titles.append(title)

        return titles

    def build_answer_request(
        self,
        *,
        request_id: str,
        original_query: str,
        response_language: (
            ResponseLanguage
            | str
            | None
        ),
        retrieved_evidence: RetrievedEvidence,
        record_statuses: Sequence[
            ValidityStatus
        ] = (),
        safe_context: Sequence[
            SafeContextTurn
        ] = (),
        response_instructions: Sequence[
            str
        ] = (),
    ) -> AnswerGenerationRequest:
        """
        Build the one authoritative M6 -> M4
        Package 4 request.

        Trusted legal evidence remains in
        RetrievedEvidence.

        M6 decides policy and sufficiency only.
        Citation metadata is resolved later by M4.
        """

        evidence_result = (
            self.evaluate_evidence(
                retrieved_evidence,
                original_query=original_query,
            )
        )

        context = list(
            safe_context
        )

        policy = (
            self.conversation_policy.decide(
                requested_language=(
                    response_language
                ),
                evidence_result=(
                    evidence_result
                ),
                record_statuses=list(
                    record_statuses
                ),
                has_follow_up_context=(
                    bool(context)
                ),
            )
        )

        evidence_sufficient = (
            evidence_result.sufficient
            and policy.allow_generation
        )

        insufficiency_reason: (
            str | None
        ) = None

        if not evidence_sufficient:

            if not evidence_result.sufficient:
                insufficiency_reason = (
                    evidence_result.reason
                )

            else:
                insufficiency_reason = (
                    policy.reason
                )

        return AnswerGenerationRequest(
            request_id=request_id,
            query_id=(
                retrieved_evidence.query_id
            ),
            original_query=original_query,
            response_language=(
                policy.response_language
            ),
            retrieved_evidence=(
                retrieved_evidence
            ),
            evidence_sufficient=(
                evidence_sufficient
            ),
            insufficiency_reason=(
                insufficiency_reason
            ),
            safe_context=(
                context
                if (
                    policy
                    .use_safe_follow_up_context
                )
                else []
            ),
            response_instructions=list(
                response_instructions
            ),
        )