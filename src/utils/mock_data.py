import numpy as np
from typing import List, Dict, Any
from qdrant_client.http.models import PointStruct

from src.schemas.m2_contract import ProcessedQuery, QueryFilters


def generate_mock_embedding(dim: int = 1024, seed: int = 42) -> List[float]:
    """
    Generate a normalized mock 1024-dimensional embedding vector.
    Simulates what M2 (upstream embedding module) provides to M3.
    """
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(dim)
    norm = np.linalg.norm(vec)
    normalized_vec = vec / norm if norm > 0 else vec
    return normalized_vec.tolist()


def generate_mock_legal_chunks() -> List[Dict[str, Any]]:
    """
    Generate sample Arabic and English legal document chunks for Qdrant testing.
    """
    return [
        {
            "id": 1,
            "document_id": "doc_001",
            "chunk_id": "chunk_017",
            "text": "يحق لأحد الطرفين فسخ العقد في حالة خرق البند السابع والتأخر عن السداد لمدة تزيد عن ثلاثين يوماً من تاريخ الإخطار الرسمي.",
            "page": 12,
            "section": "شروط الفسخ والإنهاء",
            "language": "ar",
            "document_type": "contract",
            "jurisdiction": "Egypt",
            "seed": 101
        },
        {
            "id": 2,
            "document_id": "doc_001",
            "chunk_id": "chunk_018",
            "text": "في حالة القوة القاهرة، يتم تعليق التزامات الطرفين لمدة لا تجاوز ستين يوماً دون فرض أي غرامات تأخير.",
            "page": 13,
            "section": "القوة القاهرة",
            "language": "ar",
            "document_type": "contract",
            "jurisdiction": "Egypt",
            "seed": 102
        },
        {
            "id": 3,
            "document_id": "doc_002",
            "chunk_id": "chunk_005",
            "text": "تنص المادة 157 من القانون المدني المصري على أنه في العقود الملزمة للجانبين، إذا لم يوف أحد المتعاقدين بالتزامه جاز للمتعاقد الآخر أن يطالب بفسخ العقد.",
            "page": 45,
            "section": "القانون المدني - الفسخ القضائي",
            "language": "ar",
            "document_type": "law",
            "jurisdiction": "Egypt",
            "seed": 103
        },
        {
            "id": 4,
            "document_id": "doc_003",
            "chunk_id": "chunk_010",
            "text": "Either party may terminate this agreement immediately by written notice if the other party breaches any material term of this contract.",
            "page": 8,
            "section": "Termination Clause",
            "language": "en",
            "document_type": "contract",
            "jurisdiction": "KSA",
            "seed": 104
        },
        {
            "id": 5,
            "document_id": "doc_004",
            "chunk_id": "chunk_002",
            "text": "تخضع جميع النزاعات الناشئة عن هذا العقد لاختصاص المحاكم الاقتصادية بالقاهرة وفقاً للقانون المصري.",
            "page": 3,
            "section": "تسوية النزاعات والقانون الواجب التطبيق",
            "language": "ar",
            "document_type": "contract",
            "jurisdiction": "Egypt",
            "seed": 105
        }
    ]


def prepare_qdrant_points(chunks: List[Dict[str, Any]], vector_size: int = 1024) -> List[PointStruct]:
    """
    Convert raw chunks into Qdrant PointStruct list using mock embeddings.
    In production, embeddings are provided by M2 (upstream embedding module).
    """
    points = []
    for chunk in chunks:
        vec = generate_mock_embedding(dim=vector_size, seed=chunk.get("seed", 42))
        payload = {
            "document_id": chunk["document_id"],
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"],
            "page": chunk.get("page"),
            "section": chunk.get("section"),
            "language": chunk.get("language", "ar"),
            "document_type": chunk.get("document_type"),
            "jurisdiction": chunk.get("jurisdiction")
        }
        points.append(
            PointStruct(
                id=chunk["id"],
                vector=vec,
                payload=payload
            )
        )
    return points


def generate_mock_processed_query(
    query_id: str = "q_001",
    query_text: str = "ما هي شروط الفسخ؟",
    doc_type: str = "contract",
    jurisdiction: str = "Egypt",
    lang: str = "ar",
    seed: int = 101
) -> ProcessedQuery:
    """
    Generate mock ProcessedQuery matching M2 output contract.
    embedding is pre-populated as M2 would provide it.
    """
    return ProcessedQuery(
        query_id=query_id,
        text_original=query_text,
        normalized_text=query_text.strip(),
        language=lang,
        embedding=generate_mock_embedding(dim=1024, seed=seed),
        filters=QueryFilters(
            document_type=doc_type,
            jurisdiction=jurisdiction,
            language=lang
        )
    )
