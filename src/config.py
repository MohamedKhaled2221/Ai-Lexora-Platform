from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the M2 embedding component."""

    embedding_model: str = "BAAI/bge-m3"
    use_fp16: bool = True
    batch_size: int = 8
    max_length: int = 512
    normalize_embeddings: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
    )


settings = Settings()
