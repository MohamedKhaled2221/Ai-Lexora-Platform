from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the M2 embedding component."""

    embedding_model: str = "BAAI/bge-m3"
    use_fp16: bool = True
    batch_size: int = 8
    max_length: int = 512
    """BGE-M3's encoder window, in tokens.

    A **safety net, not a chunking policy.** M1 now sizes chunks against this
    same tokenizer (``ChunkingConfig.max_chunk_tokens = 480``), so in normal
    operation nothing reaching the encoder is long enough for this to bite and
    it is a no-op.

    It stays because the alternative to truncating an over-long text is
    crashing the ingest, and because M1 and M2 can be deployed at different
    versions: a chunk produced by an older M1 that predates token-aware
    chunking must still be embeddable. What must not happen is that
    truncation occurs *and nobody finds out* -- which is exactly what did
    happen, for every long Arabic chunk, until this was measured. See
    ``warn_on_truncation``.
    """

    warn_on_truncation: bool = True
    """Log when a text actually hits the ``max_length`` ceiling.

    Turns the safety net from an assumption into an observation. Truncation
    silently discards the tail of a chunk from both the dense and the sparse
    vector while the full text stays in the payload for keyword search, so a
    keyword hit can land on a passage no vector ever saw. That is worth a
    warning every time it happens.

    Costs one extra tokenization per text, which is a fraction of a percent of
    the encoder's own forward pass.
    """
    normalize_embeddings: bool = True

    return_sparse: bool = True
    """Whether BGE-M3 also emits lexical (sparse) weights.

    BGE-M3 produces dense and sparse representations from the same forward
    pass, so asking for both costs almost nothing beyond the extra tensors --
    the model was already computing them and the result was being discarded.

    Kept switchable because the sparse path is new: turning this off makes
    the service behave exactly as it did before, which is the fastest way to
    tell whether a retrieval regression came from sparse or from elsewhere.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
    )


settings = Settings()
