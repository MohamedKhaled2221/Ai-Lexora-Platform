"""Tests for the DocumentChunk output contract.

This schema is what M2/M3 and M5 integrate against, so these tests are as much
a specification as a regression guard. If a test here needs changing, that is a
breaking change for two other team members.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.document_chunk_schema import (
    BoundingBox,
    ChunkMetadata,
    DocumentChunk,
    DocumentIngestResult,
    DocumentType,
    Language,
    OCRConfidence,
    RTLFlag,
    SourceEngine,
    StructuralRef,
    make_chunk_id,
    make_document_id,
)

SPEC_FIELDS = {
    "document_id",
    "chunk_id",
    "text",
    "page",
    "section",
    "language",
    "document_type",
    "metadata",
}
"""The eight fields frozen by the team spec."""

ACCESS_CONTROL_FIELDS = {
    "client_id",
    "matter_id",
    "confidentiality_level",
}
"""Added 2026-09-05 for M3 tenancy filtering.

Additive and optional: every one defaults to ``None``, so a producer that
predates them keeps working unchanged. They are named separately from
``SPEC_FIELDS`` so this test still fails on an *unplanned* field -- the point
of the lock is to catch fields nobody decided on, not to forbid growth.
"""

SPEC_EXAMPLE = {
    "document_id": "doc_001",
    "chunk_id": "chunk_017",
    "text": "Termination may occur...",
    "page": 12,
    "section": "Termination",
    "language": "en",
    "document_type": "contract",
    "metadata": {"jurisdiction": "Egypt"},
}


class TestSpecCompliance:
    def test_spec_example_validates(self):
        chunk = DocumentChunk(**SPEC_EXAMPLE)
        assert chunk.document_id == "doc_001"
        assert chunk.chunk_id == "chunk_017"
        assert chunk.page == 12
        assert chunk.section == "Termination"

    def test_spec_example_round_trips_exactly(self):
        """The serialized shape must match the spec's JSON, field for field.

        ``clause`` is the first addition to the spec's original eight -- see
        ``TestClauseSurfacing`` -- and it is ``None`` on a chunk that carries
        no clause, exactly as M2's copy of the contract defaults it.

        The access-control triple is the second, and defaults the same way:
        M1 is not an authority on who may read a document, so it emits
        ``None`` and the M3 ingest boundary stamps the real values from the
        authenticated caller.
        """
        dumped = DocumentChunk(**SPEC_EXAMPLE).model_dump(mode="json")
        assert dumped == {
            **SPEC_EXAMPLE,
            "clause": None,
            **{name: None for name in ACCESS_CONTROL_FIELDS},
        }

    def test_exact_field_set(self):
        """Extra top-level fields are forbidden: consumers destructure this."""
        assert set(DocumentChunk.model_fields) == (
            SPEC_FIELDS | {"clause"} | ACCESS_CONTROL_FIELDS
        )

    def test_access_control_fields_default_to_none(self):
        """
        Absent, not permissive.

        A null ``client_id`` matches no allowed-client set downstream, so an
        unstamped chunk is unreadable rather than public -- and M3's indexing
        layer refuses it outright rather than storing it that way.
        """
        chunk = DocumentChunk(**SPEC_EXAMPLE)

        for name in ACCESS_CONTROL_FIELDS:
            assert getattr(chunk, name) is None

    def test_confidentiality_level_is_a_closed_vocabulary(self):
        """
        A typo must fail here, not silently match nothing at query time.
        """
        with pytest.raises(ValidationError):
            DocumentChunk(
                **{**SPEC_EXAMPLE, "confidentiality_level": "secret"}
            )

        for level in ("public", "internal", "privileged"):
            assert DocumentChunk(
                **{**SPEC_EXAMPLE, "confidentiality_level": level}
            ).confidentiality_level == level

    def test_extra_top_level_field_rejected(self):
        with pytest.raises(ValidationError):
            DocumentChunk(**SPEC_EXAMPLE, unexpected="value")

    def test_json_serializable(self):
        chunk = DocumentChunk(**SPEC_EXAMPLE)
        assert json.loads(chunk.model_dump_json())["chunk_id"] == "chunk_017"


class TestValidation:
    def test_empty_text_rejected(self):
        """An empty chunk is never useful and pollutes a vector index."""
        with pytest.raises(ValidationError, match="empty"):
            DocumentChunk(**{**SPEC_EXAMPLE, "text": ""})

    def test_whitespace_only_text_rejected(self):
        with pytest.raises(ValidationError):
            DocumentChunk(**{**SPEC_EXAMPLE, "text": "   \n  "})

    def test_page_must_be_positive(self):
        with pytest.raises(ValidationError):
            DocumentChunk(**{**SPEC_EXAMPLE, "page": 0})

    def test_page_is_required(self):
        """``page`` is required and ``ge=1`` -- M2's schema has no default for
        it, so a page-less chunk is unconsumable downstream. Unpaginated
        formats report page 1; they do not report ``None``."""
        payload = {k: v for k, v in SPEC_EXAMPLE.items() if k != "page"}
        with pytest.raises(ValidationError):
            DocumentChunk(**payload)

    def test_page_none_rejected(self):
        with pytest.raises(ValidationError):
            DocumentChunk(**{**SPEC_EXAMPLE, "page": None})

    def test_ids_reject_whitespace(self):
        with pytest.raises(ValidationError):
            DocumentChunk(**{**SPEC_EXAMPLE, "chunk_id": "chunk 017"})

    def test_invalid_language_rejected(self):
        with pytest.raises(ValidationError):
            DocumentChunk(**{**SPEC_EXAMPLE, "language": "fr"})

    def test_invalid_document_type_rejected(self):
        with pytest.raises(ValidationError):
            DocumentChunk(**{**SPEC_EXAMPLE, "document_type": "invoice"})

    @pytest.mark.parametrize("lang", ["ar", "en", "ar-en", "unknown"])
    def test_all_languages_accepted(self, lang):
        assert DocumentChunk(**{**SPEC_EXAMPLE, "language": lang}).language == lang

    @pytest.mark.parametrize("dtype", [d.value for d in DocumentType])
    def test_all_document_types_accepted(self, dtype):
        assert DocumentChunk(**{**SPEC_EXAMPLE, "document_type": dtype}).document_type == dtype


class TestMetadata:
    def test_metadata_is_open(self):
        """Adding a metadata key must never break a consumer."""
        chunk = DocumentChunk(
            **{**SPEC_EXAMPLE, "metadata": {"jurisdiction": "Egypt", "future_key": [1, 2]}}
        )
        assert chunk.metadata["future_key"] == [1, 2]

    def test_metadata_defaults_to_empty_dict(self):
        payload = {k: v for k, v in SPEC_EXAMPLE.items() if k != "metadata"}
        assert DocumentChunk(**payload).metadata == {}

    def test_chunk_metadata_model_serializes_to_plain_json(self):
        meta = ChunkMetadata(
            jurisdiction="Egypt",
            structure=StructuralRef(article="المادة 12", clause_id="art_12"),
            bboxes=[BoundingBox(x0=1, y0=2, x1=3, y1=4, page=1)],
            ocr_confidence=OCRConfidence(engine=SourceEngine.PADDLEOCR, mean=0.91),
            rtl_flags=[RTLFlag(kind="mixed_direction", detail="test")],
        )
        dumped = meta.model_dump(mode="json")
        json.dumps(dumped)  # must not raise
        assert dumped["structure"]["article"] == "المادة 12"
        assert dumped["ocr_confidence"]["engine"] == "paddleocr"

    def test_structure_property_gives_typed_view(self):
        chunk = DocumentChunk(
            **{**SPEC_EXAMPLE,
               "metadata": {"structure": {"article": "المادة 12", "clause_id": "art_12"}}}
        )
        assert chunk.structure.article == "المادة 12"

    def test_structure_property_safe_when_absent(self):
        assert DocumentChunk(**SPEC_EXAMPLE).structure.article is None

    def test_is_clause_is_the_m5_filter(self):
        with_clause = DocumentChunk(
            **{**SPEC_EXAMPLE, "metadata": {"structure": {"clause_id": "art_12.cl_3"}}}
        )
        without = DocumentChunk(**SPEC_EXAMPLE)
        assert with_clause.is_clause is True
        assert without.is_clause is False


class TestBoundingBox:
    def test_corners_normalized(self):
        box = BoundingBox(x0=10, y0=20, x1=5, y1=8)
        assert box.x0 == 5 and box.x1 == 10
        assert box.y0 == 8 and box.y1 == 20

    def test_dimensions(self):
        box = BoundingBox(x0=0, y0=0, x1=10, y1=4)
        assert box.width == 10 and box.height == 4

    def test_union(self):
        u = BoundingBox.union([
            BoundingBox(x0=0, y0=0, x1=10, y1=10, page=3),
            BoundingBox(x0=5, y0=5, x1=20, y1=8, page=3),
        ])
        assert (u.x0, u.y0, u.x1, u.y1) == (0, 0, 20, 10)
        assert u.page == 3

    def test_union_of_empty_is_none(self):
        assert BoundingBox.union([]) is None

    def test_from_paddle_quad(self):
        box = BoundingBox.from_quad([[10, 20], [50, 22], [50, 40], [10, 38]], page=2, scale=0.24)
        assert box.x0 == 10 and box.x1 == 50
        assert box.y0 == 20 and box.y1 == 40
        assert box.page == 2 and box.scale == 0.24


class TestIds:
    def test_sequential_ids_match_spec_format(self):
        assert make_document_id("", seq=1) == "doc_001"
        assert make_chunk_id(17) == "chunk_017"

    def test_content_hash_is_deterministic(self):
        """Re-ingesting the same file after a pipeline change must produce the
        same document_id, or downstream indexes silently duplicate."""
        assert make_document_id("/path/to/contract.pdf") == make_document_id("/path/to/contract.pdf")

    def test_different_sources_differ(self):
        assert make_document_id("a.pdf") != make_document_id("b.pdf")


class TestIngestResult:
    def test_chunk_count_is_derived(self):
        result = DocumentIngestResult(
            document_id="doc_001", source_file="x.pdf", file_type="pdf",
            chunks=[DocumentChunk(**SPEC_EXAMPLE)],
        )
        assert result.n_chunks == 1

    def test_defaults_are_safe(self):
        result = DocumentIngestResult(document_id="d", source_file="x", file_type="pdf")
        assert result.chunks == [] and result.n_chunks == 0
        assert result.succeeded is True
        assert result.warnings == [] and result.errors == []

    def test_serializes_with_flags_and_log(self):
        result = DocumentIngestResult(
            document_id="doc_001", source_file="x.pdf", file_type="pdf",
            rtl_flags=[RTLFlag(kind="mixed_direction", page=2, detail="d")],
            engine_log=[{"page": 1, "engine": "paddleocr"}],
        )
        json.dumps(result.model_dump(mode="json"))


class TestClauseField:
    """``clause`` is a top-level field of the contract, mirroring
    ``metadata.structure.clause``. M2 declares it and defaults it to ``None``,
    so if M1 stops sending it nothing raises -- it just silently reads empty
    on every chunk. That is what this class exists to prevent."""

    def test_clause_defaults_to_none(self):
        assert DocumentChunk(**SPEC_EXAMPLE).clause is None

    def test_clause_round_trips(self):
        chunk = DocumentChunk(**{**SPEC_EXAMPLE, "clause": "Clause 1"})
        assert chunk.model_dump(mode="json")["clause"] == "Clause 1"

    def test_clause_is_part_of_the_serialized_shape_even_when_empty(self):
        """M2 destructures the key; it must be present, not omitted."""
        assert "clause" in DocumentChunk(**SPEC_EXAMPLE).model_dump(mode="json")

    def test_top_level_and_nested_clause_coexist(self):
        """The top-level field is additive -- it does not replace the
        structural view M5 filters on."""
        chunk = DocumentChunk(
            **{**SPEC_EXAMPLE,
               "clause": "Clause 1",
               "metadata": {"structure": {"clause": "Clause 1", "clause_id": "cl_1"}}}
        )
        assert chunk.clause == chunk.structure.clause == "Clause 1"
        assert chunk.is_clause is True


class TestLanguageWireValues:
    """The `Language` enum is the wire vocabulary M2 validates against.

    M2 declares `Literal["ar", "en", "ar-en", "unknown"]`. The bilingual value
    was `"mixed"` here until 2026-08-17 and was the sole cause of every chunk
    M2 rejected -- see `reports/schema_contract_verification.md`. These pin the
    exact strings so the drift cannot silently recur.
    """

    def test_wire_values_match_m2s_literal(self):
        assert {m.value for m in Language} == {"ar", "en", "ar-en", "unknown"}

    def test_bilingual_value_is_ar_en(self):
        assert Language.AR_EN.value == "ar-en"

    def test_mixed_is_no_longer_a_language_value(self):
        assert "mixed" not in {m.value for m in Language}
        with pytest.raises(ValidationError):
            DocumentChunk(**{**SPEC_EXAMPLE, "language": "mixed"})

    def test_bilingual_chunk_serializes_as_ar_en(self):
        """`use_enum_values=True`, so the dumped value is the raw string."""
        chunk = DocumentChunk(**{**SPEC_EXAMPLE, "language": Language.AR_EN})
        assert chunk.model_dump(mode="json")["language"] == "ar-en"
