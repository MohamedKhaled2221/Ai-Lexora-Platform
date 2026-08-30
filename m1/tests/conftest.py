"""Shared pytest fixtures.

The interim corpus is the fixture source. Tests that need a corpus file skip
(rather than fail) when it is absent, so the suite still runs on a fresh clone
before ``scripts/fetch_public_corpus.py`` and ``scripts/make_synthetic_corpus.py``
have been run -- and so a network outage during corpus fetch does not look like
a code regression.

Tests that need a real OCR engine are marked ``@pytest.mark.ocr`` and skipped
unless the engine is importable/installed. Run just those with::

    pytest -m ocr
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import (  # noqa: E402
    ChunkingConfig,
    NormalizationConfig,
    OCRConfig,
    PipelineConfig,
    PUBLIC_CORPUS_DIR,
    RTLConfig,
    SYNTHETIC_CORPUS_DIR,
)


def pytest_configure(config):
    config.addinivalue_line("markers", "ocr: requires a working OCR engine (slow)")
    config.addinivalue_line("markers", "docling: requires Docling models (slow)")
    config.addinivalue_line("markers", "slow: takes more than a few seconds")


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> PipelineConfig:
    """Default pipeline config with OCR and Docling off.

    Off by default so the bulk of the suite is fast and deterministic; the
    tests that genuinely exercise those engines switch them back on.
    """
    cfg = PipelineConfig()
    cfg.ocr.enabled = False
    cfg.extraction.use_docling = False
    return cfg


@pytest.fixture
def norm_config() -> NormalizationConfig:
    return NormalizationConfig()


@pytest.fixture
def rtl_config() -> RTLConfig:
    return RTLConfig()


@pytest.fixture
def chunk_config() -> ChunkingConfig:
    return ChunkingConfig()


@pytest.fixture
def ocr_config() -> OCRConfig:
    return OCRConfig()


# ---------------------------------------------------------------------------
# Corpus fixtures
# ---------------------------------------------------------------------------


def _corpus_file(directory: Path, name: str) -> Path:
    path = directory / name
    if not path.exists():
        pytest.skip(
            f"corpus file {name} missing -- run scripts/fetch_public_corpus.py "
            "and scripts/make_synthetic_corpus.py"
        )
    return path


@pytest.fixture
def synthetic_dir() -> Path:
    """The synthetic corpus directory itself, for tests that check a fixture's
    presence themselves rather than skipping on a single named file."""
    return SYNTHETIC_CORPUS_DIR


@pytest.fixture
def statute_txt() -> Path:
    """Arabic statute, TXT. Full الباب/الفصل/المادة hierarchy."""
    return _corpus_file(SYNTHETIC_CORPUS_DIR, "synthetic_statute_ar.txt")


@pytest.fixture
def memo_txt() -> Path:
    """Heavily code-switched Arabic/English memo. RTL flags expected."""
    return _corpus_file(SYNTHETIC_CORPUS_DIR, "synthetic_memo_mixed.txt")


@pytest.fixture
def visual_order_txt() -> Path:
    """Same statute stored in VISUAL order -- the rtl_fix repair fixture."""
    return _corpus_file(SYNTHETIC_CORPUS_DIR, "synthetic_visual_order_ar.txt")


@pytest.fixture
def contract_pdf() -> Path:
    """Bilingual contract, text-based PDF with tables and a stamp box."""
    return _corpus_file(SYNTHETIC_CORPUS_DIR, "synthetic_contract_bilingual.pdf")


@pytest.fixture
def contract_docx() -> Path:
    return _corpus_file(SYNTHETIC_CORPUS_DIR, "synthetic_contract_ar.docx")


@pytest.fixture
def lease_docx() -> Path:
    """Bilingual lease with decimal (1.1 / 2.3) clause numbering."""
    return _corpus_file(SYNTHETIC_CORPUS_DIR, "synthetic_lease_bilingual.docx")


@pytest.fixture
def scanned_pdf() -> Path:
    """Image-only PDF derived from a public Arabic statute, with ground truth."""
    return _corpus_file(SYNTHETIC_CORPUS_DIR, "scan_wipo_eg088ar_1_150dpi.pdf")


@pytest.fixture
def scanned_pdf_groundtruth() -> Path:
    return _corpus_file(SYNTHETIC_CORPUS_DIR, "scan_wipo_eg088ar_1_150dpi.groundtruth.txt")


@pytest.fixture
def stamped_image() -> Path:
    return _corpus_file(SYNTHETIC_CORPUS_DIR, "synthetic_stamped_page.png")


@pytest.fixture
def public_arabic_pdf() -> Path:
    """A real public Arabic legal PDF (digitally native)."""
    return _corpus_file(PUBLIC_CORPUS_DIR, "constitute_egypt_2014_ar.pdf")


@pytest.fixture
def public_english_pdf() -> Path:
    return _corpus_file(PUBLIC_CORPUS_DIR, "constitute_egypt_2014_en.pdf")


# ---------------------------------------------------------------------------
# Engine availability
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def has_paddle() -> bool:
    from src.ocr_pipeline import paddle_available

    return paddle_available()


@pytest.fixture(scope="session")
def has_tesseract() -> bool:
    from src.ocr_pipeline import tesseract_available

    return tesseract_available()


@pytest.fixture(scope="session")
def has_docling() -> bool:
    from src.extract_pymupdf_docling import docling_available

    return docling_available()


# ---------------------------------------------------------------------------
# Synthetic in-memory documents
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_txt(tmp_path):
    """Factory: write text to a temp .txt and return the path."""

    def _make(content: str, name: str = "doc.txt", encoding: str = "utf-8") -> Path:
        p = tmp_path / name
        p.write_text(content, encoding=encoding)
        return p

    return _make


@pytest.fixture
def make_doc():
    """Factory building an ExtractedDocument from ``[(page_no, [texts])]``.

    Lets chunking and structure tests run without touching any file or engine.
    """
    from src.document_chunk_schema import SourceEngine
    from src.structure_preservation import ExtractedDocument, ExtractedPage, TextBlock

    def _make(pages: list[tuple[int, list[str]]], doc_id: str = "doc_test") -> ExtractedDocument:
        doc = ExtractedDocument(document_id=doc_id, source_path="memory://test", file_type="txt")
        for pno, texts in pages:
            page = ExtractedPage(page_number=pno, source_engine=SourceEngine.PLAINTEXT)
            for i, t in enumerate(texts):
                page.blocks.append(
                    TextBlock(text=t, page=pno, order=i, source_engine=SourceEngine.PLAINTEXT)
                )
            doc.pages.append(page)
        return doc

    return _make
