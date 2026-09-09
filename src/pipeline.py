import time
import logging
from typing import Optional, Tuple

from src.schemas.access_control import (
    AccessScope,
    AccessScopeRequired,
    AccessScopeViolation,
)
from src.schemas.m2_contract import ProcessedQuery
from src.schemas.m4_contract import RetrievedEvidence, EvidenceItem
from src.vector_store.qdrant_manager import QdrantVectorStore
from src.retrieval.hybrid_search import (
    HybridSearcher,
    KeywordBackend,
)
from src.retrieval.reranker import BGEReranker

logger = logging.getLogger(__name__)


class M3RetrievalPipeline:
    """
    Module 3 (M3) Master Retrieval & Reranking Pipeline.
    Connects M2 (ProcessedQuery with embedding) to M4 (RetrievedEvidence).

    Responsibilities:
    - Qdrant dense vector search
    - BM25 keyword search
    - Reciprocal Rank Fusion (RRF)
    - BGE-M3 CrossEncoder reranking
    - Retrieval evaluation metrics

    NOTE: Embedding generation is M2's responsibility.
          M3 expects query.embedding to be pre-populated.
    """

    def __init__(
        self,
        vector_store: Optional[QdrantVectorStore] = None,
        candidate_top_k: int = 20,
        final_top_k: int = 5,
        reranker_model_name: str = "BAAI/bge-reranker-v2-m3",
        use_mock_fallback: bool = True,
        reranker_local_files_only: bool = True,
        keyword_backend: KeywordBackend = "sparse",
    ):
        self.vector_store = vector_store or QdrantVectorStore()
        self.candidate_top_k = candidate_top_k
        self.final_top_k = final_top_k

        self.keyword_backend = keyword_backend
        """Which keyword retriever this pipeline was built with.

        Recorded on the instance so a benchmark run can report which side of
        an A/B it measured without reaching into the searcher."""

        self.hybrid_searcher = HybridSearcher(
            vector_store=self.vector_store,
            rrf_k=60,
            keyword_backend=keyword_backend,
        )
        self.reranker = BGEReranker(
            model_name=reranker_model_name,
            use_mock_fallback=use_mock_fallback,
            local_files_only=reranker_local_files_only,
        )

    def run(self, query: ProcessedQuery) -> Tuple[RetrievedEvidence, float]:
        """
        Execute full M3 Pipeline:
        ProcessedQuery (M2) -> Hybrid Search -> Reranking -> RetrievedEvidence (M4).

        Returns (RetrievedEvidence, execution_latency_ms)
        """
        start_time = time.perf_counter()

        logger.info(f"Executing M3 Pipeline for Query ID: '{query.query_id}'...")

        # Step 1: Hybrid Search (Dense + Keyword BM25 with RRF + Metadata Filter)
        candidates = self.hybrid_searcher.search(
            query=query,
            candidate_top_k=self.candidate_top_k
        )

        # Step 2: BGE Rerank top candidates
        query_text_for_reranker = query.normalized_text or query.text_original
        reranked_chunks = self.reranker.rerank(
            query_text=query_text_for_reranker,
            candidates=candidates,
            top_k=self.final_top_k
        )

        # Step 2b: Verify the filter did what it claimed, before anything
        # leaves the retrieval boundary.
        self._assert_within_scope(
            access=query.filters.access,
            candidates=reranked_chunks,
            query_id=query.query_id,
        )

        # Step 3: Format Output Contract for M4 (RetrievedEvidence)
        evidence_items = []
        for chunk in reranked_chunks:
            evidence_items.append(
                EvidenceItem(
                    document_id=chunk.get("document_id", "doc_unknown"),
                    chunk_id=chunk.get("chunk_id", "chunk_unknown"),
                    text=chunk.get("text", ""),
                    page=chunk.get("page"),
                    section=chunk.get("section"),
                    language=chunk.get("language", query.language),
                    score=chunk.get("score", 0.0)
                )
            )

        output_evidence = RetrievedEvidence(
            query_id=query.query_id,
            retrieved_evidence=evidence_items
        )

        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000.0

        logger.info(
            f"M3 Pipeline completed in {latency_ms:.2f}ms. "
            f"Retrieved {len(evidence_items)} evidence chunks for M4."
        )

        return output_evidence, latency_ms

    def _assert_within_scope(
        self,
        *,
        access: Optional[AccessScope],
        candidates: list,
        query_id: str,
    ) -> None:
        """
        Defence in depth: re-check every surviving candidate against the scope.

        Reaching a violation here means the Qdrant filter did not do its job,
        because the same scope produced both the filter and this check. That
        is a bug in the enforcement layer, so the request fails rather than
        the offending candidate being dropped: a silent drop would turn a
        filtering bug into an invisible one, and the next one might not be
        caught by a check at all.

        This runs *after* reranking rather than before, so it also covers a
        reranker that reordered, merged, or reconstructed candidate dicts.
        """

        if access is None:
            # Unreachable via HybridSearcher, which refuses first. Repeated
            # here so a future caller that assembles candidates by another
            # route cannot skip the check by omitting a scope.
            raise AccessScopeRequired(
                "Retrieval produced candidates with no access scope to "
                "verify them against."
            )

        for candidate in candidates:
            if access.permits(
                client_id=candidate.get("client_id"),
                confidentiality_level=candidate.get(
                    "confidentiality_level"
                ),
                matter_id=candidate.get("matter_id"),
            ):
                continue

            # Deliberately omits the offending text and client id: this is
            # logged and raised on a path where the caller was not entitled
            # to the content, so the diagnostics must not restate it.
            logger.error(
                "acl_post_retrieval_violation",
                extra={
                    "query_id": query_id,
                    "document_id": candidate.get(
                        "document_id",
                        "unknown",
                    ),
                    "chunk_id": candidate.get(
                        "chunk_id",
                        "unknown",
                    ),
                },
            )

            raise AccessScopeViolation(
                "Retrieved evidence fell outside the requesting access "
                "scope. The vector-store filter failed to enforce it, so "
                "the whole result is refused rather than partially served."
            )
