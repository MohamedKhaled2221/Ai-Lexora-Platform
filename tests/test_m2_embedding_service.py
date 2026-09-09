import math

import numpy as np
import pytest

import src.embedding_service as embedding_module
from src.embedding_service import (
    EmbeddingContractError,
    EmbeddingModelLoadError,
    EmbeddingRuntimeError,
    EmbeddingService,
)
from src.schemas.m2_contract import (
    ProcessedQuery,
)


class FakeModel:
    def __init__(
        self,
        *,
        vectors=None,
        error: Exception | None = None,
    ):
        self.vectors = vectors
        self.error = error

        self.last_texts = None
        self.last_kwargs = None

    def encode(
        self,
        texts,
        **kwargs,
    ):
        self.last_texts = list(
            texts
        )

        self.last_kwargs = kwargs

        if self.error is not None:
            raise self.error

        vectors = self.vectors

        if vectors is None:
            vectors = [
                [
                    3.0,
                    4.0,
                    0.0,
                ]
                for _ in texts
            ]

        return {
            "dense_vecs": np.asarray(
                vectors,
                dtype=float,
            )
        }


def make_service(
    *,
    model=None,
    normalize_embeddings=True,
    expected_dimension=3,
):
    return EmbeddingService(
        model_name="fake-bge-m3",
        use_fp16=False,
        batch_size=4,
        max_length=128,
        normalize_embeddings=(
            normalize_embeddings
        ),
        expected_dimension=(
            expected_dimension
        ),
        device="cpu",
        model=(
            model
            or FakeModel()
        ),
    )


def test_embed_text_returns_expected_dimension():
    service = make_service()

    vector = service.embed_text(
        "legal query"
    )

    assert len(vector) == 3
    assert service.dimension == 3


def test_embeddings_are_l2_normalized_when_enabled():
    service = make_service()

    vector = service.embed_text(
        "legal query"
    )

    assert vector == pytest.approx(
        [
            0.6,
            0.8,
            0.0,
        ]
    )

    norm = math.sqrt(
        sum(
            value * value
            for value in vector
        )
    )

    assert norm == pytest.approx(
        1.0
    )


def test_normalization_can_be_disabled():
    service = make_service(
        normalize_embeddings=False
    )

    vector = service.embed_text(
        "legal query"
    )

    assert vector == [
        3.0,
        4.0,
        0.0,
    ]


def test_encode_names_its_requested_outputs_explicitly():
    """Every output flag is passed explicitly, none left to library defaults.

    This test previously asserted ``return_sparse is False``. M3 now consumes
    BGE-M3's lexical weights for hybrid retrieval, so sparse follows the
    ``return_sparse`` setting rather than being hardcoded off; ColBERT stays
    off because nothing consumes it. What still matters -- and is what this
    test guards -- is that the call names what it wants, so a future
    FlagEmbedding whose defaults shift cannot quietly change M2's output.
    """
    model = FakeModel()

    service = make_service(
        model=model
    )

    service.embed_text(
        "legal query"
    )

    assert (
        model.last_kwargs[
            "return_dense"
        ]
        is True
    )

    assert (
        model.last_kwargs[
            "return_sparse"
        ]
        is service.return_sparse
    )

    assert (
        model.last_kwargs[
            "return_colbert_vecs"
        ]
        is False
    )


def test_batch_and_max_length_are_forwarded():
    model = FakeModel()

    service = make_service(
        model=model
    )

    service.embed_text(
        "legal query"
    )

    assert (
        model.last_kwargs[
            "batch_size"
        ]
        == 4
    )

    assert (
        model.last_kwargs[
            "max_length"
        ]
        == 128
    )


def test_batch_output_count_must_match_input_count():
    model = FakeModel(
        vectors=[
            [
                1.0,
                0.0,
                0.0,
            ]
        ]
    )

    service = make_service(
        model=model
    )

    with pytest.raises(
        EmbeddingContractError,
        match="different number",
    ):
        service.embed_documents(
            [
                "first",
                "second",
            ]
        )


def test_wrong_dimension_is_rejected():
    model = FakeModel(
        vectors=[
            [
                1.0,
                0.0,
            ]
        ]
    )

    service = make_service(
        model=model,
        expected_dimension=3,
    )

    with pytest.raises(
        EmbeddingContractError,
        match="dimension",
    ):
        service.embed_text(
            "legal query"
        )


@pytest.mark.parametrize(
    "bad_value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_non_finite_embedding_values_are_rejected(
    bad_value,
):
    model = FakeModel(
        vectors=[
            [
                1.0,
                bad_value,
                0.0,
            ]
        ]
    )

    service = make_service(
        model=model
    )

    with pytest.raises(
        EmbeddingContractError,
        match="NaN or infinite",
    ):
        service.embed_text(
            "legal query"
        )


def test_zero_vector_is_rejected_when_normalizing():
    model = FakeModel(
        vectors=[
            [
                0.0,
                0.0,
                0.0,
            ]
        ]
    )

    service = make_service(
        model=model
    )

    with pytest.raises(
        EmbeddingContractError,
        match="zero or invalid",
    ):
        service.embed_text(
            "legal query"
        )


def test_model_runtime_failure_is_wrapped():
    model = FakeModel(
        error=RuntimeError(
            "fake CUDA failure"
        )
    )

    service = make_service(
        model=model
    )

    with pytest.raises(
        EmbeddingRuntimeError,
        match="inference failed",
    ):
        service.embed_text(
            "legal query"
        )


def test_empty_batch_is_rejected_before_model_call():
    service = make_service()

    with pytest.raises(
        ValueError,
        match="must not be empty",
    ):
        service.embed_documents(
            []
        )


def test_blank_text_is_rejected_before_model_call():
    service = make_service()

    with pytest.raises(
        ValueError,
        match="empty strings",
    ):
        service.embed_documents(
            [
                "valid",
                "   ",
            ]
        )


def test_last_metrics_are_recorded():
    service = make_service()

    service.embed_documents(
        [
            "first",
            "second",
        ]
    )

    metrics = service.last_metrics

    assert metrics is not None

    assert metrics.text_count == 2
    assert metrics.dimension == 3
    assert metrics.device == "cpu"

    assert metrics.latency_ms >= 0.0

    assert (
        metrics.rss_before_mib
        >= 0.0
    )

    assert (
        metrics.rss_after_mib
        >= 0.0
    )

    assert (
        metrics.cuda_peak_allocated_mib
        is None
    )


def test_runtime_metadata_contains_model_configuration():
    service = make_service()

    metadata = (
        service.runtime_metadata
    )

    assert (
        metadata["model_name"]
        == "fake-bge-m3"
    )

    assert (
        metadata[
            "expected_dimension"
        ]
        == 3
    )

    assert (
        metadata["device"]
        == "cpu"
    )

    assert (
        metadata[
            "normalize_embeddings"
        ]
        is True
    )

    assert (
        "flagembedding_version"
        in metadata
    )

    assert (
        "torch_version"
        in metadata
    )


def test_embed_processed_query_uses_normalized_text():
    model = FakeModel()

    service = make_service(
        model=model
    )

    query = ProcessedQuery(
        query_id="q_test",
        text_original=(
            "  ما حكم إنهاء العقد؟ "
        ),
        normalized_text=(
            "ما حكم انهاء العقد؟"
        ),
        language="ar",
    )

    result = (
        service
        .embed_processed_query(
            query
        )
    )

    assert model.last_texts == [
        "ما حكم انهاء العقد؟"
    ]

    assert result.model == (
        "fake-bge-m3"
    )

    assert result.dimension == 3
    assert len(result.embedding) == 3


def test_auto_device_uses_cpu_when_cuda_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(
        embedding_module.torch.cuda,
        "is_available",
        lambda: False,
    )

    captured = {}

    def fake_loader(
        model_name,
        **kwargs,
    ):
        captured[
            "model_name"
        ] = model_name

        captured.update(
            kwargs
        )

        return FakeModel()

    monkeypatch.setattr(
        embedding_module,
        "BGEM3FlagModel",
        fake_loader,
    )

    service = EmbeddingService(
        model_name="fake-model",
        use_fp16=True,
        expected_dimension=3,
        device="auto",
    )

    assert service.device == "cpu"

    assert (
        service.use_fp16
        is False
    )

    assert captured[
        "devices"
    ] == ["cpu"]

    assert (
        captured["use_fp16"]
        is False
    )


def test_explicit_cuda_is_rejected_when_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(
        embedding_module.torch.cuda,
        "is_available",
        lambda: False,
    )

    with pytest.raises(
        EmbeddingModelLoadError,
        match="CUDA",
    ):
        EmbeddingService(
            model_name="fake-model",
            device="cuda:0",
            expected_dimension=3,
            model=FakeModel(),
        )
def test_cuda_peak_metric_failure_does_not_break_embedding(
    monkeypatch,
):
    model = FakeModel()

    service = make_service(
        model=model
    )

    service.device = "cuda:0"

    monkeypatch.setattr(
        embedding_module.torch.cuda,
        "reset_peak_memory_stats",
        lambda device: (
            (_ for _ in ())
            .throw(
                RuntimeError(
                    "Invalid device argument"
                )
            )
        ),
    )

    monkeypatch.setattr(
        embedding_module.torch.cuda,
        "synchronize",
        lambda device: None,
    )

    vector = service.embed_text(
        "legal query"
    )

    assert len(vector) == 3

    assert (
        service.last_metrics
        is not None
    )

    assert (
        service.last_metrics
        .cuda_peak_allocated_mib
        is None
    )