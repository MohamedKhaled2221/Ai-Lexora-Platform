"""
The reranker must fail loudly, in a typed way, or not at all.

``reranker_use_mock_fallback=False`` exists to guarantee one property: the
system never serves heuristic relevance scores while presenting them as
cross-encoder output. These tests pin that property against the two ways it
was previously violable, plus the diagnosability requirement that made the
first violation hard to recognise in production.

These tests do not require the model to be present, and deliberately do not
download it -- whether ``bge-reranker-v2-m3`` may be fetched onto firm
infrastructure is a policy decision, not a test fixture.
"""

from __future__ import annotations

import pytest

from src.retrieval.reranker import BGEReranker, RerankerUnavailable


CANDIDATES = [
    {"text": "المادة 15 الإضراب السلمي حق", "chunk_id": "c1", "rrf_score": 0.1},
    {"text": "Article 51 human dignity", "chunk_id": "c2", "rrf_score": 0.2},
]

MISSING_MODEL = "definitely-not-a-real-model/for-testing-only"


def test_missing_model_raises_typed_error_not_bare_oserror():
    """
    The loader's own OSError must not escape.

    Its message says "Check your internet connection", which on an air-gapped
    host describes policy rather than a fault and sends an operator to
    diagnose the wrong thing entirely.
    """
    with pytest.raises(RerankerUnavailable) as excinfo:
        BGEReranker(
            model_name=MISSING_MODEL,
            use_mock_fallback=False,
            local_files_only=True,
        )

    message = str(excinfo.value)
    assert MISSING_MODEL in message
    assert "use_mock_fallback" in message, "must say how to opt into degrading"


def test_original_exception_is_preserved_as_cause():
    """Typing the error must not discard what actually failed."""
    with pytest.raises(RerankerUnavailable) as excinfo:
        BGEReranker(
            model_name=MISSING_MODEL,
            use_mock_fallback=False,
            local_files_only=True,
        )

    assert excinfo.value.__cause__ is not None


def test_not_an_oserror_subclass():
    """
    A caller catching OSError for sockets and disks must not silently absorb
    "the reranker is missing" as though it were a transient I/O problem.
    """
    assert not issubclass(RerankerUnavailable, OSError)
    assert issubclass(RerankerUnavailable, RuntimeError)


def test_empty_model_name_does_not_bypass_the_no_fallback_guarantee():
    """
    The regression this file exists for.

    An empty model name used to return early from _init_model unconditionally,
    leaving model=None. rerank() then routed every request through the
    heuristic scorer -- so the flag that forbids silent degradation was
    defeated by the one configuration that degrades with no error at all.
    """
    with pytest.raises(RerankerUnavailable):
        BGEReranker(model_name="", use_mock_fallback=False)


def test_rerank_refuses_to_serve_heuristic_scores_when_forbidden():
    """
    Defence in depth at the point where scores would reach a caller.

    Constructed by bypassing __init__ so that a future code path which builds
    a reranker some other way still cannot serve degraded scores under a
    configuration that forbids them.
    """
    reranker = BGEReranker.__new__(BGEReranker)
    reranker.model_name = MISSING_MODEL
    reranker.use_mock_fallback = False
    reranker.local_files_only = True
    reranker.model = None

    with pytest.raises(RerankerUnavailable):
        reranker.rerank("المادة 15", CANDIDATES, top_k=2)


def test_empty_candidates_short_circuit_before_the_guard():
    """An empty result set is a legitimate outcome, not a reranker failure."""
    reranker = BGEReranker.__new__(BGEReranker)
    reranker.model_name = MISSING_MODEL
    reranker.use_mock_fallback = False
    reranker.local_files_only = True
    reranker.model = None

    assert reranker.rerank("anything", [], top_k=5) == []


# --------------------------------------------------------------- opt-in path


def test_explicit_fallback_still_degrades_on_purpose():
    """
    use_mock_fallback=True is an explicit, logged choice and must keep working.

    This is the escape hatch for development and for the evaluation harness;
    the fix must not have turned it into an error.
    """
    reranker = BGEReranker(
        model_name=MISSING_MODEL,
        use_mock_fallback=True,
        local_files_only=True,
    )

    assert reranker.model is None

    scored = reranker.rerank("المادة 15", CANDIDATES, top_k=2)

    assert len(scored) == 2
    assert all(0.0 <= row["score"] <= 0.99 for row in scored)


def test_empty_model_name_with_fallback_enabled_is_allowed():
    reranker = BGEReranker(model_name="", use_mock_fallback=True)
    assert reranker.model is None
    assert reranker.rerank("q", CANDIDATES, top_k=1)


def test_production_default_forbids_fallback():
    """
    Pin the default itself. If this flips, everything above becomes decorative.
    """
    from src.api.runtime import RAGRuntimeSettings

    assert RAGRuntimeSettings().reranker_use_mock_fallback is False
