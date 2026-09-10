from __future__ import annotations

from src.knowledge.access_control import AccessControlService
from src.knowledge.governance import KnowledgeGovernanceService
from src.knowledge.repository import KnowledgeRepository
from src.knowledge.relationships import RelationshipService
from src.schemas.m6_knowledge import (
    AnswerGenerationRequest,
    Citation,
    EvidenceSufficiencyResult,
    RelatedRecordQuery,
)


class KnowledgeIntegrationService:
    """
    M6 integration layer between canonical knowledge,
    retrieval, and answer generation.
    """

    def __init__(
        self,
        repository: KnowledgeRepository,
        relationship_service: RelationshipService,
        access_control: AccessControlService,
        governance: KnowledgeGovernanceService,
    ) -> None:
        self.repository = repository
        self.relationship_service = relationship_service
        self.access_control = access_control
        self.governance = governance

    def retrieve_related(
        self,
        query: RelatedRecordQuery,
        *,
        user_role: str,
        client_id: str | None = None,
        matter_id: str | None = None,
    ):
        source = self.repository.get(query.record_id)

        if source is None:
            return []

        if not self.governance.can_be_used_for_answer(source):
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
            for record in self.repository.list_records()
        }

        records = {
            record_id: record
            for record_id, record in records.items()
            if self.access_control.can_access(
                record,
                user_role=user_role,
                client_id=client_id,
                matter_id=matter_id,
            )
            and self.governance.can_be_used_for_answer(record)
        }

        return self.relationship_service.query_related(
            query,
            records,
        )

    def evaluate_evidence(
        self,
        evidence: list[dict],
    ) -> EvidenceSufficiencyResult:
        if not evidence:
            return EvidenceSufficiencyResult(
                sufficient=False,
                score=0.0,
                reason="No evidence was retrieved.",
                missing_information=["Relevant legal evidence"],
                requires_follow_up=True,
            )

        valid_evidence = [
            item
            for item in evidence
            if item.get("passage")
            or item.get("text")
            or item.get("content")
        ]

        if not valid_evidence:
            return EvidenceSufficiencyResult(
                sufficient=False,
                score=0.0,
                reason="Retrieved evidence contains no usable passages.",
                missing_information=["Usable source passages"],
                requires_follow_up=True,
            )

        score = min(1.0, len(valid_evidence) / 3)

        return EvidenceSufficiencyResult(
            sufficient=True,
            score=score,
            reason="Usable legal evidence is available.",
            missing_information=[],
            requires_follow_up=False,
        )

    def build_answer_request(
        self,
        *,
        query: str,
        response_language: str,
        evidence: list[dict],
        citations: list[Citation],
        follow_up_context: str | None = None,
    ) -> AnswerGenerationRequest:
        sufficiency = self.evaluate_evidence(evidence)

        return AnswerGenerationRequest(
            query=query,
            response_language=response_language,
            evidence=evidence,
            citations=citations,
            follow_up_context=follow_up_context,
            evidence_sufficiency=sufficiency,
        )