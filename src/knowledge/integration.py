from __future__ import annotations

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
                retrieved_evidence
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