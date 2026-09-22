import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class RerankerUnavailable(RuntimeError):
    """
    The cross-encoder could not be loaded and degrading was not permitted.

    Raised instead of letting the underlying loader error escape. The loader
    raises a bare ``OSError`` whose message reads "We couldn't connect to
    'https://huggingface.co' ... Check your internet connection" -- which on a
    deliberately air-gapped host sends the operator to diagnose a network fault
    that is *policy*, not a fault. The real cause is that the model is not in
    the local cache, and the real fix is to place it there.

    It is also a distinct type so a caller can catch *this* and surface
    "reranking unavailable" without also swallowing every unrelated ``OSError``
    (a closed socket, a full disk) that the same ``except`` clause would
    otherwise absorb.

    ``__cause__`` carries the original exception, so nothing is lost.
    """


def _unavailable_message(model_name: str, reason: str) -> str:
    return (
        f"Cross-encoder reranker {model_name!r} is unavailable: {reason}. "
        "The pipeline is configured with use_mock_fallback=False, so it "
        "refuses to fall back to the heuristic reranker and serve degraded "
        "relevance silently. Either place the model in the local Hugging Face "
        "cache, or set reranker_use_mock_fallback=True to accept heuristic "
        "reranking explicitly."
    )


class BGEReranker:
    """
    BGE-M3 Cross-Encoder Reranker Engine.
    Re-scores candidate chunks retrieved from Hybrid Search to deliver precise evidence ranking.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        # Fail loud by default. Heuristic reranking is an explicit opt-in, so a
        # caller that forgets the flag gets an error, not degraded scores.
        use_mock_fallback: bool = False,
        local_files_only: bool = True,
    ):
        self.model_name = model_name
        self.use_mock_fallback = use_mock_fallback
        self.local_files_only = local_files_only
        self.model = None

        self._init_model()

    def _init_model(self) -> None:
        """
        Load the BGE CrossEncoder model. If it is unavailable, raise
        RerankerUnavailable unless use_mock_fallback explicitly allows the
        heuristic reranker.
        """
        if not self.model_name:
            # Previously this returned unconditionally, which quietly defeated
            # use_mock_fallback=False: an empty model name produced a reranker
            # with self.model = None, and rerank() then routed every request
            # through the heuristic path. The flag that exists precisely to
            # forbid silent degradation did not cover the one configuration
            # that degrades without any error at all.
            if not self.use_mock_fallback:
                raise RerankerUnavailable(
                    _unavailable_message(
                        self.model_name,
                        "no model name was configured",
                    )
                )

            logger.info("No HuggingFace model specified. Using fast heuristic/mock reranker.")
            return

        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading CrossEncoder reranker model: {self.model_name}...")
            self.model = CrossEncoder(
                self.model_name,
                local_files_only=self.local_files_only,
            )
        except Exception as e:
            logger.warning(f"Could not load HuggingFace CrossEncoder '{self.model_name}': {e}.")
            if self.use_mock_fallback:
                logger.info("Enabling intelligent heuristic/mock reranker fallback.")
            else:
                # Re-raised as a typed error rather than propagating the
                # loader's own exception. `from e` keeps the original as
                # __cause__, so the traceback still shows what actually failed.
                raise RerankerUnavailable(
                    _unavailable_message(self.model_name, str(e).strip())
                ) from e

    def rerank(
        self,
        query_text: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Rerank list of candidate chunks against the query.
        Returns top_k items with updated 'score' attribute.
        """
        if not candidates:
            return []

        if self.model is None and not self.use_mock_fallback:
            # Unreachable via __init__, which now refuses to construct such an
            # instance. Repeated here because this is the point where degraded
            # scores would actually reach a caller: any future path that builds
            # a reranker another way (a test double, a partially-initialized
            # object, a subclass overriding _init_model) must not be able to
            # serve heuristic scores under a configuration that forbids them.
            raise RerankerUnavailable(
                _unavailable_message(
                    self.model_name,
                    "no cross-encoder was loaded",
                )
            )

        if self.model is not None:
            pairs = [
                [query_text, self._rerank_document_text(candidate)]
                for candidate in candidates
            ]
            raw_scores = self.model.predict(pairs)

            # Normalize scores using sigmoid for 0.0 - 1.0 output range
            import numpy as np
            scores = 1.0 / (1.0 + np.exp(-np.array(raw_scores)))

            reranked = []
            for idx, item in enumerate(candidates):
                item_copy = dict(item)
                item_copy["score"] = float(scores[idx])
                reranked.append(item_copy)
        else:
            # Smart Fallback Reranking: Token overlap & RRF score boost
            reranked = self._fallback_rerank(query_text, candidates)

        # Sort descending by score
        reranked.sort(key=lambda x: x["score"], reverse=True)
        return reranked[:top_k]

    @staticmethod
    def _rerank_document_text(candidate: Dict[str, Any]) -> str:
        """Build trusted title + passage text for relevance scoring."""
        title = str(candidate.get("title") or "").strip()
        text = str(candidate.get("text") or "").strip()

        if not title:
            return text

        return (
            f"Document title: {title}\n"
            f"Document text: {text}"
        )

    def _fallback_rerank(
        self,
        query_text: str,
        candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Heuristic fallback reranking when deep model weights are offline.
        Combines keyword coverage, exact match bonuses, and RRF score.
        """
        query_terms = set(query_text.lower().split())
        reranked = []

        for item in candidates:
            text = self._rerank_document_text(item).lower()
            text_terms = set(text.split())

            if not query_terms:
                overlap_ratio = 0.5
            else:
                overlap = query_terms.intersection(text_terms)
                overlap_ratio = len(overlap) / len(query_terms)

            rrf_base = item.get("rrf_score", 0.1)
            raw_score = 0.5 * rrf_base + 0.5 * overlap_ratio

            # Clamp between 0.0 and 1.0
            final_score = min(max(raw_score, 0.0), 0.99)

            item_copy = dict(item)
            item_copy["score"] = round(final_score, 4)
            reranked.append(item_copy)

        return reranked
