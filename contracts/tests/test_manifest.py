from uuid import uuid4

from m1.manifest import build_generation_manifest
from m1.schemas import (
    AITransformation,
    ApprovedClause,
    AssembledDraft,
    AssembledSection,
    DraftStatus,
    GuidedDocumentRequest,
)


def make_request():
    return GuidedDocumentRequest(
        request_id=str(uuid4()),
        document_type="nda",
        jurisdiction="EG",
        fields={
            "party_a": "Test A",
            "party_b": "Test B",
        },
    )


def make_draft(request):
    return AssembledDraft(
        draft_id="draft-001",
        request_id=request.request_id,
        template_id="TMPL-NDA-EG-001",
        template_version="1.0.0",
        document_type="nda",
        jurisdiction="EG",
        sections=[
            AssembledSection(
                section_id="sec-1",
                title="Test Section",
                text="Test content",
                order=1,
                source_type="template",
                source_id="TMPL-NDA-EG-001",
            ),
            AssembledSection(
                section_id="clause-1",
                title="confidentiality",
                text="Approved test clause",
                order=2,
                source_type="approved_clause",
                source_id="CLZ-CONF-EG-001",
                clause_id="CLZ-CONF-EG-001",
                clause_version="1.0.0",
            ),
        ],
        plain_text="Test content\nApproved test clause",
        status=DraftStatus.DRAFT,
    )


def make_clause():
    return ApprovedClause(
        clause_id="CLZ-CONF-EG-001",
        type="confidentiality",
        jurisdiction="EG",
        document_types=["employment_contract", "nda", "service_agreement"],
        version="1.0.0",
        approval_status="approved",
        source="Test approved source",
        text_en="Approved test clause",
        sequence=1,
        insertion_key="test_confidentiality",
    )


def test_build_generation_manifest():
    request = make_request()
    draft = make_draft(request)
    clause = make_clause()

    manifest = build_generation_manifest(
        request,
        draft,
        [clause],
    )

    assert manifest.generation_id
    assert manifest.draft_id == draft.draft_id
    assert manifest.request_id == request.request_id

    assert manifest.template_id == draft.template_id
    assert manifest.template_version == draft.template_version

    assert manifest.clause_refs == [
        {
            "clause_id": "CLZ-CONF-EG-001",
            "version": "1.0.0",
        }
    ]

    assert manifest.user_fields == request.fields

    assert manifest.ai_transformation.used is False
    assert manifest.ai_transformation.model_tag is None

    assert manifest.edits == []

    assert "created_at" in manifest.timestamps


def test_manifest_with_ai_transformation():
    request = make_request()
    draft = make_draft(request)
    clause = make_clause()

    transformation = AITransformation(
        used=True,
        model_tag="test-model",
        prompt_version="prompt-v1",
        description="Test transformation",
        allowed_source_ids=[
            "CLZ-CONF-EG-001"
        ],
    )

    manifest = build_generation_manifest(
        request,
        draft,
        [clause],
        ai_transformation=transformation,
    )

    assert manifest.ai_transformation.used is True
    assert manifest.ai_transformation.model_tag == "test-model"
    assert manifest.ai_transformation.prompt_version == "prompt-v1"
    assert manifest.ai_transformation.description == "Test transformation"

    assert manifest.ai_transformation.allowed_source_ids == [
        "CLZ-CONF-EG-001"
    ]


def test_manifest_with_edits():
    request = make_request()
    draft = make_draft(request)
    clause = make_clause()

    edits = [
        {
            "section_id": "sec-1",
            "editor_id": "lawyer-001",
            "change": "Approved edit",
        }
    ]

    manifest = build_generation_manifest(
        request,
        draft,
        [clause],
        edits=edits,
    )

    assert manifest.edits == edits