from src.embedding_service import EmbeddingService
from src.query_processor import QueryProcessor
from src.schemas import EmbeddedQuery


class M2QueryPipeline:
    """
    Reusable M2 query pipeline.

    Responsibilities:
        - Process the raw user query.
        - Generate the BGE-M3 embedding.
        - Return the complete query handoff object.

    Non-responsibilities:
        - Retrieval.
        - Qdrant indexing.
        - Reranking.
        - RAG generation.
    """

    def __init__(
        self,
        query_processor: QueryProcessor | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        """
        Initialize the M2 query pipeline.

        The embedding model is loaded by EmbeddingService.
        If no services are provided, the pipeline creates them itself.
        """

        self.query_processor = query_processor or QueryProcessor()
        self.embedding_service = embedding_service or EmbeddingService()

    def process(self, raw_query: str) -> EmbeddedQuery:
        """
        Process and embed one raw user query.

        Input:
            raw_query:
                The original Arabic, English,
                Egyptian Arabic, or Arabic-English
                mixed user query.

        Output:
            EmbeddedQuery containing:
                - ProcessedQuery
                - embedding
                - model name
                - embedding dimension

        Raises:
            ValueError:
                If the query is empty or invalid.

        Notes:
            This method is synchronous.
            All inference is performed locally by BGE-M3.
        """

        processed_query = self.query_processor.process(raw_query)

        return self.embedding_service.embed_processed_query(
            processed_query
        )
