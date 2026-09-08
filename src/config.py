from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    """
    Central configuration for the M2 embedding component.
    """

    embedding_model: str = "BAAI/bge-m3"

    # auto | cpu | cuda | cuda:0 | cuda:1 ...
    embedding_device: str = "auto"

    # BAAI/bge-m3 dense-vector dimension.
    embedding_dimension: int = 1024

    use_fp16: bool = True

    batch_size: int = 8

    # Intentionally below BGE-M3's maximum sequence length
    # to limit local inference latency and memory consumption.
    max_length: int = 512

    # BGE-M3 dense outputs are normally normalized already.
    # Keeping this enabled additionally enforces unit vectors
    # at the M2 boundary.
    normalize_embeddings: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
    )


settings = Settings()