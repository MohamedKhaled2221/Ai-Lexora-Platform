"""Tests for the two handoff endpoints.

``POST /ingest`` (M1 -> M2/M3) and ``POST /clauses`` (M1 -> M5) are integration
contracts with two other team members, so the response *shape* is asserted
explicitly, not just the status code.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api import app, get_config
from src.config import PipelineConfig


@pytest.fixture
def client():
    """TestClient with OCR and Docling disabled for speed and determinism."""

    def fast_config() -> PipelineConfig:
        cfg = PipelineConfig()
        cfg.ocr.enabled = False
        cfg.extraction.use_docling = False
        return cfg

    app.dependency_overrides[get_config] = fast_config
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _upload(path, mime="application/octet-stream"):
    return {"file": (path.name, path.read_bytes(), mime)}


class TestIngestEndpoint:
    def test_txt_ingest(self, client, statute_txt):
        r = client.post("/ingest", files=_upload(statute_txt, "text/plain"))
        assert r.status_code == 200
        body = r.json()
        assert body["succeeded"] is True
        assert body["n_chunks"] == len(body["chunks"]) > 0
        assert body["file_type"] == "txt"
        assert body["document_type"] == "law"

    def test_chunks_match_the_spec_shape(self, client, statute_txt):
        """This is the field set M2/M3 destructure. It must not drift.

        The access-control triple was added 2026-09-05 for M3 tenancy
        filtering. It is additive and every field defaults to None -- M1 does
        not know who may read a document, so the M3 ingest boundary stamps the
        real values from the authenticated caller. Listed explicitly so this
        test still catches a field nobody decided on.
        """
        spec_fields = {
            "document_id", "chunk_id", "text", "page",
            "section", "clause", "language", "document_type", "metadata",
        }
        access_control_fields = {
            "client_id", "matter_id", "confidentiality_level",
        }
        chunks = client.post("/ingest", files=_upload(statute_txt)).json()["chunks"]
        for chunk in chunks:
            assert set(chunk) == spec_fields | access_control_fields
            for name in access_control_fields:
                assert chunk[name] is None
            assert isinstance(chunk["metadata"], dict)
            assert chunk["text"].strip()

    def test_pdf_ingest_with_bboxes(self, client, contract_pdf):
        body = client.post("/ingest", files=_upload(contract_pdf, "application/pdf")).json()
        assert body["pdf_kind"] == "text"
        assert body["n_pages"] == 3
        assert any(c["metadata"].get("bbox") for c in body["chunks"])

    def test_docx_ingest(self, client, contract_docx):
        body = client.post("/ingest", files=_upload(contract_docx)).json()
        assert body["file_type"] == "docx"
        assert body["n_chunks"] > 0

    def test_diagnostics_present(self, client, memo_txt):
        body = client.post("/ingest", files=_upload(memo_txt)).json()
        assert body["engine_log"]
        assert body["rtl_flags"], "code-switched memo should surface reading-order flags"
        assert "total" in body["timings_ms"]

    def test_rtl_flags_carry_detail(self, client, memo_txt):
        flags = client.post("/ingest", files=_upload(memo_txt)).json()["rtl_flags"]
        for flag in flags:
            assert flag["kind"] and flag["detail"]

    def test_document_id_override(self, client, statute_txt):
        body = client.post(
            "/ingest", files=_upload(statute_txt), params={"document_id": "DMS-99"}
        ).json()
        assert body["document_id"] == "DMS-99"
        assert all(c["document_id"] == "DMS-99" for c in body["chunks"])

    def test_chunk_size_override(self, client, public_arabic_pdf):
        small = client.post("/ingest", files=_upload(public_arabic_pdf),
                            params={"target_chunk_chars": 400, "max_chunk_chars": 600}).json()
        large = client.post("/ingest", files=_upload(public_arabic_pdf),
                            params={"target_chunk_chars": 2000, "max_chunk_chars": 4000}).json()
        assert small["n_chunks"] > large["n_chunks"]
        assert all(len(c["text"]) <= 600 for c in small["chunks"])

    def test_respect_structure_false_is_a_baseline(self, client, statute_txt):
        body = client.post("/ingest", files=_upload(statute_txt),
                           params={"respect_structure": False}).json()
        assert all(c["metadata"]["chunk_strategy"] == "paragraph" for c in body["chunks"])

    def test_display_form_opt_in(self, client, statute_txt):
        off = client.post("/ingest", files=_upload(statute_txt)).json()
        on = client.post("/ingest", files=_upload(statute_txt),
                         params={"emit_display_form": True}).json()
        assert all(c["metadata"].get("display_text") is None for c in off["chunks"])
        assert any(c["metadata"].get("display_text") for c in on["chunks"])

    def test_keep_raw_text_toggle(self, client, statute_txt):
        body = client.post("/ingest", files=_upload(statute_txt),
                           params={"keep_raw_text": False}).json()
        assert all(c["metadata"].get("raw_text") is None for c in body["chunks"])


class TestIngestErrors:
    def test_unsupported_extension_rejected(self, client, tmp_path):
        p = tmp_path / "thing.exe"
        p.write_bytes(b"MZ" + b"\x00" * 500)
        r = client.post("/ingest", files=_upload(p))
        assert r.status_code == 415
        assert "unsupported" in r.json()["detail"]

    def test_empty_upload_rejected(self, client, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_bytes(b"")
        assert client.post("/ingest", files=_upload(p)).status_code == 400

    def test_unprocessable_document_reports_why(self, client, tmp_path):
        p = tmp_path / "broken.pdf"
        p.write_bytes(b"%PDF-1.4\nnot actually a pdf\n" * 40)
        r = client.post("/ingest", files=_upload(p, "application/pdf"))
        assert r.status_code == 422
        assert r.json()["detail"]["errors"]

    def test_missing_file_is_a_validation_error(self, client):
        assert client.post("/ingest").status_code == 422


class TestClausesEndpoint:
    def test_returns_clause_level_view(self, client, contract_docx):
        r = client.post("/clauses", files=_upload(contract_docx))
        assert r.status_code == 200
        body = r.json()
        assert body["n_clauses"] == len(body["clauses"]) > 0
        assert body["n_chunks_total"] >= body["n_clauses"]

    def test_clause_shape_is_the_m5_contract(self, client, contract_docx):
        clauses = client.post("/clauses", files=_upload(contract_docx)).json()["clauses"]
        for clause in clauses:
            assert set(clause) == {
                "chunk_id", "clause_id", "article", "clause", "section",
                "heading_path", "page", "language", "is_table", "text",
            }
            assert clause["text"].strip()

    def test_every_clause_has_an_identity(self, client, contract_docx):
        """The endpoint's purpose is clause-granular data. A returned clause
        with no identifier would be indistinguishable from a paragraph."""
        clauses = client.post("/clauses", files=_upload(contract_docx)).json()["clauses"]
        assert all(c["clause_id"] or c["article"] or c["clause"] for c in clauses)

    def test_contracts_only_filter(self, client, statute_txt):
        body = client.post("/clauses", files=_upload(statute_txt),
                           params={"contracts_only": True}).json()
        assert body["document_type"] == "law"
        assert body["n_clauses"] == 0

    def test_statute_articles_available_without_filter(self, client, statute_txt):
        body = client.post("/clauses", files=_upload(statute_txt)).json()
        assert body["n_clauses"] > 0
        assert any("المادة" in (c["article"] or "") for c in body["clauses"])

    def test_exclude_tables(self, client, contract_docx):
        with_t = client.post("/clauses", files=_upload(contract_docx)).json()
        without = client.post("/clauses", files=_upload(contract_docx),
                              params={"include_tables": False}).json()
        assert without["n_clauses"] <= with_t["n_clauses"]

    def test_heading_path_present_for_nested_clauses(self, client, lease_docx):
        clauses = client.post("/clauses", files=_upload(lease_docx)).json()["clauses"]
        assert any(c["heading_path"] for c in clauses)


class TestOpsEndpoints:
    def test_health_reports_engine_availability(self, client):
        body = client.get("/health").json()
        assert body["status"] in ("ok", "degraded")
        for engine in ("pymupdf", "docling", "paddleocr", "tesseract", "pyarabic"):
            assert engine in body["engines"]

    def test_config_endpoint_exposes_settings(self, client):
        body = client.get("/config").json()
        assert "chunking" in body and "normalization" in body
        assert "target_chunk_chars" in body["chunking"]

    def test_openapi_documents_both_handoffs(self, client):
        spec = client.get("/openapi.json").json()
        assert "/ingest" in spec["paths"]
        assert "/clauses" in spec["paths"]
        tags = {
            t for path in ("/ingest", "/clauses")
            for t in spec["paths"][path]["post"].get("tags", [])
        }
        assert tags == {"M1 -> M2/M3", "M1 -> M5"}

    def test_endpoints_are_documented(self, client):
        """Two other members integrate against these; the docstrings are the
        integration docs and must not be empty."""
        spec = client.get("/openapi.json").json()
        for path in ("/ingest", "/clauses"):
            assert len(spec["paths"][path]["post"]["description"]) > 200
