"""
Tests for M5 Clause Library, Compatibility Engine, Approval Workflow,
Versioning, Special Condition Resolver, and Service.
"""

import json
import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.schemas.m5_contract import (
    ApprovalStatus,
    ApprovedClause,
    ClauseCompatibilityRule,
    ClauseType,
    CompatibilityRelationship,
    DocumentType,
    Jurisdiction,
    TemplateClauseRequirement,
    ConditionalClause,
)
from src.clause_engine.clause_library import (
    ClauseLibrary,
    ClauseNotFoundError,
    DuplicateClauseError,
)
from src.clause_engine.compatibility_engine import CompatibilityEngine
from src.clause_engine.approval_workflow import (
    ApprovalWorkflow,
    InvalidTransitionError,
)
from src.clause_engine.versioning import ClauseVersionManager, VersioningError
from src.clause_engine.special_condition_resolver import SpecialConditionResolver
from src.clause_engine.traceability import ClauseTraceability
from src.clause_engine.required_clause_rules import RequiredClauseEngine
from src.clause_engine.service import M5ClauseService


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

def _make_clause(**overrides) -> ApprovedClause:
    """Create a test clause with defaults."""
    defaults = {
        "clause_id": "CLZ-TEST-EG-001",
        "type": ClauseType.TERMINATION,
        "jurisdiction": Jurisdiction.EG,
        "document_types": [DocumentType.EMPLOYMENT_CONTRACT],
        "version": "1.0.0",
        "approval_status": ApprovalStatus.APPROVED,
        "effective_date": datetime(2020, 1, 1, tzinfo=timezone.utc),
        "owner": "legal_team",
        "source": "Test Source",
        "text_ar": "نص البند بالعربية",
        "text_en": "Clause text in English",
    }
    defaults.update(overrides)
    return ApprovedClause(**defaults)


@pytest.fixture
def library() -> ClauseLibrary:
    """Empty clause library."""
    return ClauseLibrary()


@pytest.fixture
def populated_library() -> ClauseLibrary:
    """Library with sample clauses."""
    lib = ClauseLibrary()
    lib.add_clause(_make_clause(clause_id="CLZ-TERM-EG-001"))
    lib.add_clause(_make_clause(
        clause_id="CLZ-CONF-EG-001",
        type=ClauseType.CONFIDENTIALITY,
        document_types=[DocumentType.NDA, DocumentType.SERVICE_AGREEMENT],
    ))
    lib.add_clause(_make_clause(
        clause_id="CLZ-TERM-KSA-001",
        jurisdiction=Jurisdiction.KSA,
    ))
    lib.add_clause(_make_clause(
        clause_id="CLZ-LIAB-INT-001",
        type=ClauseType.LIABILITY_LIMITATION,
        jurisdiction=Jurisdiction.INTERNATIONAL,
        document_types=[DocumentType.SERVICE_AGREEMENT],
    ))
    return lib


@pytest.fixture
def seed_library_path(tmp_path) -> Path:
    """Create a temporary seed JSON library file."""
    data = {
        "version": "1.0.0",
        "clauses": [
            _make_clause(clause_id="CLZ-SEED-EG-001").model_dump(mode="json"),
            _make_clause(
                clause_id="CLZ-SEED-EG-002",
                type=ClauseType.CONFIDENTIALITY,
            ).model_dump(mode="json"),
        ],
    }
    path = tmp_path / "test_library.json"
    path.write_text(json.dumps(data, default=str), encoding="utf-8")
    return path


# ──────────────────────────────────────────────
# Clause Library Tests
# ──────────────────────────────────────────────

class TestClauseLibrary:

    def test_add_and_get_clause(self, library):
        clause = _make_clause()
        library.add_clause(clause)
        result = library.get_clause("CLZ-TEST-EG-001")
        assert result.clause_id == "CLZ-TEST-EG-001"

    def test_add_duplicate_raises(self, library):
        clause = _make_clause()
        library.add_clause(clause)
        with pytest.raises(DuplicateClauseError):
            library.add_clause(clause)

    def test_get_nonexistent_raises(self, library):
        with pytest.raises(ClauseNotFoundError):
            library.get_clause("CLZ-NOPE-001")

    def test_get_clause_or_none(self, library):
        assert library.get_clause_or_none("CLZ-NOPE-001") is None

    def test_clause_count(self, populated_library):
        assert populated_library.clause_count == 4

    def test_search_by_type(self, populated_library):
        results = populated_library.search_clauses(
            clause_type=ClauseType.TERMINATION,
        )
        assert len(results) == 2

    def test_search_by_jurisdiction(self, populated_library):
        results = populated_library.search_clauses(
            jurisdiction=Jurisdiction.KSA,
        )
        assert len(results) == 1

    def test_search_by_document_type(self, populated_library):
        results = populated_library.search_clauses(
            document_type=DocumentType.NDA,
        )
        assert len(results) == 1

    def test_search_active_only(self, populated_library):
        results = populated_library.search_clauses(active_only=True)
        assert len(results) == 4

    def test_get_active_clauses(self, populated_library):
        active = populated_library.get_active_clauses()
        assert len(active) == 4

    def test_update_clause(self, library):
        library.add_clause(_make_clause())
        updated = library.update_clause(
            "CLZ-TEST-EG-001",
            text_en="Updated text",
        )
        assert updated.text_en == "Updated text"

    def test_remove_clause(self, library):
        library.add_clause(_make_clause())
        removed = library.remove_clause("CLZ-TEST-EG-001")
        assert removed.clause_id == "CLZ-TEST-EG-001"
        assert library.clause_count == 0

    def test_load_from_file(self, seed_library_path):
        lib = ClauseLibrary(library_path=seed_library_path)
        assert lib.clause_count == 2

    def test_save_and_reload(self, library, tmp_path):
        library.add_clause(_make_clause())
        save_path = tmp_path / "saved_library.json"
        library.save_library(save_path)
        reloaded = ClauseLibrary(library_path=save_path)
        assert reloaded.clause_count == 1

    def test_validate_clause_valid(self, library):
        clause = _make_clause()
        errors = library.validate_clause(clause)
        assert errors == []

    def test_validate_clause_invalid_id(self, library):
        clause = _make_clause()
        # Bypass Pydantic validation to test library-level validation
        clause_data = clause.model_dump()
        clause_data["clause_id"] = "INVALID-001"
        # This will fail at Pydantic level
        with pytest.raises(ValueError):
            ApprovedClause(**clause_data)

    def test_get_clauses_by_ids(self, populated_library):
        result = populated_library.get_clauses_by_ids(
            ["CLZ-TERM-EG-001", "CLZ-CONF-EG-001", "CLZ-NOPE"]
        )
        assert len(result) == 2


# ──────────────────────────────────────────────
# Compatibility Engine Tests
# ──────────────────────────────────────────────

class TestCompatibilityEngine:

    def test_compatible_clauses(self, populated_library):
        engine = CompatibilityEngine()
        clause_a = populated_library.get_clause("CLZ-TERM-EG-001")
        clause_b = populated_library.get_clause("CLZ-CONF-EG-001")
        result = engine.check_compatibility(clause_a, clause_b)
        assert result.compatible is True

    def test_jurisdiction_mismatch(self, populated_library):
        engine = CompatibilityEngine()
        clause_eg = populated_library.get_clause("CLZ-TERM-EG-001")
        clause_ksa = populated_library.get_clause("CLZ-TERM-KSA-001")
        result = engine.check_compatibility(clause_eg, clause_ksa)
        assert result.compatible is False

    def test_international_always_compatible(self, populated_library):
        engine = CompatibilityEngine()
        clause_eg = populated_library.get_clause("CLZ-TERM-EG-001")
        clause_int = populated_library.get_clause("CLZ-LIAB-INT-001")
        result = engine.check_compatibility(clause_eg, clause_int)
        assert result.compatible is True

    def test_custom_incompatibility_rule(self, populated_library):
        rule = ClauseCompatibilityRule(
            rule_id="RULE-001",
            clause_id_a="CLZ-TERM-EG-001",
            clause_id_b="CLZ-CONF-EG-001",
            relationship=CompatibilityRelationship.INCOMPATIBLE,
            reason="Test incompatibility",
        )
        engine = CompatibilityEngine(rules=[rule])
        clause_a = populated_library.get_clause("CLZ-TERM-EG-001")
        clause_b = populated_library.get_clause("CLZ-CONF-EG-001")
        result = engine.check_compatibility(clause_a, clause_b)
        assert result.compatible is False

    def test_check_document_compatibility(self, populated_library):
        engine = CompatibilityEngine()
        clause = populated_library.get_clause("CLZ-TERM-EG-001")
        assert engine.check_document_compatibility(
            clause, DocumentType.EMPLOYMENT_CONTRACT
        ) is True
        assert engine.check_document_compatibility(
            clause, DocumentType.NDA
        ) is False

    def test_check_jurisdiction_compatibility(self, populated_library):
        engine = CompatibilityEngine()
        clause = populated_library.get_clause("CLZ-TERM-EG-001")
        assert engine.check_jurisdiction_compatibility(
            clause, Jurisdiction.EG
        ) is True
        assert engine.check_jurisdiction_compatibility(
            clause, Jurisdiction.KSA
        ) is False

    def test_find_incompatible_pairs(self, populated_library):
        engine = CompatibilityEngine()
        clauses = populated_library.get_all_clauses()
        pairs = engine.find_incompatible_pairs(clauses)
        # EG vs KSA should be incompatible
        assert len(pairs) >= 1

    def test_validate_clause_set(self, populated_library):
        engine = CompatibilityEngine()
        clauses = [
            populated_library.get_clause("CLZ-TERM-EG-001"),
            populated_library.get_clause("CLZ-CONF-EG-001"),
        ]
        errors = engine.validate_clause_set_for_document(
            clauses, DocumentType.EMPLOYMENT_CONTRACT, Jurisdiction.EG
        )
        # CONF clause doesn't have EMPLOYMENT_CONTRACT in its types
        assert any("not compatible with document type" in e for e in errors)


# ──────────────────────────────────────────────
# Approval Workflow Tests
# ──────────────────────────────────────────────

class TestApprovalWorkflow:

    def test_submit_for_review(self, library):
        clause = _make_clause(approval_status=ApprovalStatus.DRAFT)
        library.add_clause(clause)
        workflow = ApprovalWorkflow(library)
        updated = workflow.submit_for_review("CLZ-TEST-EG-001")
        assert updated.approval_status == ApprovalStatus.PENDING_REVIEW

    def test_approve(self, library):
        clause = _make_clause(approval_status=ApprovalStatus.PENDING_REVIEW)
        library.add_clause(clause)
        workflow = ApprovalWorkflow(library)
        updated = workflow.approve("CLZ-TEST-EG-001", "admin")
        assert updated.approval_status == ApprovalStatus.APPROVED

    def test_reject(self, library):
        clause = _make_clause(approval_status=ApprovalStatus.PENDING_REVIEW)
        library.add_clause(clause)
        workflow = ApprovalWorkflow(library)
        updated = workflow.reject("CLZ-TEST-EG-001", "admin", "Not suitable")
        assert updated.approval_status == ApprovalStatus.REJECTED

    def test_reject_requires_reason(self, library):
        clause = _make_clause(approval_status=ApprovalStatus.PENDING_REVIEW)
        library.add_clause(clause)
        workflow = ApprovalWorkflow(library)
        with pytest.raises(Exception):
            workflow.reject("CLZ-TEST-EG-001", "admin", "")

    def test_invalid_transition(self, library):
        clause = _make_clause(approval_status=ApprovalStatus.DRAFT)
        library.add_clause(clause)
        workflow = ApprovalWorkflow(library)
        with pytest.raises(InvalidTransitionError):
            workflow.approve("CLZ-TEST-EG-001", "admin")

    def test_lawyer_edit_flow(self, library):
        clause = _make_clause(
            approval_status=ApprovalStatus.APPROVED,
            effective_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        library.add_clause(clause)
        workflow = ApprovalWorkflow(library)

        # Lawyer edits
        edited = workflow.mark_as_lawyer_edited(
            "CLZ-TEST-EG-001", "lawyer_x"
        )
        assert edited.approval_status == ApprovalStatus.LAWYER_EDITED
        assert edited.is_lawyer_edited is True
        assert edited.requires_separate_approval is True

        # Request reapproval
        pending = workflow.request_reapproval("CLZ-TEST-EG-001")
        assert pending.approval_status == ApprovalStatus.PENDING_REVIEW

        # Approve again
        approved = workflow.approve("CLZ-TEST-EG-001", "admin")
        assert approved.approval_status == ApprovalStatus.APPROVED

    def test_approval_history(self, library):
        clause = _make_clause(approval_status=ApprovalStatus.DRAFT)
        library.add_clause(clause)
        workflow = ApprovalWorkflow(library)
        workflow.submit_for_review("CLZ-TEST-EG-001")
        workflow.approve("CLZ-TEST-EG-001", "admin")
        history = workflow.get_approval_history("CLZ-TEST-EG-001")
        assert len(history) == 2

    def test_get_pending_reviews(self, library):
        c1 = _make_clause(
            clause_id="CLZ-PEND-001",
            approval_status=ApprovalStatus.PENDING_REVIEW,
        )
        c2 = _make_clause(
            clause_id="CLZ-APPR-001",
            approval_status=ApprovalStatus.APPROVED,
        )
        library.add_clause(c1)
        library.add_clause(c2)
        workflow = ApprovalWorkflow(library)
        pending = workflow.get_pending_reviews()
        assert len(pending) == 1

    def test_return_to_draft(self, library):
        clause = _make_clause(approval_status=ApprovalStatus.REJECTED)
        library.add_clause(clause)
        workflow = ApprovalWorkflow(library)
        updated = workflow.return_to_draft("CLZ-TEST-EG-001")
        assert updated.approval_status == ApprovalStatus.DRAFT

    def test_superseded_is_terminal(self, library):
        clause = _make_clause(
            approval_status=ApprovalStatus.SUPERSEDED,
            superseded_by="CLZ-OTHER-001",
        )
        library.add_clause(clause)
        workflow = ApprovalWorkflow(library)
        with pytest.raises(InvalidTransitionError):
            workflow.submit_for_review("CLZ-TEST-EG-001")


# ──────────────────────────────────────────────
# Versioning Tests
# ──────────────────────────────────────────────

class TestVersioning:

    def test_bump_patch(self, library):
        library.add_clause(_make_clause(version="1.0.0"))
        vm = ClauseVersionManager(library)
        updated = vm.create_version(
            "CLZ-TEST-EG-001", "Fix typo", bump="patch"
        )
        assert updated.version == "1.0.1"

    def test_bump_minor(self, library):
        library.add_clause(_make_clause(version="1.0.0"))
        vm = ClauseVersionManager(library)
        updated = vm.create_version(
            "CLZ-TEST-EG-001", "Improve wording", bump="minor"
        )
        assert updated.version == "1.1.0"

    def test_bump_major(self, library):
        library.add_clause(_make_clause(version="1.2.3"))
        vm = ClauseVersionManager(library)
        updated = vm.create_version(
            "CLZ-TEST-EG-001", "Legal meaning change", bump="major"
        )
        assert updated.version == "2.0.0"

    def test_version_history(self, library):
        library.add_clause(_make_clause(version="1.0.0"))
        vm = ClauseVersionManager(library)
        vm.create_version("CLZ-TEST-EG-001", "v1", bump="patch")
        vm.create_version("CLZ-TEST-EG-001", "v2", bump="patch")
        history = vm.get_version_history("CLZ-TEST-EG-001")
        assert len(history) == 2

    def test_supersede(self, library):
        library.add_clause(_make_clause(
            clause_id="CLZ-OLD-001",
            version="1.0.0",
        ))
        library.add_clause(_make_clause(
            clause_id="CLZ-NEW-001",
            version="2.0.0",
        ))
        vm = ClauseVersionManager(library)
        old, new = vm.supersede("CLZ-OLD-001", "CLZ-NEW-001")
        assert old.approval_status == ApprovalStatus.SUPERSEDED
        assert old.superseded_by == "CLZ-NEW-001"
        assert new.supersedes == "CLZ-OLD-001"

    def test_get_latest_version_follows_chain(self, library):
        library.add_clause(_make_clause(
            clause_id="CLZ-OLD-001",
        ))
        library.add_clause(_make_clause(
            clause_id="CLZ-NEW-001",
        ))
        vm = ClauseVersionManager(library)
        vm.supersede("CLZ-OLD-001", "CLZ-NEW-001")
        latest = vm.get_latest_version("CLZ-OLD-001")
        assert latest.clause_id == "CLZ-NEW-001"

    def test_invalid_bump_type(self):
        assert ClauseVersionManager._bump_version("1.0.0", "patch") == "1.0.1"
        with pytest.raises(VersioningError):
            ClauseVersionManager._bump_version("1.0.0", "invalid")


# ──────────────────────────────────────────────
# Special Condition Resolver Tests
# ──────────────────────────────────────────────

class TestSpecialConditionResolver:

    def test_resolve_known_condition(self, populated_library):
        resolver = SpecialConditionResolver(populated_library)
        result = resolver.resolve(
            "termination",
            jurisdiction=Jurisdiction.EG,
        )
        assert result.resolved is True
        assert result.requires_lawyer_input is False
        assert result.matched_clause is not None

    def test_resolve_unknown_condition(self, populated_library):
        resolver = SpecialConditionResolver(populated_library)
        result = resolver.resolve("quantum_computing_clause")
        assert result.resolved is False
        assert result.requires_lawyer_input is True

    def test_resolve_arabic_condition(self, populated_library):
        resolver = SpecialConditionResolver(populated_library)
        result = resolver.resolve("إنهاء")
        assert result.resolved is True

    def test_resolve_empty_condition(self, populated_library):
        resolver = SpecialConditionResolver(populated_library)
        result = resolver.resolve("")
        assert result.resolved is False
        assert result.requires_lawyer_input is True

    def test_requires_lawyer_input_method(self, populated_library):
        resolver = SpecialConditionResolver(populated_library)
        assert resolver.requires_lawyer_input("termination", jurisdiction=Jurisdiction.EG) is False
        assert resolver.requires_lawyer_input("custom_unknown") is True


# ──────────────────────────────────────────────
# Traceability Tests
# ──────────────────────────────────────────────

class TestTraceability:

    def test_record_usage(self, populated_library):
        tracer = ClauseTraceability(populated_library)
        trace = tracer.record_usage(
            "CLZ-TERM-EG-001",
            document_id="DOC-001",
            section="Section 5",
        )
        assert trace.clause_id == "CLZ-TERM-EG-001"
        assert trace.document_id == "DOC-001"

    def test_get_clause_usage(self, populated_library):
        tracer = ClauseTraceability(populated_library)
        tracer.record_usage("CLZ-TERM-EG-001", "DOC-001")
        tracer.record_usage("CLZ-TERM-EG-001", "DOC-002")
        tracer.record_usage("CLZ-CONF-EG-001", "DOC-001")
        usage = tracer.get_clause_usage("CLZ-TERM-EG-001")
        assert len(usage) == 2

    def test_get_document_clauses(self, populated_library):
        tracer = ClauseTraceability(populated_library)
        tracer.record_usage("CLZ-TERM-EG-001", "DOC-001")
        tracer.record_usage("CLZ-CONF-EG-001", "DOC-001")
        doc_clauses = tracer.get_document_clauses("DOC-001")
        assert len(doc_clauses) == 2

    def test_provenance_report(self, populated_library):
        tracer = ClauseTraceability(populated_library)
        tracer.record_usage("CLZ-TERM-EG-001", "DOC-001")
        report = tracer.generate_provenance_report("DOC-001")
        assert report.document_id == "DOC-001"
        assert len(report.traces) == 1

    def test_get_documents_using_clause(self, populated_library):
        tracer = ClauseTraceability(populated_library)
        tracer.record_usage("CLZ-TERM-EG-001", "DOC-001")
        tracer.record_usage("CLZ-TERM-EG-001", "DOC-002")
        docs = tracer.get_documents_using_clause("CLZ-TERM-EG-001")
        assert set(docs) == {"DOC-001", "DOC-002"}


# ──────────────────────────────────────────────
# Required Clause Rules Tests
# ──────────────────────────────────────────────

class TestRequiredClauseRules:

    def test_add_and_find_template(self, populated_library):
        engine = RequiredClauseEngine(populated_library)
        template = TemplateClauseRequirement(
            template_id="TMPL-EMP-EG",
            document_type=DocumentType.EMPLOYMENT_CONTRACT,
            jurisdiction=Jurisdiction.EG,
            required_clauses=["CLZ-TERM-EG-001"],
            optional_clauses=["CLZ-CONF-EG-001"],
        )
        engine.add_template(template)
        found = engine.find_template(
            DocumentType.EMPLOYMENT_CONTRACT, Jurisdiction.EG
        )
        assert found is not None
        assert found.template_id == "TMPL-EMP-EG"

    def test_get_required_clauses(self, populated_library):
        engine = RequiredClauseEngine(populated_library)
        template = TemplateClauseRequirement(
            template_id="TMPL-EMP-EG",
            document_type=DocumentType.EMPLOYMENT_CONTRACT,
            jurisdiction=Jurisdiction.EG,
            required_clauses=["CLZ-TERM-EG-001"],
        )
        engine.add_template(template)
        required = engine.get_required_clauses(
            DocumentType.EMPLOYMENT_CONTRACT, Jurisdiction.EG
        )
        assert len(required) == 1
        assert required[0].clause_id == "CLZ-TERM-EG-001"

    def test_validate_completeness_missing(self, populated_library):
        engine = RequiredClauseEngine(populated_library)
        template = TemplateClauseRequirement(
            template_id="TMPL-EMP-EG",
            document_type=DocumentType.EMPLOYMENT_CONTRACT,
            jurisdiction=Jurisdiction.EG,
            required_clauses=["CLZ-TERM-EG-001", "CLZ-CONF-EG-001"],
        )
        engine.add_template(template)
        report = engine.validate_completeness(
            ["CLZ-TERM-EG-001"],
            DocumentType.EMPLOYMENT_CONTRACT,
            Jurisdiction.EG,
        )
        assert report.is_complete is False
        assert "CLZ-CONF-EG-001" in report.missing_required

    def test_validate_completeness_complete(self, populated_library):
        engine = RequiredClauseEngine(populated_library)
        template = TemplateClauseRequirement(
            template_id="TMPL-EMP-EG",
            document_type=DocumentType.EMPLOYMENT_CONTRACT,
            jurisdiction=Jurisdiction.EG,
            required_clauses=["CLZ-TERM-EG-001"],
        )
        engine.add_template(template)
        report = engine.validate_completeness(
            ["CLZ-TERM-EG-001"],
            DocumentType.EMPLOYMENT_CONTRACT,
            Jurisdiction.EG,
        )
        assert report.is_complete is True

    def test_validate_prohibited_clauses(self, populated_library):
        engine = RequiredClauseEngine(populated_library)
        template = TemplateClauseRequirement(
            template_id="TMPL-EMP-EG",
            document_type=DocumentType.EMPLOYMENT_CONTRACT,
            jurisdiction=Jurisdiction.EG,
            required_clauses=[],
            prohibited_clauses=["CLZ-TERM-KSA-001"],
        )
        engine.add_template(template)
        report = engine.validate_completeness(
            ["CLZ-TERM-KSA-001"],
            DocumentType.EMPLOYMENT_CONTRACT,
            Jurisdiction.EG,
        )
        assert report.is_complete is False
        assert "CLZ-TERM-KSA-001" in report.included_prohibited
    def test_validate_completeness_fails_without_template(
        self,
        populated_library,
    ):
        engine = RequiredClauseEngine(populated_library)

        report = engine.validate_completeness(
            ["CLZ-TERM-EG-001"],
            DocumentType.EMPLOYMENT_CONTRACT,
            Jurisdiction.EG,
        )

        assert report.is_complete is False
        assert report.template_id == "unknown"
        assert any(
            "No template found" in warning
            for warning in report.warnings
        )

# ──────────────────────────────────────────────
# M5 Service Integration Tests
# ──────────────────────────────────────────────

class TestM5Service:

    @pytest.fixture
    def service(self, populated_library) -> M5ClauseService:
        """Create M5 service with populated library."""
        populated_library.add_clause(
            _make_clause(
                clause_id="CLZ-DATA-EG-001",
                type=ClauseType.DATA_PROTECTION,
                document_types=[
                    DocumentType.EMPLOYMENT_CONTRACT
                ],
            )
        )
        populated_library.add_clause(
            _make_clause(
                clause_id="CLZ-CONF-EMP-EG-001",
                type=ClauseType.CONFIDENTIALITY,
                document_types=[
                    DocumentType.EMPLOYMENT_CONTRACT
                ],
            )
        )
        engine = RequiredClauseEngine(populated_library)
        template = TemplateClauseRequirement(
            template_id="TMPL-EMP-EG",
            document_type=DocumentType.EMPLOYMENT_CONTRACT,
            jurisdiction=Jurisdiction.EG,
            required_clauses=["CLZ-TERM-EG-001"],
            optional_clauses=["CLZ-CONF-EMP-EG-001"],
            prohibited_clauses=["CLZ-TERM-KSA-001"],
            conditional_clauses=[
                ConditionalClause(
                    clause_id="CLZ-DATA-EG-001",
                    condition="handles_personal_data",
                    description=(
                        "Required when the employment relationship "
                        "involves personal-data processing"
                    ),
                )
            ],
        )
        engine.add_template(template)

        return M5ClauseService(
            clause_library=populated_library,
            required_clause_engine=engine,
        )

    def test_get_clauses_for_document(self, service):
        handoff = service.get_clauses_for_document(
            DocumentType.EMPLOYMENT_CONTRACT,
            Jurisdiction.EG,
        )
        assert len(handoff.clauses) >= 1
        assert handoff.source_metadata["jurisdiction"] == "EG"
        assert (
            handoff.template_requirement.document_type
            == DocumentType.EMPLOYMENT_CONTRACT
        )

        assert (
            handoff.template_requirement.jurisdiction
            == Jurisdiction.EG
        )

        assert "CLZ-TERM-EG-001" in (
            handoff.template_requirement.required_clauses
        )

    def test_get_provenance_rules(self, service):
        handoff = service.get_provenance_rules()
        assert len(handoff.provenance_rules) > 0
        assert len(handoff.status_rules) > 0

    def test_validate_clause_set(self, service):
        report = service.validate_clause_set(
            ["CLZ-TERM-EG-001"],
            DocumentType.EMPLOYMENT_CONTRACT,
            Jurisdiction.EG,
        )
        assert report.valid is True

    def test_validate_clause_set_missing_required(self, service):
        report = service.validate_clause_set(
            ["CLZ-CONF-EMP-EG-001"],
            DocumentType.EMPLOYMENT_CONTRACT,
            Jurisdiction.EG,
        )
        assert report.valid is False

    def test_resolve_special_condition(self, service):
        result = service.resolve_special_condition(
            "termination",
            jurisdiction=Jurisdiction.EG,
        )
        assert result.resolved is True

    def test_resolve_unknown_condition(self, service):
        result = service.resolve_special_condition(
            "blockchain_smart_contract",
        )
        assert result.resolved is False
        assert result.requires_lawyer_input is True

    def test_validate_clause_set_fails_without_template(
        self,
        populated_library,
    ):
        service = M5ClauseService(
            clause_library=populated_library,
            required_clause_engine=RequiredClauseEngine(
                populated_library
            ),
        )

        report = service.validate_clause_set(
            ["CLZ-TERM-EG-001"],
            DocumentType.EMPLOYMENT_CONTRACT,
            Jurisdiction.EG,
        )

        assert report.valid is False
        assert any(
            "No template found" in error
            for error in report.errors
        )
    def test_conditional_clause_not_selected_when_condition_inactive(
        self,
        service,
    ):
        handoff = service.get_clauses_for_document(
            DocumentType.EMPLOYMENT_CONTRACT,
            Jurisdiction.EG,
        )

        clause_ids = {
            clause.clause_id
            for clause in handoff.clauses
        }

        assert "CLZ-DATA-EG-001" not in clause_ids
    def test_conditional_clause_selected_when_condition_active(
        self,
        service,
    ):
        handoff = service.get_clauses_for_document(
            DocumentType.EMPLOYMENT_CONTRACT,
            Jurisdiction.EG,
            active_conditions=["handles_personal_data"],
        )

        clause_ids = {
            clause.clause_id
            for clause in handoff.clauses
        }

        assert "CLZ-DATA-EG-001" in clause_ids

        assert handoff.source_metadata["active_conditions"] == [
            "handles_personal_data"
        ]

        assert handoff.source_metadata["conditional_count"] == 1
    def test_validate_clause_set_requires_active_conditional_clause(
        self,
        service,
    ):
        report = service.validate_clause_set(
            ["CLZ-TERM-EG-001"],
            DocumentType.EMPLOYMENT_CONTRACT,
            Jurisdiction.EG,
            active_conditions=["handles_personal_data"],
        )

        assert report.valid is False
        assert "CLZ-DATA-EG-001" in (
            report.completeness.missing_required
        )
    def test_validate_clause_set_accepts_active_conditional_clause(
        self,
        service,
    ):
        report = service.validate_clause_set(
            [
                "CLZ-TERM-EG-001",
                "CLZ-DATA-EG-001",
            ],
            DocumentType.EMPLOYMENT_CONTRACT,
            Jurisdiction.EG,
            active_conditions=["handles_personal_data"],
        )

        assert report.valid is True
        assert report.completeness.missing_required == []
    def test_handoff_rejects_clause_with_wrong_document_type(
        self,
        populated_library,
    ):
        bad_clause = _make_clause(
            clause_id="CLZ-BAD-DOC-EG-001",
            type=ClauseType.CONFIDENTIALITY,
            document_types=[DocumentType.NDA],
        )

        populated_library.add_clause(bad_clause)

        engine = RequiredClauseEngine(populated_library)

        engine.add_template(
            TemplateClauseRequirement(
                template_id="TMPL-EMP-EG-BAD-DOC",
                document_type=DocumentType.EMPLOYMENT_CONTRACT,
                jurisdiction=Jurisdiction.EG,
                optional_clauses=[
                    "CLZ-BAD-DOC-EG-001"
                ],
            )
        )

        service = M5ClauseService(
            clause_library=populated_library,
            required_clause_engine=engine,
        )

        with pytest.raises(
            ValueError,
            match="not compatible with document type",
        ):
            service.get_clauses_for_document(
                DocumentType.EMPLOYMENT_CONTRACT,
                Jurisdiction.EG,
            )
    def test_handoff_rejects_clause_with_wrong_jurisdiction(
        self,
        populated_library,
    ):
        bad_clause = _make_clause(
            clause_id="CLZ-BAD-KSA-001",
            jurisdiction=Jurisdiction.KSA,
            document_types=[
                DocumentType.EMPLOYMENT_CONTRACT
            ],
        )

        populated_library.add_clause(bad_clause)

        engine = RequiredClauseEngine(populated_library)

        engine.add_template(
            TemplateClauseRequirement(
                template_id="TMPL-EMP-EG-BAD-JUR",
                document_type=(
                    DocumentType.EMPLOYMENT_CONTRACT
                ),
                jurisdiction=Jurisdiction.EG,
                optional_clauses=[
                    "CLZ-BAD-KSA-001"
                ],
            )
        )

        service = M5ClauseService(
            clause_library=populated_library,
            required_clause_engine=engine,
        )

        with pytest.raises(
            ValueError,
            match="not compatible with jurisdiction",
        ):
            service.get_clauses_for_document(
                DocumentType.EMPLOYMENT_CONTRACT,
                Jurisdiction.EG,
            )
    def test_handoff_accepts_applicable_clauses(
        self,
        service,
    ):
        handoff = service.get_clauses_for_document(
            DocumentType.EMPLOYMENT_CONTRACT,
            Jurisdiction.EG,
        )

        for clause in handoff.clauses:
            assert (
                DocumentType.EMPLOYMENT_CONTRACT
                in clause.document_types
            )

            assert clause.jurisdiction in {
                Jurisdiction.EG,
                Jurisdiction.INTERNATIONAL,
            }
# ──────────────────────────────────────────────
# Seed Data Loading Test
# ──────────────────────────────────────────────

class TestSeedDataLoading:

    def test_load_seed_clause_library(self):
        """Test loading the actual seed data file."""
        seed_path = Path(__file__).parent.parent / "data" / "clause_library.json"
        if not seed_path.exists():
            pytest.skip("Seed data not found")
        lib = ClauseLibrary(library_path=seed_path)
        assert lib.clause_count > 0

    def test_load_seed_template_requirements(self):
        """Test loading the actual template requirements file."""
        seed_path = Path(__file__).parent.parent / "data" / "clause_library.json"
        req_path = Path(__file__).parent.parent / "data" / "template_requirements.json"
        if not seed_path.exists() or not req_path.exists():
            pytest.skip("Seed data not found")

        lib = ClauseLibrary(library_path=seed_path)
        engine = RequiredClauseEngine(lib, requirements_path=req_path)
        assert engine.template_count > 0

    def test_nda_eg_discrepancy_resolution_and_handoff(self):
        """Test that NDA-EG optional clauses are compatible with NDA document type and handoff includes insertion_map."""
        seed_path = Path(__file__).parent.parent / "data" / "clause_library.json"
        req_path = Path(__file__).parent.parent / "data" / "template_requirements.json"
        if not seed_path.exists() or not req_path.exists():
            pytest.skip("Seed data not found")

        service = M5ClauseService(library_path=seed_path, requirements_path=req_path)
        handoff = service.get_clauses_for_document(DocumentType.NDA, Jurisdiction.EG)

        clause_ids = [c.clause_id for c in handoff.clauses]
        assert "CLZ-CONF-EG-001" in clause_ids
        assert "CLZ-GLAW-EG-001" in clause_ids
        assert "CLZ-DISP-EG-001" in clause_ids
        assert "CLZ-PNLT-EG-001" in clause_ids

        # Validate completeness check
        report = service.validate_clause_set(clause_ids, DocumentType.NDA, Jurisdiction.EG)
        assert report.valid is True

        # Validate insertion map and template structure metadata
        source_meta = handoff.source_metadata
        assert "insertion_map" in source_meta
        assert source_meta["insertion_map"].get("CLZ-CONF-EG-001") == "section_confidentiality"
        assert "template_structure" in source_meta
        assert "{{CONFIDENTIALITY_CLAUSE}}" in source_meta["template_structure"]
        assert "section_placeholders" in source_meta
        assert source_meta["section_placeholders"].get("section_confidentiality") == "{{CONFIDENTIALITY_CLAUSE}}"
        requirement = handoff.template_requirement

        assert (
            requirement.section_placeholders[
                "section_confidentiality"
            ]
            == "{{CONFIDENTIALITY_CLAUSE}}"
        )

        assert "{{CONFIDENTIALITY_CLAUSE}}" in (
            requirement.template_structure
        )
