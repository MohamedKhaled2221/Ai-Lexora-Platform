from ipaddress import (
    ip_address,
)
from pathlib import Path
from urllib.parse import (
    urlparse,
)

from pydantic import (
    Field,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


_LOOPBACK_HOSTNAMES = {
    "localhost",
}


class DeploymentSettings(
    BaseSettings
):
    """
    Process-level production deployment settings.

    AI-Lexora currently targets a single-machine,
    local/offline deployment.
    """

    model_config = SettingsConfigDict(
        env_prefix="DEPLOY_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    host: str = "127.0.0.1"

    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
    )

    # Multiple workers would duplicate the loaded
    # ML runtimes in memory.
    workers: int = Field(
        default=1,
        ge=1,
    )

    @model_validator(
        mode="after"
    )
    def validate_deployment(
        self,
    ) -> "DeploymentSettings":
        if not _is_loopback_host(
            self.host
        ):
            raise ValueError(
                "Production API binding must "
                "use a loopback host."
            )

        if self.workers != 1:
            raise ValueError(
                "Production deployment requires "
                "exactly one Uvicorn worker."
            )

        return self


def _is_loopback_host(
    host: str,
) -> bool:
    normalized = (
        host
        .strip()
        .lower()
        .strip("[]")
    )

    if normalized in (
        _LOOPBACK_HOSTNAMES
    ):
        return True

    try:
        return ip_address(
            normalized
        ).is_loopback

    except ValueError:
        return False


def _validate_loopback_url(
    *,
    name: str,
    value: str,
) -> None:
    parsed = urlparse(
        value
    )

    if parsed.scheme not in {
        "http",
        "https",
    }:
        raise RuntimeError(
            f"{name} must use HTTP(S)."
        )

    if parsed.hostname is None:
        raise RuntimeError(
            f"{name} must contain a host."
        )

    if not _is_loopback_host(
        parsed.hostname
    ):
        raise RuntimeError(
            f"{name} must use a loopback host."
        )


def _validate_local_model_directory(
    *,
    name: str,
    value: str,
) -> Path:
    path = Path(
        value
    ).expanduser()

    if not path.is_absolute():
        raise RuntimeError(
            f"{name} must be an absolute "
            "local model directory."
        )

    if not path.is_dir():
        raise RuntimeError(
            f"{name} directory does not exist."
        )

    config_file = (
        path / "config.json"
    )

    if not config_file.is_file():
        raise RuntimeError(
            f"{name} is missing config.json."
        )

    has_weights = (
        any(
            path.glob(
                "*.safetensors"
            )
        )
        or any(
            path.glob(
                "pytorch_model*.bin"
            )
        )
    )

    if not has_weights:
        raise RuntimeError(
            f"{name} does not contain "
            "model weights."
        )

    return path


def validate_production_deployment(
    *,
    api_environment: str,
    log_output_format: str,
    disable_uvicorn_access_log: bool,
    strict_offline: bool,
    embedding_model: str,
    reranker_model: str,
    ollama_base_url: str,
    qdrant_location: str,
) -> None:
    """
    Validate the deployment contract before
    Uvicorn starts serving requests.

    This is intentionally stricter than the normal
    development runtime.
    """

    if api_environment != "production":
        raise RuntimeError(
            "The production launcher requires "
            "API_ENVIRONMENT=production."
        )

    if log_output_format != "json":
        raise RuntimeError(
            "Production operational logging "
            "must use JSON format."
        )

    if not disable_uvicorn_access_log:
        raise RuntimeError(
            "Production must disable the "
            "Uvicorn access log."
        )

    if not strict_offline:
        raise RuntimeError(
            "Production requires strict "
            "offline RAG mode."
        )

    _validate_loopback_url(
        name="Ollama",
        value=ollama_base_url,
    )

    _validate_loopback_url(
        name="Qdrant",
        value=qdrant_location,
    )

    _validate_local_model_directory(
        name="BGE-M3 embedding model",
        value=embedding_model,
    )

    _validate_local_model_directory(
        name="BGE reranker model",
        value=reranker_model,
    )
