import sentence_transformers

from src.retrieval.reranker import (
    BGEReranker,
)


def test_reranker_uses_local_files_only(
    monkeypatch,
):
    captured = {}

    class FakeCrossEncoder:
        def __init__(
            self,
            model_name,
            **kwargs,
        ):
            captured["model_name"] = (
                model_name
            )

            captured.update(
                kwargs
            )

    monkeypatch.setattr(
        sentence_transformers,
        "CrossEncoder",
        FakeCrossEncoder,
    )

    BGEReranker(
        model_name=(
            "BAAI/bge-reranker-v2-m3"
        ),
        use_mock_fallback=False,
        local_files_only=True,
    )

    assert (
        captured["model_name"]
        == "BAAI/bge-reranker-v2-m3"
    )

    assert (
        captured["local_files_only"]
        is True
    )
