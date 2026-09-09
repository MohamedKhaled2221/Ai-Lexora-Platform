from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import (
    PackageNotFoundError,
    version,
)
import math
import os
from time import perf_counter
from typing import Any

from FlagEmbedding import BGEM3FlagModel
import psutil
import torch

from src.config import settings
from src.schemas import (
    DocumentChunk,
    EmbeddedDocumentChunk,
    EmbeddedQuery,
    ProcessedQuery,
)


_BYTES_PER_MIB = 1024 * 1024


class EmbeddingServiceError(RuntimeError):
    """
    Base error for M2 embedding failures.
    """


class EmbeddingModelLoadError(
    EmbeddingServiceError
):
    """
    Raised when BGE-M3 cannot be initialized safely.
    """


class EmbeddingRuntimeError(
    EmbeddingServiceError
):
    """
    Raised when model inference fails.
    """


class EmbeddingContractError(
    EmbeddingServiceError
):
    """
    Raised when model output violates the M2 embedding contract.
    """


@dataclass(
    frozen=True,
    slots=True,
)
class EmbeddingRunMetrics:
    """
    Operational metrics for the latest successful embedding call.
    """

    text_count: int
    dimension: int
    latency_ms: float
    device: str

    rss_before_mib: float
    rss_after_mib: float
    rss_delta_mib: float

    cuda_peak_allocated_mib: (
        float | None
    )


class EmbeddingService:
    """
    Hardened BGE-M3 embedding service owned by M2.

    Responsibilities:
        - load the configured BGE-M3 model;
        - select the local CPU/GPU runtime;
        - embed queries and trusted document chunks;
        - validate embedding count and dimensions;
        - reject invalid/non-finite vectors;
        - optionally enforce L2 normalization;
        - expose model/runtime metadata;
        - record latency and memory metrics.

    Non-responsibilities:
        - Qdrant indexing;
        - retrieval;
        - reranking;
        - query interpretation;
        - LLM generation.
    """

    def __init__(
        self,
        model_name: str = settings.embedding_model,
        use_fp16: bool = settings.use_fp16,
        batch_size: int = settings.batch_size,
        max_length: int = settings.max_length,
        normalize_embeddings: bool = (
            settings.normalize_embeddings
        ),
        expected_dimension: int = (
            settings.embedding_dimension
        ),
        device: str = (
            settings.embedding_device
        ),
        model: Any | None = None,
    ) -> None:
        if not model_name.strip():
            raise ValueError(
                "model_name must not be empty"
            )

        if batch_size < 1:
            raise ValueError(
                "batch_size must be at least 1"
            )

        if max_length < 1:
            raise ValueError(
                "max_length must be at least 1"
            )

        if expected_dimension < 1:
            raise ValueError(
                "expected_dimension must be "
                "at least 1"
            )

        self.model_name = model_name
        self.batch_size = batch_size
        self.max_length = max_length

        self.normalize_embeddings = (
            normalize_embeddings
        )

        self.expected_dimension = (
            expected_dimension
        )

        self.device = self._resolve_device(
            device
        )
        self._cuda_peak_metrics_available = (
            self.device.startswith("cuda")
        )

        # FP16 should only be enabled for CUDA inference.
        self.use_fp16 = bool(
            use_fp16
            and self.device.startswith(
                "cuda"
            )
        )

        self._dimension: int | None = None

        self.last_metrics: (
            EmbeddingRunMetrics | None
        ) = None

        self.model_load_ms = 0.0
        self.model_load_rss_delta_mib = 0.0

        if model is not None:
            # Test/injected runtime. Do not load another model.
            self.model = model
        else:
            before_rss = self._rss_mib()

            started = perf_counter()

            self.model = self._load_model()

            self.model_load_ms = (
                perf_counter() - started
            ) * 1000.0

            self.model_load_rss_delta_mib = (
                self._rss_mib()
                - before_rss
            )

    # ---------------------------------------------------------
    # Runtime metadata
    # ---------------------------------------------------------
    def _cuda_device_index(
        self,
    ) -> int | None:
        """
        Return the integer CUDA device index used by PyTorch's
        memory-stat APIs.

        Some PyTorch/CUDA combinations are less reliable when a
        torch.device object is supplied to these APIs.
        """

        if not self.device.startswith(
            "cuda"
        ):
            return None

        if self.device == "cuda":
            return 0

        try:
            return int(
                self.device.split(
                    ":",
                    maxsplit=1,
                )[1]
            )
        except (
            ValueError,
            IndexError,
        ):
            return None
    @property
    def dimension(
        self,
    ) -> int | None:
        """
        Return the detected dimension after successful inference.
        """

        return self._dimension

    @property
    def runtime_metadata(
        self,
    ) -> dict[str, Any]:
        """
        Return non-sensitive model/runtime metadata.

        No query/document content is included.
        """

        return {
            "model_name": self.model_name,
            "expected_dimension": (
                self.expected_dimension
            ),
            "detected_dimension": (
                self._dimension
            ),
            "device": self.device,
            "use_fp16": self.use_fp16,
            "batch_size": self.batch_size,
            "max_length": self.max_length,
            "normalize_embeddings": (
                self.normalize_embeddings
            ),
            "flagembedding_version": (
                self._package_version(
                    "FlagEmbedding"
                )
            ),
            "torch_version": (
                torch.__version__
            ),
            "cuda_available": (
                torch.cuda.is_available()
            ),
            "cuda_device_name": (
                self._cuda_device_name()
            ),
            "model_load_ms": (
                self.model_load_ms
            ),
            "model_load_rss_delta_mib": (
                self.model_load_rss_delta_mib
            ),
        }

    # ---------------------------------------------------------
    # Model loading
    # ---------------------------------------------------------

    def _load_model(
        self,
    ) -> BGEM3FlagModel:
        try:
            return BGEM3FlagModel(
                self.model_name,
                use_fp16=self.use_fp16,
                devices=[
                    self.device
                ],
            )

        except Exception as exc:
            raise EmbeddingModelLoadError(
                "Unable to load the configured "
                f"BGE-M3 model: {self.model_name}"
            ) from exc

    @staticmethod
    def _resolve_device(
        requested: str,
    ) -> str:
        value = (
            requested.strip().lower()
            if requested
            else "auto"
        )

        if value == "auto":
            if torch.cuda.is_available():
                return "cuda:0"

            return "cpu"

        if value == "cpu":
            return "cpu"

        if value == "cuda":
            value = "cuda:0"

        if value.startswith("cuda:"):
            if not torch.cuda.is_available():
                raise EmbeddingModelLoadError(
                    "CUDA embedding device was "
                    "requested but CUDA is not available."
                )

            try:
                index = int(
                    value.split(
                        ":",
                        maxsplit=1,
                    )[1]
                )
            except (
                ValueError,
                IndexError,
            ) as exc:
                raise ValueError(
                    "CUDA device must use the "
                    "format cuda:<index>."
                ) from exc

            if (
                index < 0
                or index
                >= torch.cuda.device_count()
            ):
                raise EmbeddingModelLoadError(
                    "Requested CUDA embedding device "
                    "does not exist."
                )

            return value

        raise ValueError(
            "embedding_device must be one of: "
            "auto, cpu, cuda, or cuda:<index>"
        )

    # ---------------------------------------------------------
    # Core encoding
    # ---------------------------------------------------------

    def _encode(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        text_batch = list(
            texts
        )

        if not text_batch:
            raise ValueError(
                "texts must not be empty"
            )

        if any(
            not text
            or not text.strip()
            for text in text_batch
        ):
            raise ValueError(
                "texts must not contain "
                "empty strings"
            )

        rss_before = self._rss_mib()

        self._prepare_cuda_metrics()
        self._synchronize_cuda()

        started = perf_counter()

        try:
            result = self.model.encode(
                text_batch,
                batch_size=self.batch_size,
                max_length=self.max_length,

                # M2 currently requires dense vectors only.
                # Avoid unnecessary sparse/ColBERT computation.
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )

            self._synchronize_cuda()

            latency_ms = (
                perf_counter() - started
            ) * 1000.0

            vectors = self._extract_dense_vectors(
                result=result,
                expected_count=len(
                    text_batch
                ),
            )

        except EmbeddingContractError:
            raise

        except Exception as exc:
            raise EmbeddingRuntimeError(
                "BGE-M3 embedding inference failed."
            ) from exc

        rss_after = self._rss_mib()

        self._dimension = len(
            vectors[0]
        )

        self.last_metrics = (
            EmbeddingRunMetrics(
                text_count=len(
                    text_batch
                ),
                dimension=self._dimension,
                latency_ms=latency_ms,
                device=self.device,
                rss_before_mib=rss_before,
                rss_after_mib=rss_after,
                rss_delta_mib=(
                    rss_after
                    - rss_before
                ),
                cuda_peak_allocated_mib=(
                    self._cuda_peak_memory_mib()
                ),
            )
        )

        return vectors

    def _extract_dense_vectors(
        self,
        *,
        result: Any,
        expected_count: int,
    ) -> list[list[float]]:
        if not isinstance(
            result,
            dict,
        ):
            raise EmbeddingContractError(
                "BGE-M3 returned an unexpected "
                "result type."
            )

        if "dense_vecs" not in result:
            raise EmbeddingContractError(
                "BGE-M3 output does not contain "
                "dense_vecs."
            )

        raw_vectors = result[
            "dense_vecs"
        ]

        try:
            raw_count = len(
                raw_vectors
            )
        except TypeError as exc:
            raise EmbeddingContractError(
                "BGE-M3 dense_vecs is not a "
                "vector sequence."
            ) from exc

        if raw_count != expected_count:
            raise EmbeddingContractError(
                "BGE-M3 returned a different "
                "number of vectors than input texts."
            )

        output: list[
            list[float]
        ] = []

        for raw_vector in raw_vectors:
            if hasattr(
                raw_vector,
                "tolist",
            ):
                raw_values = (
                    raw_vector.tolist()
                )
            else:
                raw_values = list(
                    raw_vector
                )

            try:
                vector = [
                    float(value)
                    for value
                    in raw_values
                ]
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise EmbeddingContractError(
                    "BGE-M3 returned a "
                    "non-numeric dense vector."
                ) from exc

            self._validate_vector(
                vector
            )

            if self.normalize_embeddings:
                vector = (
                    self._normalize_vector(
                        vector
                    )
                )

            output.append(
                vector
            )

        if not output:
            raise EmbeddingContractError(
                "BGE-M3 returned no dense vectors."
            )

        return output

    def _validate_vector(
        self,
        vector: list[float],
    ) -> None:
        if not vector:
            raise EmbeddingContractError(
                "BGE-M3 returned an empty "
                "dense vector."
            )

        if (
            len(vector)
            != self.expected_dimension
        ):
            raise EmbeddingContractError(
                "BGE-M3 embedding dimension "
                f"mismatch: expected "
                f"{self.expected_dimension}, "
                f"received {len(vector)}."
            )

        if not all(
            math.isfinite(value)
            for value in vector
        ):
            raise EmbeddingContractError(
                "BGE-M3 returned NaN or "
                "infinite embedding values."
            )

    @staticmethod
    def _normalize_vector(
        vector: list[float],
    ) -> list[float]:
        norm = math.sqrt(
            sum(
                value * value
                for value in vector
            )
        )

        if (
            not math.isfinite(norm)
            or norm <= 0.0
        ):
            raise EmbeddingContractError(
                "BGE-M3 returned a zero or "
                "invalid embedding vector."
            )

        return [
            value / norm
            for value in vector
        ]

    # ---------------------------------------------------------
    # Public embedding API
    # ---------------------------------------------------------

    def embed_text(
        self,
        text: str,
    ) -> list[float]:
        """
        Embed one legal text.
        """

        return self._encode(
            [text]
        )[0]

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        """
        Embed multiple legal passages in one batch.
        """

        return self._encode(
            texts
        )

    def embed_query(
        self,
        query: str | ProcessedQuery,
    ) -> list[float]:
        """
        Embed a raw query or an already processed query.

        Processed queries use normalized_text rather than
        replacing the user's original query.
        """

        text = (
            query.normalized_text
            if isinstance(
                query,
                ProcessedQuery,
            )
            else query
        )

        return self.embed_text(
            text
        )

    def embed_processed_query(
        self,
        query: ProcessedQuery,
    ) -> EmbeddedQuery:
        """
        Produce the complete M2 query embedding handoff.
        """

        vector = self.embed_query(
            query
        )

        return EmbeddedQuery(
            processed_query=query,
            embedding=vector,
            model=self.model_name,
            dimension=len(
                vector
            ),
        )

    def embed_document_chunk(
        self,
        document_id: str,
        chunk_id: str,
        text: str,
    ) -> EmbeddedDocumentChunk:
        """
        Embed one document chunk.
        """

        vector = self.embed_text(
            text
        )

        return EmbeddedDocumentChunk(
            document_id=document_id,
            chunk_id=chunk_id,
            text=text,
            embedding=vector,
            model=self.model_name,
            dimension=len(
                vector
            ),
        )

    def embed_document_chunks(
        self,
        chunks: Sequence[
            DocumentChunk
        ],
    ) -> list[
        EmbeddedDocumentChunk
    ]:
        """
        Embed trusted document chunks received from M1.

        All M1 source/provenance metadata is preserved.
        """

        if not chunks:
            raise ValueError(
                "chunks must not be empty"
            )

        texts = [
            chunk.text
            for chunk in chunks
        ]

        vectors = self._encode(
            texts
        )

        results: list[
            EmbeddedDocumentChunk
        ] = []

        for (
            chunk,
            vector,
        ) in zip(
            chunks,
            vectors,
        ):
            results.append(
                EmbeddedDocumentChunk(
                    document_id=(
                        chunk.document_id
                    ),
                    chunk_id=(
                        chunk.chunk_id
                    ),
                    text=chunk.text,
                    page=chunk.page,
                    section=chunk.section,
                    clause=chunk.clause,
                    language=chunk.language,
                    document_type=(
                        chunk.document_type
                    ),
                    metadata=chunk.metadata,
                    embedding=vector,
                    model=self.model_name,
                    dimension=len(
                        vector
                    ),
                )
            )

        return results

    # ---------------------------------------------------------
    # Metrics helpers
    # ---------------------------------------------------------

    @staticmethod
    def _rss_mib(
        ) -> float:
        process = psutil.Process(
            os.getpid()
        )

        return (
            process
            .memory_info()
            .rss
            / _BYTES_PER_MIB
        )

    def _prepare_cuda_metrics(
    self,
) -> None:
        index = self._cuda_device_index()

        if index is None:
            return

        try:
            torch.cuda.reset_peak_memory_stats(
                index
            )
        except RuntimeError:
            # Metrics are observability only.
            # A metrics API incompatibility must not prevent
            # otherwise-valid BGE-M3 inference.
            self._cuda_peak_metrics_available = False
    def _synchronize_cuda(
        self,
    ) -> None:
        index = self._cuda_device_index()

        if index is None:
            return

        try:
            torch.cuda.synchronize(
                index
            )
        except RuntimeError:
            # If synchronization is unavailable for metrics/timing,
            # let model inference determine whether CUDA itself works.
            return
    def _cuda_peak_memory_mib(
        self,
    ) -> float | None:
        index = self._cuda_device_index()

        if (
            index is None
            or not self._cuda_peak_metrics_available
        ):
            return None

        try:
            value = (
                torch.cuda
                .max_memory_allocated(
                    index
                )
            )
        except RuntimeError:
            self._cuda_peak_metrics_available = False
            return None

        return (
            value
            / _BYTES_PER_MIB
        )

    def _cuda_device_name(
        self,
    ) -> str | None:
        index = self._cuda_device_index()

        if index is None:
            return None

        try:
            return (
                torch.cuda.get_device_name(
                    index
                )
            )
        except RuntimeError:
            return None

    @staticmethod
    def _package_version(
        package_name: str,
    ) -> str:
        try:
            return version(
                package_name
            )
        except PackageNotFoundError:
            return "unknown"