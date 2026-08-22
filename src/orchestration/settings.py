from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class M4Settings(BaseSettings):
    """
    Runtime configuration for the M4 local LLM orchestration layer.

    Settings can be overridden through environment variables using
    the M4_ prefix or through a project-level .env file.
    """

    model_config = SettingsConfigDict(
        env_prefix="M4_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        str_strip_whitespace=True,
    )

    ollama_base_url: str = Field(
        default="http://localhost:11434",
        min_length=1,
        description="Base URL of the local Ollama server",
    )

    model_name: str = Field(
        default="qwen3.5:4b",
        min_length=1,
        description="Ollama model used by M4",
    )

    temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for grounded legal generation",
    )

    num_ctx: int = Field(
        default=4096,
        ge=1024,
        description="Ollama context window size",
    )

    num_predict: int = Field(
        default=512,
        ge=1,
        description="Maximum number of generated tokens",
    )

    keep_alive: str | int = Field(
        default="10m",
        description="How long Ollama keeps the model loaded after a request",
    )

    reasoning: bool = Field(
        default=False,
        description="Whether Qwen thinking/reasoning mode is enabled",
    )

    validate_model_on_init: bool = Field(
        default=True,
        description="Validate that the configured Ollama model exists at startup",
    )

    request_timeout_seconds: float = Field(
        default=120.0,
        gt=0.0,
        description="Timeout for a single Ollama request",
    )

    max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum retries for recoverable LLM request failures",
    )

    seed: int = Field(
        default=42,
        description="Generation seed used for reproducibility",
    )

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_base_url(cls, value: str) -> str:
        value = value.rstrip("/")

        if not value.startswith(("http://", "https://")):
            raise ValueError(
                "ollama_base_url must start with http:// or https://"
            )

        return value

    @field_validator("keep_alive")
    @classmethod
    def validate_keep_alive(cls, value: str | int) -> str | int:
        if isinstance(value, str) and not value.strip():
            raise ValueError("keep_alive cannot be empty")

        return value

    @model_validator(mode="after")
    def validate_generation_limits(self) -> "M4Settings":
        if self.num_predict >= self.num_ctx:
            raise ValueError(
                "num_predict must be smaller than num_ctx"
            )

        return self
