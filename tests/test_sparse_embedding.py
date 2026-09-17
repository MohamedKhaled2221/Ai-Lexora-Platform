"""
Step 1 coverage: BGE-M3 sparse output.

The real model needs torch and cannot run here, so every test drives a fake
BGEM3FlagModel that returns FlagEmbedding-shaped output. That pins the part
this change actually owns -- what is asked of the model, and how its output
is converted -- while leaving "does BGE-M3 behave as documented" to be
confirmed on a machine that has the weights.

The fake deliberately returns the awkward types FlagEmbedding really returns:
a defaultdict keyed by *string* token ids, holding numpy float32 weights.
"""

from collections import defaultdict
from unittest.mock import patch

import numpy as np
import pytest

from src.embedding_service import (
    EmbeddingService,
    normalize_lexical_weights,
)


class _FakeBGEM3:
    """Records how it was called and returns FlagEmbedding-shaped output."""

    def __init__(self, *args, sparse_payload="default", **kwargs):
        self.calls = []
        self.sparse_payload = sparse_payload

    def encode(self, texts, **kwargs):
        self.calls.append({"texts": list(texts), **kwargs})

        result = {
            "dense_vecs": [
                np.array([0.1, 0.2, 0.3], dtype=np.float32)
                for _ in texts
            ]
        }

        if kwargs.get("return_sparse"):
            if self.sparse_payload == "default":
                result["lexical_weights"] = [
                    defaultdict(
                        int,
                        {
                            "1045": np.float32(0.31),
                            "7890": np.float32(0.12),
                        },
                    )
                    for _ in texts
                ]
            elif self.sparse_payload == "missing":
                pass
            elif self.sparse_payload == "mismatched":
                result["lexical_weights"] = [
                    defaultdict(int, {"1": np.float32(0.5)})
                ]
            else:
                result["lexical_weights"] = self.sparse_payload

        return result


def _service(**kwargs):
    fake = _FakeBGEM3(sparse_payload=kwargs.pop("sparse_payload", "default"))

    # The fake emits 3-dimensional vectors. M2's hardened service validates
    # every vector against expected_dimension (default 1024), so the fake's
    # width has to be declared or every encode fails the contract check.
    kwargs.setdefault("expected_dimension", 3)
    kwargs.setdefault("device", "cpu")

    with patch(
        "src.embedding_service.BGEM3FlagModel",
        return_value=fake,
    ):
        service = EmbeddingService(**kwargs)

    return service, fake


# ---------------------------------------------------------------------------
# normalize_lexical_weights
# ---------------------------------------------------------------------------


def test_numpy_types_are_normalized_to_json_safe_python_types():
    """
    FlagEmbedding returns numpy floats and a defaultdict. Neither survives a
    Pydantic round-trip or a JSON boundary cleanly.
    """

    raw = defaultdict(
        int,
        {"1045": np.float32(0.25), "12": np.float64(0.5)},
    )

    result = normalize_lexical_weights(raw)

    assert result == {"1045": 0.25, "12": 0.5}
    assert type(result) is dict
    for key, value in result.items():
        assert type(key) is str
        assert type(value) is float


def test_integer_token_ids_are_accepted_and_stringified():
    """FlagEmbedding is not consistent about key type across versions."""

    assert normalize_lexical_weights({1045: 0.25}) == {"1045": 0.25}
    assert normalize_lexical_weights({np.int64(7): 0.5}) == {"7": 0.5}


def test_zero_and_negative_weights_are_dropped():
    """
    A zero-weight term contributes nothing to a sparse dot product but still
    costs index space in every stored vector.
    """

    result = normalize_lexical_weights(
        {"1": 0.5, "2": 0.0, "3": -0.1}
    )

    assert result == {"1": 0.5}


def test_empty_weights_normalize_to_an_empty_dict():
    assert normalize_lexical_weights({}) == {}


# ---------------------------------------------------------------------------
# What the model is asked for
# ---------------------------------------------------------------------------


def test_encode_requests_dense_and_sparse_explicitly():
    service, fake = _service()

    service.embed_text("termination clause")

    call = fake.calls[-1]

    assert call["return_dense"] is True
    assert call["return_sparse"] is True


def test_sparse_can_be_switched_off():
    """The escape hatch: behave exactly as before the sparse work."""

    service, fake = _service(return_sparse=False)

    service.embed_text("termination clause")

    assert fake.calls[-1]["return_sparse"] is False


def test_dense_only_service_produces_no_sparse():
    service, _ = _service(return_sparse=False)

    encoded = service._encode(["a", "b"])

    assert encoded.sparse is None
    assert encoded.sparse_at(0) is None
    assert len(encoded.dense) == 2


# ---------------------------------------------------------------------------
# Query path
# ---------------------------------------------------------------------------


def test_processed_query_sparse_embedding_is_populated():
    """
    The field has been declared since the original M2 contract and was never
    filled, so M3 had no sparse query vector even though the model computed
    one on every call.
    """

    from src.schemas import ProcessedQuery

    service, _ = _service()

    query = ProcessedQuery(
        query_id="q_001",
        text_original="ما هي شروط الفسخ؟",
        normalized_text="ما هي شروط الفسخ",
    )

    embedded = service.embed_processed_query(query)

    assert embedded.processed_query.sparse_embedding == {
        "1045": pytest.approx(0.31),
        "7890": pytest.approx(0.12),
    }
    assert embedded.sparse_embedding == (
        embedded.processed_query.sparse_embedding
    )
    assert embedded.processed_query.embedding == (
        embedded.embedding
    )

    assert len(
        embedded.processed_query.embedding
    ) == embedded.dimension


def test_query_is_encoded_once_not_twice():
    """
    Dense and sparse come from the same forward pass. Encoding the query
    twice would double query latency for a signal the first pass already
    produced.
    """

    from src.schemas import ProcessedQuery

    service, fake = _service()

    service.embed_processed_query(
        ProcessedQuery(
            query_id="q_001",
            text_original="x",
            normalized_text="normalized form",
        )
    )

    assert len(fake.calls) == 1
    assert fake.calls[0]["texts"] == ["normalized form"]


def test_empty_normalized_text_is_now_refused_by_the_schema():
    """M2 moved this invariant out of M3's reach.

    This test used to feed ``normalized_text=""`` and assert that
    embed_processed_query fell back to ``text_original``. ProcessedQuery now
    declares ``min_length=1`` and rejects whitespace-only text, so that input
    can no longer be constructed and the fallback branch is unreachable by
    contract. The guarantee still holds -- it is just enforced a layer up.
    """
    import pytest as _pytest
    from pydantic import ValidationError

    from src.schemas import ProcessedQuery

    with _pytest.raises(ValidationError):
        ProcessedQuery(
            query_id="q_001",
            text_original="raw question",
            normalized_text="",
        )

def test_document_chunks_carry_sparse_weights():
    from src.schemas import DocumentChunk

    service, _ = _service()

    chunks = [
        DocumentChunk(
            document_id="doc_001",
            chunk_id=f"chunk_{index:03d}",
            text=f"clause text {index}",
            page=1,
            client_id="client_042",
            matter_id="_none",
            confidentiality_level="internal",
        )
        for index in range(1, 4)
    ]

    embedded = service.embed_document_chunks(chunks)

    assert len(embedded) == 3
    for item in embedded:
        assert item.sparse_embedding == {
            "1045": pytest.approx(0.31),
            "7890": pytest.approx(0.12),
        }


def test_sparse_is_paired_with_the_right_chunk_by_position():
    from src.schemas import DocumentChunk

    per_text = [
        defaultdict(int, {"1": np.float32(0.1)}),
        defaultdict(int, {"2": np.float32(0.2)}),
    ]

    service, _ = _service(sparse_payload=per_text)

    chunks = [
        DocumentChunk(
            document_id="doc_001",
            chunk_id=f"chunk_{index}",
            text=f"text {index}",
            page=1,
        )
        for index in (1, 2)
    ]

    embedded = service.embed_document_chunks(chunks)

    assert embedded[0].sparse_embedding == {"1": pytest.approx(0.1)}
    assert embedded[1].sparse_embedding == {"2": pytest.approx(0.2)}


def test_single_chunk_helper_carries_sparse_too():
    service, _ = _service()

    embedded = service.embed_document_chunk(
        document_id="doc_001",
        chunk_id="chunk_001",
        text="clause text",
    )

    assert embedded.sparse_embedding


# ---------------------------------------------------------------------------
# Degrading rather than failing
# ---------------------------------------------------------------------------


def test_missing_lexical_weights_degrades_to_dense_only(caplog):
    """
    Sparse is a secondary signal. If the model does not return it, retrieval
    still works dense-only, so this warns rather than taking down ingestion
    and search.
    """

    import logging

    service, _ = _service(sparse_payload="missing")

    with caplog.at_level(logging.WARNING, logger="src.embedding_service"):
        encoded = service._encode(["a"])

    assert encoded.dense
    assert encoded.sparse is None
    assert any(
        "lexical_weights" in record.message for record in caplog.records
    )


def test_length_mismatch_is_refused_rather_than_mispaired():
    """
    Pairing sparse to dense by position is only safe if the lengths match.
    A silent zip() would attach one chunk's keywords to another's text.
    """

    from src.embedding_service import EmbeddingContractError

    service, _ = _service(sparse_payload="mismatched")

    with pytest.raises(EmbeddingContractError, match="refusing to pair"):
        service._encode(["a", "b"])


def test_dense_only_encode_helper_still_works():
    """The dense half of a merged encode is unchanged.

    ``_encode`` returns an EncodedTexts rather than a bare list since M2's
    hardening merged the dense-only helper into it, and normalization is now
    on by default -- disabled here so the fake's raw values are observable.
    """
    service, _ = _service(normalize_embeddings=False)

    assert service._encode(["a", "b"]).dense == [
        [pytest.approx(0.1), pytest.approx(0.2), pytest.approx(0.3)]
    ] * 2

def test_dimension_is_still_detected():
    service, _ = _service()

    service.embed_text("x")

    assert service.dimension == 3
