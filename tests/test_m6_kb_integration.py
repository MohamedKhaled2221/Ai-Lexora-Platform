from src.knowledge.access_control import AccessControlService
from src.knowledge.governance import KnowledgeGovernanceService
from src.knowledge.integration import KnowledgeIntegrationService
from src.knowledge.relationships import RelationshipService
from src.knowledge.repository import InMemoryKnowledgeRepository
from src.schemas.m6_knowledge import Citation


def make_service():
    return KnowledgeIntegrationService(
        repository=InMemoryKnowledgeRepository(),
        relationship_service=RelationshipService(),
        access_control=AccessControlService(),
        governance=KnowledgeGovernanceService(),
    )


def test_empty_evidence_is_insufficient():
    service = make_service()

    result = service.evaluate_evidence([])

    assert result.sufficient is False
    assert result.requires_follow_up is True


def test_valid_evidence_is_sufficient():
    service = make_service()

    result = service.evaluate_evidence(
        [
            {"passage": "Article 10 provides..."},
        ]
    )

    assert result.sufficient is True
    assert result.score > 0


def test_build_answer_generation_request():
    service = make_service()

    request = service.build_answer_request(
        query="What does Article 10 provide?",
        response_language="en",
        evidence=[
            {
                "passage": "Article 10 provides...",
                "source_id": "law-001",
            }
        ],
        citations=[
            Citation(
                citation_id="cit-1",
                source_id="law-001",
                passage="Article 10 provides...",
            )
        ],
    )

    assert request.query == "What does Article 10 provide?"
    assert request.response_language == "en"
    assert request.evidence_sufficiency.sufficient is True
    assert len(request.citations) == 1