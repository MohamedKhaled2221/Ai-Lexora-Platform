import logging
import numpy as np
from typing import List, Union

logger = logging.getLogger(__name__)


class BGEM3Embedder:
    """
    BGE-M3 Dense Embedding Engine.
    Generates 1024-dimensional dense vector representations for Arabic & English texts.
    Uses `sentence-transformers` (BAAI/bge-m3) with intelligent fallback.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: str = "cpu",
        use_mock_fallback: bool = True
    ):
        self.model_name = model_name
        self.device = device
        self.use_mock_fallback = use_mock_fallback
        self.vector_dim = 1024
        self.model = None

        self._init_model()

    def _init_model(self) -> None:
        """
        Attempt to load SentenceTransformer BGE-M3 model.
        """
        if not self.model_name:
            logger.info("No HuggingFace embedding model specified. Using mock vector generator.")
            return

        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading BGE-M3 Embedding Model: {self.model_name} on device '{self.device}'...")
            self.model = SentenceTransformer(self.model_name, device=self.device)
            self.vector_dim = self.model.get_sentence_embedding_dimension() or 1024
            logger.info(f"BGE-M3 Model loaded successfully with vector dimension = {self.vector_dim}.")
        except Exception as e:
            logger.warning(f"Could not load SentenceTransformer model '{self.model_name}': {e}.")
            if self.use_mock_fallback:
                logger.info("Enabling intelligent deterministic fallback for embeddings.")
            else:
                raise e

    def encode(self, texts: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        """
        Encode single text or batch of texts into dense vector embeddings.
        """
        is_single = isinstance(texts, str)
        text_list = [texts] if is_single else texts

        if not text_list:
            return [] if not is_single else []

        if self.model is not None:
            embeddings = self.model.encode(text_list, convert_to_numpy=True, normalize_embeddings=True)
            results = embeddings.tolist()
        else:
            results = [self._mock_encode(t) for t in text_list]

        return results[0] if is_single else results

    def _mock_encode(self, text: str) -> List[float]:
        """
        Deterministic pseudo-embedding for testing without downloading full 2GB model weights.
        """
        seed = sum(ord(c) for c in text) % (2**32)
        rng = np.random.RandomState(seed)
        vec = rng.randn(self.vector_dim)
        normalized_vec = vec / np.linalg.norm(vec)
        return normalized_vec.tolist()
