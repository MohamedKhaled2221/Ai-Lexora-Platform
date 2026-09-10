from __future__ import annotations

import pytest

from src.m1.knowledge_ingestion_adapter import KnowledgeIngestionAdapter


class FakeProcessor:
    def __init__(self, payload):
        self.payload = payload
        self.received_path = None

    def process(self, source_path: str):
        self.received_path = source_path
        return self.payload


def test_ingest_normalizes_passages():
    processor = FakeProcessor(
        {
            "passages": [
                {
                    "passage_id": "P-001",
                    "text": "This is an English legal passage.",
                    "language": "en",
                    "page": 2,
                    "section": "Definitions",
                    "clause": "Clause 1",
                    "heading": "Definitions",
                    "metadata": {
                        "source": "approved-source",
                    },
                }
            ]
        }
    )

    adapter = KnowledgeIngestionAdapter(processor)

    record = adapter.ingest(
        "contract.pdf",
        document_id="DOC-001",
        source_type="law",
        title="Test Legal Document",
        jurisdiction="EG",
        approved=True,
    )

    assert processor.received_path == "contract.pdf"

    assert record.source_document_id == "DOC-001"
    assert record.source_type == "law"
    assert record.title == "Test Legal Document"
    assert record.jurisdiction == "EG"
    assert record.approved is True

    assert len(record.passages) == 1

    passage = record.passages[0]

    assert passage.passage_id == "P-001"
    assert passage.document_id == "DOC-001"
    assert passage.text == "This is an English legal passage."
    assert passage.language == "en"

    assert passage.page_start == 2
    assert passage.page_end == 2

    assert passage.section == "Definitions"
    assert passage.clause == "Clause 1"
    assert passage.heading == "Definitions"

    assert passage.source_uri == "contract.pdf"


def test_ingest_supports_sections_fallback():
    processor = FakeProcessor(
        {
            "sections": [
                {
                    "section_id": "S-001",
                    "content": "Arabic legal content.",
                    "language": "ar",
                    "page": 3,
                }
            ]
        }
    )

    adapter = KnowledgeIngestionAdapter(processor)

    record = adapter.ingest(
        "law.pdf",
        document_id="DOC-002",
    )

    assert len(record.passages) == 1

    passage = record.passages[0]

    assert passage.passage_id != ""
    assert passage.text == "Arabic legal content."
    assert passage.language == "ar"
    assert passage.page_start == 3
    assert passage.page_end == 3


def test_ingest_supports_chunks_fallback():
    processor = FakeProcessor(
        {
            "chunks": [
                {
                    "chunk_id": "CH-001",
                    "text": "English chunk.",
                }
            ]
        }
    )

    adapter = KnowledgeIngestionAdapter(processor)

    record = adapter.ingest(
        "document.pdf",
        document_id="DOC-003",
    )

    assert len(record.passages) == 1

    passage = record.passages[0]

    assert passage.passage_id == "CH-001"
    assert passage.text == "English chunk."
    assert passage.language == "en"


def test_ingest_handles_page_span():
    processor = FakeProcessor(
        {
            "passages": [
                {
                    "passage_id": "P-002",
                    "text": "A passage spanning multiple pages.",
                    "metadata": {
                        "page_span": [4, 6, 5],
                    },
                }
            ]
        }
    )

    adapter = KnowledgeIngestionAdapter(processor)

    record = adapter.ingest(
        "document.pdf",
        document_id="DOC-004",
    )

    passage = record.passages[0]

    assert passage.page_start == 4
    assert passage.page_end == 6


def test_ingest_extracts_structure_from_metadata():
    processor = FakeProcessor(
        {
            "passages": [
                {
                    "text": "Legal clause text.",
                    "metadata": {
                        "structure": {
                            "section": "Confidentiality",
                            "clause": "Clause 4",
                        },
                        "heading": "Confidential Information",
                    },
                }
            ]
        }
    )

    adapter = KnowledgeIngestionAdapter(processor)

    record = adapter.ingest(
        "nda.pdf",
        document_id="DOC-005",
    )

    passage = record.passages[0]

    assert passage.section == "Confidentiality"
    assert passage.clause == "Clause 4"
    assert passage.heading == "Confidential Information"

    assert passage.metadata["structure"]["section"] == "Confidentiality"
    assert passage.metadata["structure"]["clause"] == "Clause 4"


def test_ingest_supports_m1_structure_fallback():
    processor = FakeProcessor(
        {
            "passages": [
                {
                    "text": "Structured legal passage.",
                    "metadata": {
                        "m1_structure": {
                            "section": "Payment",
                            "clause": "Clause 7",
                        }
                    },
                }
            ]
        }
    )

    adapter = KnowledgeIngestionAdapter(processor)

    record = adapter.ingest(
        "agreement.pdf",
        document_id="DOC-006",
    )

    passage = record.passages[0]

    assert passage.section == "Payment"
    assert passage.clause == "Clause 7"


def test_language_is_detected_when_not_explicit():
    processor = FakeProcessor(
        {
            "passages": [
                {"text": "This is English text."},
                {"text": "هذا نص قانوني باللغة العربية"},
                {"text": "This is نص مختلط."},
            ]
        }
    )

    adapter = KnowledgeIngestionAdapter(processor)

    record = adapter.ingest(
        "mixed.pdf",
        document_id="DOC-007",
    )

    languages = [passage.language for passage in record.passages]

    assert languages == ["en", "ar", "ar-en"]


def test_explicit_language_has_priority():
    processor = FakeProcessor(
        {
            "passages": [
                {
                    "text": "This text is actually English.",
                    "language": "ar",
                }
            ]
        }
    )

    adapter = KnowledgeIngestionAdapter(processor)

    record = adapter.ingest(
        "document.pdf",
        document_id="DOC-008",
    )

    assert record.passages[0].language == "ar"


def test_empty_passages_are_ignored():
    processor = FakeProcessor(
        {
            "passages": [
                {"text": ""},
                {"text": "   "},
                {"text": "Valid passage."},
                {"content": ""},
                "invalid-item",
            ]
        }
    )

    adapter = KnowledgeIngestionAdapter(processor)

    record = adapter.ingest(
        "document.pdf",
        document_id="DOC-009",
    )

    assert len(record.passages) == 1
    assert record.passages[0].text == "Valid passage."


def test_unapproved_source_is_rejected():
    processor = FakeProcessor({"passages": []})

    adapter = KnowledgeIngestionAdapter(processor)

    with pytest.raises(ValueError, match="Only approved sources"):
        adapter.ingest(
            "unapproved.pdf",
            document_id="DOC-010",
            approved=False,
        )


def test_invalid_source_type_falls_back_to_other():
    processor = FakeProcessor(
        {
            "passages": [
                {"text": "Legal content."},
            ]
        }
    )

    adapter = KnowledgeIngestionAdapter(processor)

    record = adapter.ingest(
        "document.pdf",
        document_id="DOC-011",
        source_type="random_type",
    )

    assert record.source_type == "other"


def test_record_language_uses_dominant_passage_language():
    processor = FakeProcessor(
        {
            "passages": [
                {"text": "English one.", "language": "en"},
                {"text": "English two.", "language": "en"},
                {"text": "Arabic.", "language": "ar"},
            ]
        }
    )

    adapter = KnowledgeIngestionAdapter(processor)

    record = adapter.ingest(
        "document.pdf",
        document_id="DOC-012",
    )

    assert record.language == "en"


def test_missing_passage_list_raises_error():
    processor = FakeProcessor(
        {
            "metadata": {
                "document_id": "DOC-013",
            }
        }
    )

    adapter = KnowledgeIngestionAdapter(processor)

    with pytest.raises(ValueError, match="no passage list"):
        adapter.ingest(
            "document.pdf",
            document_id="DOC-013",
        )