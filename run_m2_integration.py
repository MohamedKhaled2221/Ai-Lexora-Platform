import json
import os

from src.embedding_service import EmbeddingService
from src.schemas import DocumentChunk


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

    print("Initializing EmbeddingService...")
    embedding_service = EmbeddingService()

    print("Embedding document chunks...")
    embedded_chunks = embedding_service.embed_document_chunks(chunks)

    print(f"M2 embeddings generated: {len(embedded_chunks)}")

    first = embedded_chunks[0]

    print("Document ID:", first.document_id)
    print("Chunk ID:", first.chunk_id)
    print("Model:", first.model)
    print("Dimension:", first.dimension)
    print("Embedding length:", len(first.embedding))


if __name__ == "__main__":
    main()
