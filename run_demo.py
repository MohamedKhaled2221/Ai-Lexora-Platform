import json
import logging
from src.vector_store.qdrant_manager import QdrantVectorStore
from src.pipeline import M3RetrievalPipeline
from src.utils.mock_data import (
    generate_mock_legal_chunks,
    prepare_qdrant_points,
    generate_mock_processed_query
)
from src.evaluation.metrics import RetrievalEvaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def main():
    print("=" * 70)
    print("AI-Lexora: Module M3 (RAG Vector Search & Reranking Engine) Demo")
    print("Stack: Qdrant DB | BM25 RRF Hybrid Search | BGE-Reranker-v2-M3")
    print("=" * 70)

    # 1. Initialize In-Memory Qdrant Store
    print("\n[Step 1] Initializing Qdrant Collection & Indexing Metadata...")
    vector_store = QdrantVectorStore(
        location=":memory:",
        collection_name="legal_documents",
        vector_size=1024
    )

    # 2. Seed Mock Legal Documents (Arabic & English)
    # In production, embeddings come from M2 (upstream module)
    chunks = generate_mock_legal_chunks()
    points = prepare_qdrant_points(chunks, vector_size=1024)
    vector_store.upsert_chunks(points)

    # 3. Instantiate M3 Pipeline
    print("\n[Step 2] Building M3 Retrieval Pipeline...")
    pipeline = M3RetrievalPipeline(
        vector_store=vector_store,
        candidate_top_k=10,
        final_top_k=3,
        reranker_model_name="BAAI/bge-reranker-v2-m3",
        use_mock_fallback=True
    )

    # 4. Simulate M2 Upstream Input (ProcessedQuery with embedding pre-computed by M2)
    query_ar = generate_mock_processed_query(
        query_id="q_001",
        query_text="ما هي شروط الفسخ؟",
        doc_type="contract",
        jurisdiction="Egypt",
        lang="ar",
        seed=101
    )

    print("\n[Step 3] Received ProcessedQuery from M2:")
    query_dict = query_ar.model_dump()
    query_dict["embedding"] = f"<Dense Vector float[{len(query_ar.embedding)}] — provided by M2>"
    print(json.dumps(query_dict, indent=2, ensure_ascii=False))

    # 5. Run M3 Pipeline
    print("\n[Step 4] Executing Hybrid Search (Dense + BM25 RRF) + BGE Reranker...")
    evidence_output, latency_ms = pipeline.run(query_ar)

    # 6. Print Downstream M4 Output (RetrievedEvidence)
    print("\n[Step 5] Delivered RetrievedEvidence to M4:")
    print(json.dumps(evidence_output.model_dump(), indent=2, ensure_ascii=False))

    # 7. Evaluate Metrics
    retrieved_chunk_ids = [item.chunk_id for item in evidence_output.retrieved_evidence]
    ground_truth = {"chunk_017", "chunk_005"}
    metrics = RetrievalEvaluator.evaluate_query(
        retrieved_chunk_ids=retrieved_chunk_ids,
        ground_truth_chunk_ids=ground_truth,
        latency_ms=latency_ms
    )

    print("\n[Step 6] Evaluation Benchmark Metrics:")
    for metric_name, val in metrics.items():
        if "latency" in metric_name:
            print(f"  • {metric_name}: {val:.2f} ms")
        else:
            print(f"  • {metric_name}: {val * 100:.1f}%")

    print("\n" + "=" * 70)
    print("M3 Pipeline Execution Completed Successfully!")
    print("=" * 70)


if __name__ == "__main__":
    main()
