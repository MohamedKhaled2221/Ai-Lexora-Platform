from types import SimpleNamespace

from src.api import package_runtime


class _FakeQueryPipeline:
    def process(
        self,
        _raw_query: str,
    ):
        return SimpleNamespace(
            embedding=[0.0] * 1024
        )


class _FakeHybridSearcher:
    def __init__(
        self,
        **kwargs,
    ) -> None:
        self.__dict__.update(kwargs)


def test_p4_candidate_pool_override_does_not_mutate_base(
    monkeypatch,
):
    monkeypatch.setattr(
        package_runtime,
        "HybridSearcher",
        _FakeHybridSearcher,
    )

    monkeypatch.setattr(
        package_runtime,
        "P4M4Orchestrator",
        lambda: object(),
    )

    reranker = object()

    base_retrieval = SimpleNamespace(
        candidate_top_k=20,
        final_top_k=5,
        vector_store=object(),
        keyword_backend="sparse",
        reranker=reranker,
        hybrid_searcher=SimpleNamespace(
            rrf_k=60,
            dense_weight=0.9,
            keyword_weight=0.1,
            identifier_weight=1.0,
            min_dense_score=None,
        ),
    )

    rag_service = SimpleNamespace(
        retrieval_pipeline=base_retrieval
    )

    raw_rag_service = SimpleNamespace(
        query_pipeline=_FakeQueryPipeline()
    )

    p4_service = (
        package_runtime.build_p4_chat_service(
            rag_service,
            raw_rag_service,
        )
    )

    assert (
        base_retrieval.candidate_top_k
        == 20
    )

    assert (
        p4_service.retrieval_pipeline
        is not base_retrieval
    )

    assert (
        p4_service
        .retrieval_pipeline
        .candidate_top_k
        == 5
    )

    assert (
        p4_service
        .retrieval_pipeline
        .final_top_k
        == 5
    )

    assert (
        p4_service
        .retrieval_pipeline
        .reranker
        is reranker
    )
