"""End-to-end pipeline tests over the interim corpus.

These assert the *contract* -- that every stage runs in the specified order and
every spec field is populated -- rather than exact text, which depends on engine
versions.
"""

from __future__ import annotations

import pytest

from src.config import PipelineConfig
from src.document_chunk_schema import DocumentType, Language
from src.pipeline import (
    clause_view,
    get_clause_chunks,
    ingest,
    ingest_batch,
    process_document,
)


@pytest.fixture
def fast_config() -> PipelineConfig:
    """OCR and Docling off: exercises the pipeline wiring without model loads."""
    cfg = PipelineConfig()
    cfg.ocr.enabled = False
    cfg.extraction.use_docling = False
    return cfg


class TestTxtPath:
    def test_statute_produces_article_chunks(self, statute_txt, fast_config):
        result = process_document(statute_txt, fast_config)
        assert result.succeeded
        assert result.n_chunks > 5
        assert result.document_type == DocumentType.LAW.value
        assert result.language == Language.AR.value

    def test_every_spec_field_populated(self, statute_txt, fast_config):
        for chunk in process_document(statute_txt, fast_config).chunks:
            assert chunk.document_id and chunk.chunk_id
            assert chunk.text.strip()
            assert chunk.page == 1, "TXT has no pagination; page must be 1"
            assert chunk.language in {"ar", "en", "ar-en", "unknown"}
            assert chunk.document_type
            assert chunk.metadata.get("jurisdiction")
            assert chunk.metadata.get("source_engine")
            assert chunk.metadata.get("chunk_strategy")

    def test_articles_detected_including_bis(self, statute_txt, fast_config):
        """'مكرر' (bis) numbering is an Egyptian legislative convention that a
        naive numeric parser drops entirely."""
        chunks = process_document(statute_txt, fast_config).chunks
        articles = {(c.metadata["structure"] or {}).get("article") for c in chunks}
        assert "المادة 7" in articles
        assert any(a and "مكرر" in a for a in articles), "المادة (7) مكرر was lost"

    def test_mixed_memo_raises_rtl_flags(self, memo_txt, fast_config):
        """Code-switched text must be surfaced for review, not silently passed."""
        result = process_document(memo_txt, fast_config)
        assert result.succeeded
        kinds = {f.kind for f in result.rtl_flags}
        assert "mixed_direction" in kinds
        assert result.language == Language.AR_EN.value

    def test_visual_order_file_is_flagged(self, visual_order_txt, fast_config):
        result = process_document(visual_order_txt, fast_config)
        kinds = {f.kind for f in result.rtl_flags}
        assert "presentation_forms_found" in kinds
        assert kinds & {"visual_order_repaired", "visual_order_suspected",
                        "neutral_order_mirrored"}


class TestPdfPath:
    def test_text_pdf_end_to_end(self, contract_pdf, fast_config):
        result = process_document(contract_pdf, fast_config)
        assert result.succeeded
        assert result.pdf_kind == "text"
        assert result.n_pages == 3
        assert result.n_chunks > 5
        assert result.document_type == DocumentType.CONTRACT.value

    def test_bounding_boxes_reach_the_chunks(self, contract_pdf, fast_config):
        """Bounding boxes are a named spec requirement; they must survive all
        the way to chunk metadata, not just exist mid-pipeline."""
        chunks = process_document(contract_pdf, fast_config).chunks
        boxed = [c for c in chunks if c.metadata.get("bbox")]
        assert boxed, "no chunk carried a bounding box"
        box = boxed[0].metadata["bbox"]
        assert box["x1"] > box["x0"] and box["y1"] > box["y0"]
        assert boxed[0].metadata["bboxes"]

    def test_pages_all_represented(self, contract_pdf, fast_config):
        result = process_document(contract_pdf, fast_config)
        pages = {c.page for c in result.chunks if c.page}
        assert pages == set(range(1, result.n_pages + 1))

    def test_tables_survive(self, contract_pdf, fast_config):
        chunks = process_document(contract_pdf, fast_config).chunks
        tables = [c for c in chunks if c.metadata.get("is_table")]
        assert tables
        assert tables[0].metadata["table_markdown"]

    def test_public_arabic_statute(self, public_arabic_pdf, fast_config):
        result = process_document(public_arabic_pdf, fast_config)
        assert result.succeeded
        assert result.language in (Language.AR.value, Language.AR_EN.value)
        assert result.n_chunks > 20
        assert all(c.metadata["jurisdiction"] for c in result.chunks)

    def test_english_document_classified_english(self, public_english_pdf, fast_config):
        result = process_document(public_english_pdf, fast_config)
        assert result.language == Language.EN.value


class TestDocxPath:
    def test_contract_docx(self, contract_docx, fast_config):
        result = process_document(contract_docx, fast_config)
        assert result.succeeded
        assert result.document_type == DocumentType.CONTRACT.value
        assert result.n_chunks > 5
        assert any("pagination" in w for w in result.warnings)

    def test_lease_clause_numbering(self, lease_docx, fast_config):
        result = process_document(lease_docx, fast_config)
        ids = {(c.metadata["structure"] or {}).get("clause_id") for c in result.chunks}
        assert any(i and i.startswith("cl_") for i in ids)


class TestStageOrdering:
    def test_normalization_runs_before_structure_detection(self, visual_order_txt, fast_config):
        """Markers like 'الـمـادة ١٢' only match after tatweel is stripped and
        digits folded, so normalization must precede structure annotation. If
        the order flips, structure detection silently collapses to zero."""
        result = process_document(visual_order_txt, fast_config)
        with_structure = [c for c in result.chunks if (c.metadata["structure"] or {}).get("clause_id")]
        assert with_structure, "no structure detected -- stage order may have flipped"

    def test_timings_cover_every_stage(self, statute_txt, fast_config):
        timings = process_document(statute_txt, fast_config).timings_ms
        for stage in ("detect", "rtl_fix", "normalize", "structure", "chunking", "total"):
            assert stage in timings

    def test_engine_log_records_the_route(self, contract_pdf, fast_config):
        result = process_document(contract_pdf, fast_config)
        detect_entry = next(e for e in result.engine_log if e["engine"] == "type_detection")
        assert detect_entry["file_type"] == "pdf"
        assert detect_entry["pdf_kind"] == "text"

    def test_raw_text_kept_for_ab_testing(self, statute_txt, fast_config):
        chunks = process_document(statute_txt, fast_config).chunks
        assert any(c.metadata.get("raw_text") for c in chunks)

    def test_raw_text_can_be_dropped(self, statute_txt, fast_config):
        fast_config.keep_raw_text_in_metadata = False
        chunks = process_document(statute_txt, fast_config).chunks
        assert all(c.metadata.get("raw_text") is None for c in chunks)


class TestFailureHandling:
    def test_unsupported_type_fails_gracefully(self, tmp_path, fast_config):
        p = tmp_path / "legacy.doc"
        p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 400)
        result = process_document(p, fast_config)
        assert result.succeeded is False
        assert result.errors
        assert result.chunks == []

    def test_corrupt_pdf_does_not_raise(self, tmp_path, fast_config):
        p = tmp_path / "broken.pdf"
        p.write_bytes(b"%PDF-1.4\ngarbage that is not a pdf at all\n" * 50)
        result = process_document(p, fast_config)
        assert result.succeeded is False
        assert result.errors

    def test_empty_file_fails_cleanly(self, tmp_path, fast_config):
        p = tmp_path / "empty.txt"
        p.write_text("", encoding="utf-8")
        result = process_document(p, fast_config)
        assert result.chunks == []

    def test_fail_fast_raises(self, tmp_path):
        cfg = PipelineConfig(fail_fast=True)
        p = tmp_path / "legacy.doc"
        p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 400)
        with pytest.raises(Exception):
            process_document(p, cfg)

    def test_batch_survives_one_bad_document(self, tmp_path, statute_txt, fast_config):
        bad = tmp_path / "bad.doc"
        bad.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 400)
        results = ingest_batch([statute_txt, bad, statute_txt], fast_config)
        assert len(results) == 3
        assert [r.succeeded for r in results] == [True, False, True]

    def test_batch_ids_follow_spec_format(self, statute_txt, memo_txt, fast_config):
        results = ingest_batch([statute_txt, memo_txt], fast_config)
        assert [r.document_id for r in results] == ["doc_001", "doc_002"]


class TestDeterminism:
    def test_same_input_gives_same_output(self, statute_txt, fast_config):
        a = process_document(statute_txt, fast_config)
        b = process_document(statute_txt, fast_config)
        assert a.document_id == b.document_id
        assert [c.chunk_id for c in a.chunks] == [c.chunk_id for c in b.chunks]
        assert [c.text for c in a.chunks] == [c.text for c in b.chunks]

    def test_document_id_override(self, statute_txt, fast_config):
        result = process_document(statute_txt, fast_config, document_id="DMS-12345")
        assert result.document_id == "DMS-12345"
        assert all(c.document_id == "DMS-12345" for c in result.chunks)


class TestHandoffs:
    def test_ingest_returns_chunks(self, statute_txt, fast_config):
        chunks = ingest(statute_txt, fast_config)
        assert chunks and all(c.text for c in chunks)

    def test_ingest_of_bad_file_returns_empty(self, tmp_path, fast_config):
        p = tmp_path / "x.doc"
        p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
        assert ingest(p, fast_config) == []

    def test_clause_filter_keeps_only_identified_clauses(self, statute_txt, fast_config):
        chunks = ingest(statute_txt, fast_config)
        clauses = get_clause_chunks(chunks)
        assert clauses
        assert len(clauses) <= len(chunks)
        assert all(c.is_clause for c in clauses)

    def test_clause_filter_by_document_type(self, contract_docx, fast_config):
        chunks = ingest(contract_docx, fast_config)
        assert get_clause_chunks(chunks, document_types=["contract"])
        assert get_clause_chunks(chunks, document_types=["court_ruling"]) == []

    def test_clause_view_shape_for_m5(self, contract_docx, fast_config):
        result = process_document(contract_docx, fast_config)
        view = clause_view(result)
        assert view["document_id"] == result.document_id
        assert view["n_clauses"] == len(view["clauses"])
        for clause in view["clauses"]:
            assert set(clause) >= {
                "chunk_id", "clause_id", "article", "clause", "section",
                "heading_path", "page", "language", "is_table", "text",
            }

    def test_clause_view_can_exclude_tables(self, contract_docx, fast_config):
        result = process_document(contract_docx, fast_config)
        with_tables = clause_view(result, include_tables=True)["n_clauses"]
        without = clause_view(result, include_tables=False)["n_clauses"]
        assert without <= with_tables
