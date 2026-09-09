"""
Steps 4 and 6: the encoder safety net, and sparse for token-split chunks.

Step 4's point is that ``max_length`` should now be a no-op. A safety net that
is never exercised is indistinguishable from one that is silently catching
things every day, so it announces itself when it fires.

Step 6's point is that chunk splitting changed the *input* to both vector
paths, and sparse landed after the last chunking work -- so the sparse half
needs confirming on newly-split chunks, not just the dense half.
"""

import logging
from collections import defaultdict
from unittest.mock import patch

import numpy as np
import pytest

from src.embedding_service import EmbeddingService


class _FakeTokenizer:
    """Token count proportional to length, so tests can drive truncation."""

    def __init__(self, chars_per_token=2):
        self.chars_per_token = chars_per_token

    def encode(self, text, add_special_tokens=True):
        return [0] * (len(text) // self.chars_per_token + 2)


class _FakeBGEM3:
    def __init__(self, *args, tokenizer=None, **kwargs):
        self.tokenizer = tokenizer
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.append({"texts": list(texts), **kwargs})

        result = {
            "dense_vecs": [
                np.array([0.1, 0.2, 0.3], dtype=np.float32) for _ in texts
            ]
        }

        if kwargs.get("return_sparse"):
            result["lexical_weights"] = [
                defaultdict(
                    int,
                    {
                        str(1000 + index): np.float32(0.3),
                        str(2000 + index): np.float32(0.1),
                    },
                )
                for index, _ in enumerate(texts)
            ]

        return result


def _service(tokenizer=None, **kwargs):
    fake = _FakeBGEM3(tokenizer=tokenizer)

    with patch(
        "src.embedding_service.BGEM3FlagModel",
        return_value=fake,
    ):
        return EmbeddingService(**kwargs), fake


# ---------------------------------------------------------------------------
# Step 4: the safety net stays, and speaks up
# ---------------------------------------------------------------------------


def test_max_length_is_still_passed_to_the_encoder():
    """The net stays in place even though chunking should keep it slack."""

    service, fake = _service(max_length=512)

    service.embed_text("a short clause")

    assert fake.calls[0]["max_length"] == 512


def test_no_warning_for_text_within_the_window(caplog):
    """The normal case after token-aware chunking: silence."""

    service, _ = _service(tokenizer=_FakeTokenizer(), max_length=512)

    with caplog.at_level(logging.WARNING, logger="src.embedding_service"):
        service.embed_text("x" * 200)  # ~102 tokens

    assert not [
        r for r in caplog.records if "encoder window" in r.message
    ]


def test_truncation_is_reported_rather_than_silent(caplog):
    """
    Truncation returns a perfectly normal-looking vector built from only part
    of the text, so nothing downstream can tell it happened.
    """

    service, _ = _service(tokenizer=_FakeTokenizer(), max_length=512)

    with caplog.at_level(logging.WARNING, logger="src.embedding_service"):
        service.embed_text("x" * 4000)  # ~2002 tokens

    warnings = [
        r for r in caplog.records if "encoder window" in r.message
    ]

    assert len(warnings) == 1
    assert "will not be embedded" in warnings[0].message


def test_the_warning_can_be_switched_off():
    service, _ = _service(
        tokenizer=_FakeTokenizer(),
        max_length=512,
        warn_on_truncation=False,
    )

    with patch("src.embedding_service.logger") as log:
        service.embed_text("x" * 4000)

    assert not log.warning.called


def test_missing_tokenizer_does_not_break_encoding():
    """Diagnostics must never take down ingestion."""

    service, _ = _service(tokenizer=None)

    assert service.embed_text("some text")


def test_a_broken_tokenizer_does_not_break_encoding():
    class _Exploding:
        def encode(self, *args, **kwargs):
            raise RuntimeError("nope")

    service, _ = _service(tokenizer=_Exploding())

    assert service.embed_text("some text")


# ---------------------------------------------------------------------------
# Step 6: both vector paths for newly-split chunks
# ---------------------------------------------------------------------------


def _split_chunks(n=6):
    """Stand in for what token-aware chunking now produces: more, smaller."""

    from src.schemas import DocumentChunk

    return [
        DocumentChunk(
            document_id="doc_001",
            chunk_id=f"chunk_{index:03d}",
            text=f"البند رقم {index}: نص قانوني للاختبار",
            page=1,
            client_id="client_test",
            matter_id="_none",
            confidentiality_level="internal",
            metadata={"split_from_unit": True},
        )
        for index in range(1, n + 1)
    ]


def test_every_split_chunk_gets_both_vectors():
    service, _ = _service()

    embedded = service.embed_document_chunks(_split_chunks())

    assert len(embedded) == 6
    for item in embedded:
        assert item.embedding
        assert item.sparse_embedding, (
            "a split chunk with no sparse vector is invisible to keyword "
            "search entirely -- worse than the truncation being fixed"
        )


def test_split_chunks_are_encoded_in_one_batch():
    """
    Splitting multiplies chunk count by roughly two. Encoding them one at a
    time would multiply ingest latency by the same factor.
    """

    service, fake = _service()

    service.embed_document_chunks(_split_chunks(6))

    assert len(fake.calls) == 1
    assert len(fake.calls[0]["texts"]) == 6


def test_sparse_weights_stay_paired_with_their_own_chunk():
    """
    More chunks means more chances to mis-pair. The fake gives each text a
    distinct token id so a positional slip is visible.
    """

    service, _ = _service()

    embedded = service.embed_document_chunks(_split_chunks(6))

    for index, item in enumerate(embedded):
        assert str(1000 + index) in item.sparse_embedding


def test_acl_survives_splitting():
    """Splitting must not drop the stamp the ACL work put on every chunk."""

    service, _ = _service()

    for item in service.embed_document_chunks(_split_chunks()):
        assert item.client_id == "client_test"
        assert item.matter_id == "_none"
        assert item.confidentiality_level == "internal"


def test_split_chunks_reach_qdrant_with_both_vectors():
    """End to end through the real indexing path into real Qdrant."""

    from qdrant_client.http import models as qmodels

    from src.indexing import DocumentIndexingService
    from src.vector_store.qdrant_manager import (
        DENSE_VECTOR_NAME,
        SPARSE_VECTOR_NAME,
        QdrantVectorStore,
        to_sparse_vector,
    )
    from tests.access_helpers import access_scope

    class _Embedder:
        model_name = "fake-bge-m3"
        dimension = 3

        def embed_document_chunks(self, chunks):
            service, _ = _service()
            return service.embed_document_chunks(chunks)

    store = QdrantVectorStore(
        location=":memory:",
        collection_name="token_split_roundtrip",
        vector_size=3,
    )

    service = DocumentIndexingService(
        embedding_service=_Embedder(),
        vector_store=store,
    )

    result = service.index_document(_split_chunks(6))

    assert result.chunks_indexed == 6

    query_filter = store.build_qdrant_filter(access=access_scope())

    dense_hits = store.dense_search(
        query_vector=[0.1, 0.2, 0.3],
        query_filter=query_filter,
    )
    assert len(dense_hits) == 6

    sparse_hits = store.sparse_search(
        query_sparse=to_sparse_vector({"1000": 1.0}),
        query_filter=query_filter,
    )
    assert sparse_hits, "split chunks are missing from the sparse index"
