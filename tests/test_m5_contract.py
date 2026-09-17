"""
Tests for M5 Contract Schema — m5_contract.py
"""

import pytest
from datetime import datetime, timezone, timedelta

from src.schemas.m5_contract import (
    ApprovalEvent,
    ApprovalStatus,
    ApprovedClause,
    ClauseCompatibilityRule,
    ClauseMetadata,
    ClauseType,
    CompletenessReport,
    CompatibilityRelationship,
    CompatibilityResult,
    ConditionalClause,
    DocumentType,
    Jurisdiction,
    M5ToM1Handoff,
    M5ToM4Handoff,
    SpecialConditionResult,
    TemplateClauseRequirement,
    TraceRecord,
    ValidationReport,
    VersionEntry,
)


def _make_clause(**overrides) -> ApprovedClause:
    """Helper to create a test clause with defaults."""
    defaults = {
        "clause_id": "CLZ-TEST-EG-001",
        "type": ClauseType.TERMINATION,
        "jurisdiction": Jurisdiction.EG,
        "document_types": [DocumentType.EMPLOYMENT_CONTRACT],
        "version": "1.0.0",
        "approval_status": ApprovalStatus.APPROVED,
        "effective_date": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "owner": "legal_team",
        "source": "Test Source",
        "text_ar": "نص البند بالعربية",
        "text_en": "Clause text in English",
    }
    defaults.update(overrides)
    return ApprovedClause(**defaults)


class TestApprovedClause:
    """Tests for the ApprovedClause model."""

    def test_create_valid_clause(self):
        clause = _make_clause()
        assert clause.clause_id == "CLZ-TEST-EG-001"
        assert clause.type == ClauseType.TERMINATION
        assert clause.jurisdiction == Jurisdiction.EG

    def test_clause_id_must_start_with_clz(self):
        with pytest.raises(ValueError, match="CLZ-"):
            _make_clause(clause_id="INVALID-001")

    def test_version_must_be_semver(self):
        with pytest.raises(ValueError):
            _make_clause(version="1.0")

    def test_is_active_approved_clause(self):
        clause = _make_clause(
            approval_status=ApprovalStatus.APPROVED,
            effective_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        assert clause.is_active() is True

    def test_is_active_draft_clause(self):
        clause = _make_clause(
            approval_status=ApprovalStatus.DRAFT,
        )
        assert clause.is_active() is False

    def test_is_active_expired_clause(self):
        clause = _make_clause(
            approval_status=ApprovalStatus.APPROVED,
            effective_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            expiry_date=datetime(2021, 1, 1, tzinfo=timezone.utc),
        )
        assert clause.is_active() is False

    def test_is_active_future_effective(self):
        future = datetime.now(timezone.utc) + timedelta(days=365)
        clause = _make_clause(
            effective_date=future,
        )
        assert clause.is_active() is False

    def test_is_usable_active_clause(self):
        clause = _make_clause(
            effective_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        assert clause.is_usable() is True

    def test_is_usable_lawyer_edited_needs_approval(self):
        clause = _make_clause(
            effective_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            is_lawyer_edited=True,
            requires_separate_approval=True,
        )
        assert clause.is_usable() is False

    def test_document_types_required(self):
        with pytest.raises(ValueError):
            _make_clause(document_types=[])

    def test_text_ar_required(self):
        with pytest.raises(ValueError):
            _make_clause(text_ar="")

    def test_text_en_required(self):
        with pytest.raises(ValueError):
            _make_clause(text_en="")


class TestClauseCompatibilityRule:
    """Tests for compatibility rule model."""

    def test_create_rule(self):
        rule = ClauseCompatibilityRule(
            rule_id="RULE-001",
            clause_id_a="CLZ-A",
            clause_id_b="CLZ-B",
            relationship=CompatibilityRelationship.INCOMPATIBLE,
            reason="Test reason",
        )
        assert rule.rule_id == "RULE-001"
        assert rule.relationship == CompatibilityRelationship.INCOMPATIBLE


class TestTemplateClauseRequirement:
    """Tests for template clause requirement model."""

    def test_create_template(self):
        template = TemplateClauseRequirement(
            template_id="TMPL-001",
            document_type=DocumentType.EMPLOYMENT_CONTRACT,
            jurisdiction=Jurisdiction.EG,
            required_clauses=["CLZ-001"],
            optional_clauses=["CLZ-002"],
            section_placeholders={"section_termination": "{{TERMINATION_CLAUSE}}"},
            template_structure="Sample Structure {{TERMINATION_CLAUSE}}",
        )
        assert template.template_id == "TMPL-001"
        assert len(template.required_clauses) == 1
        assert template.section_placeholders["section_termination"] == "{{TERMINATION_CLAUSE}}"
        assert "Sample Structure" in template.template_structure

    def test_clause_metadata_insertion_key(self):
        metadata = ClauseMetadata(
            risk_level="medium",
            insertion_key="section_termination",
        )
        assert metadata.insertion_key == "section_termination"


class TestSpecialConditionResult:
    """Tests for special condition result model."""

    def test_resolved_condition(self):
        clause = _make_clause()
        result = SpecialConditionResult(
            condition="termination",
            resolved=True,
            matched_clause=clause,
            requires_lawyer_input=False,
            reason="Found match",
        )
        assert result.resolved is True
        assert result.requires_lawyer_input is False

    def test_unresolved_condition(self):
        result = SpecialConditionResult(
            condition="custom_clause",
            resolved=False,
            requires_lawyer_input=True,
            reason="No match found",
        )
        assert result.resolved is False
        assert result.requires_lawyer_input is True


class TestHandoffs:
    """Tests for M5 handoff models."""

    def test_m5_to_m1_handoff(self):
        clause = _make_clause()

        template_requirement = TemplateClauseRequirement(
            template_id="TMPL-EMP-EG",
            document_type=DocumentType.EMPLOYMENT_CONTRACT,
            jurisdiction=Jurisdiction.EG,
            required_clauses=[clause.clause_id],
            section_placeholders={
                "section_termination": "{{TERMINATION_CLAUSE}}",
            },
            template_structure="{{TERMINATION_CLAUSE}}",
        )

        handoff = M5ToM1Handoff(
            clauses=[clause],
            template_requirement=template_requirement,
            source_metadata={"jurisdiction": "EG"},
        )

        assert len(handoff.clauses) == 1
        assert (
            handoff.template_requirement.template_id
            == "TMPL-EMP-EG"
        )
        assert handoff.template_requirement.required_clauses == [
            clause.clause_id
        ]

    def test_m5_to_m4_handoff(self):
        handoff = M5ToM4Handoff(
            provenance_rules=[{"rule": "test"}],
            status_rules=[{"status": "approved"}],
        )
        assert len(handoff.provenance_rules) == 1


class TestEnums:
    """Tests for M5 enums."""

    def test_clause_types(self):
        assert ClauseType.TERMINATION.value == "termination"
        assert ClauseType.CONFIDENTIALITY.value == "confidentiality"

    def test_jurisdictions(self):
        assert Jurisdiction.EG.value == "EG"
        assert Jurisdiction.KSA.value == "KSA"
        assert Jurisdiction.UAE.value == "UAE"

    def test_document_types(self):
        assert DocumentType.EMPLOYMENT_CONTRACT.value == "employment_contract"
        assert DocumentType.NDA.value == "nda"

    def test_approval_statuses(self):
        assert ApprovalStatus.DRAFT.value == "draft"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.LAWYER_EDITED.value == "lawyer_edited"
