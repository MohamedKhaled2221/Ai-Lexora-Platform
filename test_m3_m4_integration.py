import json
import os

from qdrant_client.http.models import PointStruct

from src.embedding_service import EmbeddingService
from src.schemas import DocumentChunk
from src.vector_store.qdrant_manager import QdrantVectorStore
from src.pipeline import M3RetrievalPipeline
from src.query_processor import QueryProcessor
from src.orchestration.service import M4OrchestrationService


JSON_FILE = "sample_chunks_for_m2.json"


def main():
    if not os.path.exists(JSON_FILE):
        print(f"File {JSON_FILE} not found. Please create it first.")
        return

    with open(JSON_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    chunks = []
    for sample_group in data.get("samples", []):
        for chunk_data in sample_group.get("chunks", []):
            chunk = DocumentChunk.model_validate(chunk_data)
            chunks.append(chunk)

    print(f"M1 chunks loaded: {len(chunks)}")
    if not chunks:
        print("No chunks to embed.")
        return

    print("\n[M2] Initializing EmbeddingService...")
    embedding_service = EmbeddingService()

    print("[M2] Embedding document chunks...")
    embedded_chunks = embedding_service.embed_document_chunks(chunks)
    print(f"[M2] Embeddings generated: {len(embedded_chunks)}")

    print("\n[M3] Initializing Qdrant Vector Store...")
    vector_store = QdrantVectorStore(
        location=":memory:",
        collection_name="legal_documents",
        vector_size=embedding_service.dimension or 1024
    )

    points = []
    for i, (orig_chunk, emb_chunk) in enumerate(zip(chunks, embedded_chunks)):
        payload = {
            "document_id": orig_chunk.document_id,
            "chunk_id": orig_chunk.chunk_id,
            "text": orig_chunk.text,
            "page": orig_chunk.page,
            "section": orig_chunk.section,
            "language": orig_chunk.language,
        }
        if orig_chunk.metadata:
            payload["document_type"] = orig_chunk.metadata.get("document_type")
            payload["jurisdiction"] = orig_chunk.metadata.get("jurisdiction")
            
        points.append(
            PointStruct(
                id=i + 1,
                vector=emb_chunk.embedding,
                payload=payload
            )
        )
    vector_store.upsert_chunks(points)
    print(f"[M3] Inserted {len(points)} chunks into Qdrant.")

    print("[M3] Initializing M3 Retrieval Pipeline...")
    m3_pipeline = M3RetrievalPipeline(
        vector_store=vector_store,
        candidate_top_k=10,
        final_top_k=3,
        reranker_model_name="BAAI/bge-reranker-v2-m3",
        use_mock_fallback=True
    )

    query_text = "ما هي شروط الفسخ؟"
    print(f"\n[Query] Processing Query: '{query_text}'")
    
    query_processor = QueryProcessor()
    processed_query_no_emb = query_processor.process(query_text)
    
    embedded_query = embedding_service.embed_processed_query(processed_query_no_emb)
    
    processed_query = embedded_query.processed_query
    processed_query.embedding = embedded_query.embedding

    print("\n[M3] Running M3 Search and Reranking (BM25 + Dense + RRF)...")
    evidence_output, latency_ms = m3_pipeline.run(processed_query)

    print(f"[M3] Retrieved {len(evidence_output.retrieved_evidence)} chunks in {latency_ms:.2f}ms")
    for ev in evidence_output.retrieved_evidence:
        print(f" - [{ev.chunk_id}] Score: {ev.score:.4f} | {ev.text[:60]}...")

    print("\n[M4] Initializing M4 Orchestration Service (RAG)...")
    m4_service = M4OrchestrationService()

    print("[M4] Running LLM Generation (Local Ollama)...")
    try:
        response = m4_service.answer_search(processed_query, evidence_output)
        print("\n" + "="*40)
        print("--- AI Response ---")
        print(f"Answer: {response.answer}")
        print(f"Confidence: {response.confidence}")
        citations = [f"{c.evidence_id} -> {c.chunk_id} (Doc: {c.document_id})" for c in response.citations]
        print(f"Citations: {citations}")
        print("="*40)
    except Exception as e:
        print(f"\n[M4] LLM Generation failed: {e}")
        print("Please make sure Ollama is running locally with the configured model (e.g. qwen2.5:latest).")

if __name__ == "__main__":
    main()
