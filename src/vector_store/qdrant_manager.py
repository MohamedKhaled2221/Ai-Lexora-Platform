import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    """
    Qdrant Vector Database Manager for M3 Retrieval Pipeline.
    """

    def __init__(
        self,
        location: str = ":memory:",
        collection_name: str = "legal_documents",
        vector_size: int = 1024,
        distance: Distance = Distance.COSINE
    ):
        self.location = location
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.distance = distance

        self.client = QdrantClient(location=self.location)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """
        Create collection if it does not exist and setup payload indices.
        """
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            logger.info(f"Creating Qdrant collection '{self.collection_name}' with dim={self.vector_size}...")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=self.distance
                )
            )
            self._create_payload_indices()

    def _create_payload_indices(self) -> None:
        """
        Create payload index fields for high-performance metadata filtering.
        """
        payload_fields = ["document_type", "jurisdiction", "language", "document_id"]
        for field in payload_fields:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.KEYWORD
                )
            except Exception as e:
                logger.warning(f"Failed to create index for {field}: {e}")

    def upsert_chunks(self, points: List[PointStruct]) -> None:
        """
        Insert or update points (embeddings + metadata payload) in Qdrant.
        """
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        logger.info(f"Successfully upserted {len(points)} points into '{self.collection_name}'.")

    def build_qdrant_filter(
        self,
        document_type: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        language: Optional[str] = None,
        extra_filters: Optional[Dict[str, Any]] = None
    ) -> Optional[Filter]:
        """
        Construct Qdrant Filter object based on M2 metadata query filters.
        """
        must_conditions = []

        if document_type:
            must_conditions.append(
                FieldCondition(key="document_type", match=MatchValue(value=document_type))
            )
        if jurisdiction:
            must_conditions.append(
                FieldCondition(key="jurisdiction", match=MatchValue(value=jurisdiction))
            )
        if language:
            must_conditions.append(
                FieldCondition(key="language", match=MatchValue(value=language))
            )

        if extra_filters:
            for k, v in extra_filters.items():
                if v is not None:
                    must_conditions.append(
                        FieldCondition(key=k, match=MatchValue(value=str(v)))
                    )

        if must_conditions:
            return Filter(must=must_conditions)
        return None

    def dense_search(
        self,
        query_vector: List[float],
        query_filter: Optional[Filter] = None,
        top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Perform dense vector search with optional payload filters.
        """
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True
            )
            search_result = response.points
        else:
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True
            )

        results = []
        for res in search_result:
            payload = res.payload or {}
            results.append({
                "point_id": res.id,
                "score": float(res.score),
                "document_id": payload.get("document_id", ""),
                "chunk_id": payload.get("chunk_id", str(res.id)),
                "text": payload.get("text", ""),
                "page": payload.get("page"),
                "section": payload.get("section"),
                "language": payload.get("language", "ar"),
                "document_type": payload.get("document_type"),
                "jurisdiction": payload.get("jurisdiction")
            })
        return results

    def get_all_chunks(self, query_filter: Optional[Filter] = None) -> List[Dict[str, Any]]:
        """
        Fetch stored payload chunks for BM25/keyword indexing.
        """
        scroll_res, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=query_filter,
            limit=1000,
            with_payload=True,
            with_vectors=False
        )

        results = []
        for point in scroll_res:
            payload = point.payload or {}
            results.append({
                "point_id": point.id,
                "document_id": payload.get("document_id", ""),
                "chunk_id": payload.get("chunk_id", str(point.id)),
                "text": payload.get("text", ""),
                "page": payload.get("page"),
                "section": payload.get("section"),
                "language": payload.get("language", "ar"),
                "document_type": payload.get("document_type"),
                "jurisdiction": payload.get("jurisdiction")
            })
        return results
