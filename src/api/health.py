import json
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

from src.orchestration import M4Settings


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    status: Literal[
        "ready",
        "not_ready",
    ]

    ollama_reachable: bool
    model_available: bool
    model_name: str
    detail: str | None = None


class M4ReadinessChecker:
    """
    Checks whether the configured local Ollama runtime
    and M4 model are available.

    This is a readiness check, not a generation request.
    """

    def __init__(
        self,
        settings: M4Settings | None = None,
    ) -> None:
        self.settings = (
            settings
            or M4Settings()
        )

    async def check(
        self,
    ) -> ReadinessResponse:
        url = (
            f"{self.settings.ollama_base_url}"
            "/api/tags"
        )

        timeout_seconds = min(
            self.settings.request_timeout_seconds,
            10.0,
        )

        try:
            async with httpx.AsyncClient(
                timeout=timeout_seconds,
            ) as client:
                response = await client.get(
                    url
                )

                response.raise_for_status()

                payload = response.json()

        except (
            httpx.HTTPError,
            json.JSONDecodeError,
            OSError,
        ) as exc:
            return ReadinessResponse(
                status="not_ready",
                ollama_reachable=False,
                model_available=False,
                model_name=self.settings.model_name,
                detail=(
                    "Ollama readiness check failed at "
                    f"{self.settings.ollama_base_url}: "
                    f"{exc}"
                ),
            )

        models = payload.get(
            "models",
            []
        )

        available_model_names: set[str] = set()

        for model in models:
            if not isinstance(
                model,
                dict,
            ):
                continue

            name = model.get(
                "name"
            )

            model_name = model.get(
                "model"
            )

            if isinstance(
                name,
                str,
            ):
                available_model_names.add(
                    name
                )

            if isinstance(
                model_name,
                str,
            ):
                available_model_names.add(
                    model_name
                )

        configured_model = (
            self.settings.model_name
        )

        if (
            configured_model
            not in available_model_names
        ):
            return ReadinessResponse(
                status="not_ready",
                ollama_reachable=True,
                model_available=False,
                model_name=configured_model,
                detail=(
                    "Configured model is not installed "
                    "in Ollama"
                ),
            )

        return ReadinessResponse(
            status="ready",
            ollama_reachable=True,
            model_available=True,
            model_name=configured_model,
            detail=None,
        )
