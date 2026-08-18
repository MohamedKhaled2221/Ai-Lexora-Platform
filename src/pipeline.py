import time
import logging
from typing import Optional, Tuple

from src.schemas.m2_contract import ProcessedQuery
from src.schemas.m4_contract import RetrievedEvidence, EvidenceItem
from src.vector_store.qdrant_manager import QdrantVectorStore
from src.retrieval.hybrid_search import HybridSearcher
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
    ):
        self.vector_store = vector_store or QdrantVectorStore()
        self.candidate_top_k = candidate_top_k
        self.final_top_k = final_top_k

        self.hybrid_searcher = HybridSearcher(
            vector_store=self.vector_store,
            rrf_k=60
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
