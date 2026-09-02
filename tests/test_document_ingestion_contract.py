import pytest
from pydantic import ValidationError

from src.schemas import DocumentChunk, EmbeddedDocumentChunk


def test_document_chunk_matches_m1_wire_contract():
    chunk = DocumentChunk(
        document_id="doc_001",
        chunk_id="chunk_017",
        text="Either party may terminate the agreement.",
        page=12,
        section="Termination",
        clause="Clause 7",
        language="en",
        document_type="contract",
        metadata={
            "jurisdiction": "Egypt",
        },
    )

    assert chunk.page == 12
    assert chunk.clause == "Clause 7"
    assert chunk.document_type == "contract"
    assert chunk.metadata["jurisdiction"] == "Egypt"


def test_document_chunk_rejects_invalid_m1_values():
    with pytest.raises(ValidationError):
        DocumentChunk(
            document_id="doc 001",
            chunk_id="chunk_001",
            text="text",
            page=1,
        )

    with pytest.raises(ValidationError):
        DocumentChunk(
            document_id="doc_001",
            chunk_id="chunk_001",
            text="   ",
            page=1,
        )

    with pytest.raises(ValidationError):
        DocumentChunk(
            document_id="doc_001",
            chunk_id="chunk_001",
            text="text",
            page=0,
        )


def test_embedded_document_chunk_preserves_source_metadata():
    embedded = EmbeddedDocumentChunk(
        document_id="doc_001",
        chunk_id="chunk_017",
        text="Either party may terminate the agreement.",
        page=12,
        section="Termination",
        clause="Clause 7",
        language="en",
        document_type="contract",
        metadata={
            "jurisdiction": "Egypt",
        },
        embedding=[
            0.1,
            0.2,
            0.3,
        ],
        model="BAAI/bge-m3",
        dimension=3,
    )

    dumped = embedded.model_dump()

    assert (
        dumped["text"]
        == "Either party may terminate the agreement."
    )
    assert dumped["page"] == 12
    assert dumped["section"] == "Termination"
    assert dumped["clause"] == "Clause 7"
    assert dumped["language"] == "en"
    assert dumped["document_type"] == "contract"
    assert dumped["metadata"] == {
        "jurisdiction": "Egypt",
    }
