import hashlib
import re

import numpy as np
from typing import List, Dict, Any
from qdrant_client.http.models import PointStruct

from src.schemas.access_control import (
    NO_MATTER_ID,
    AccessScope,
)
from src.vector_store.qdrant_manager import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    to_sparse_vector,
)
from src.schemas.m2_contract import ProcessedQuery, QueryFilters


DEMO_CLIENT_ID = "client_demo"
"""The tenant the demo/mock corpus belongs to."""


def generate_mock_sparse_weights(
    text: str,
    vocab_size: int = 250_002,
    ngram: int = 3,
) -> Dict[str, float]:
    """
    Stand in for BGE-M3 lexical weights without loading BGE-M3.

    Hashes **character n-grams** as well as whole words to stable pseudo token
    ids. The n-grams matter: BGE-M3 is a subword model, and whole-word hashing
    is the wrong abstraction for Arabic. The demo query asks about
    ``الفسخ`` while the corpus says ``فسخ`` -- the same root carrying a
    definite article -- and a whole-word hash gives those two entirely
    different ids, so the demo's sparse retrieval silently returns nothing.
    Subword overlap is what makes the query and the document meet.

    This is still not BGE-M3: there is no learned term importance, only
    frequency and length. It exists so ``run_demo.py`` exercises the real
    native-sparse code path without the model weights installed. Real weights
    come from :meth:`EmbeddingService._encode`.
    """

    words = [
        word
        for word in re.split(r"\W+", text.lower())
        if word
    ]

    if not words:
        return {}

    features: List[str] = []

    for word in words:
        features.append(word)

        # Subword features. Short words contribute themselves only.
        for start in range(0, max(0, len(word) - ngram) + 1):
            piece = word[start:start + ngram]

            if len(piece) == ngram:
                features.append(piece)

    counts: Dict[str, int] = {}
    for feature in features:
        counts[feature] = counts.get(feature, 0) + 1

    weights: Dict[str, float] = {}

    for feature, count in counts.items():
        token_id = (
            int(
                hashlib.sha1(
                    feature.encode("utf-8")
                ).hexdigest()[:8],
                16,
            )
            % vocab_size
        )

        # Longer, repeated features weigh more -- a crude stand-in for the
        # learned importance BGE-M3 would assign.
        weight = min(
            1.0,
            0.15 * count + 0.05 * len(feature),
        )

        weights[str(token_id)] = max(
            weights.get(str(token_id), 0.0),
            round(weight, 4),
        )

    return weights


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
            "jurisdiction": chunk.get("jurisdiction"),
            # Demo data is stamped like real data: an unstamped point is
            # invisible to every scoped query, so the demo would retrieve
            # nothing without this.
            "client_id": chunk.get(
                "client_id",
                DEMO_CLIENT_ID,
            ),
            "matter_id": chunk.get(
                "matter_id",
                NO_MATTER_ID,
            ),
            "confidentiality_level": chunk.get(
                "confidentiality_level",
                "internal",
            ),
        }
        # The demo indexes both vectors, so run_demo.py exercises the real
        # native-sparse retrieval path instead of logging "no sparse query
        # vector" and quietly degrading to dense-only.
        sparse_vector = to_sparse_vector(
            generate_mock_sparse_weights(
                chunk["text"]
            )
        )

        vector = (
            {
                DENSE_VECTOR_NAME: vec,
                SPARSE_VECTOR_NAME: sparse_vector,
            }
            if sparse_vector is not None
            else vec
        )

        points.append(
            PointStruct(
                id=chunk["id"],
                vector=vector,
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
        sparse_embedding=generate_mock_sparse_weights(
            query_text
        ),
        filters=QueryFilters(
            document_type=doc_type,
            jurisdiction=jurisdiction,
            language=lang,
            # Retrieval refuses a query with no scope. In the API this comes
            # from the authenticated caller; the demo stands in for one.
            access=AccessScope(
                client_id=DEMO_CLIENT_ID,
                max_confidentiality="privileged",
            ),
        )
    )
