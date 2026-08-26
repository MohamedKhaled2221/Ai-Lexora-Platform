import asyncio
import time
from typing import Sequence, TypeVar

import httpx
from langchain_core.messages import BaseMessage
from langchain_ollama import ChatOllama
from ollama import ResponseError

from src.orchestration.settings import M4Settings
from src.schemas.m4_contract import M4ModelOutput


T = TypeVar("T")


class M4LLMError(RuntimeError):
    """
    Base exception for M4 local LLM failures.
    """


class M4LLMConnectionError(M4LLMError):
    """
    Raised when the Ollama service cannot be reached.
    """


class M4LLMInvocationError(M4LLMError):
    """
    Raised when Ollama or the configured model fails during generation.
    """


class M4LLMService:
    """
    Local Qwen/Ollama model adapter for the M4 orchestration layer.

    Responsibilities:
    - configure ChatOllama from M4Settings
    - support configurable Pydantic structured outputs
    - provide synchronous and asynchronous invocation
    - retry transient local Ollama failures
    - convert provider/runtime errors into M4-specific exceptions

    The default output schema remains M4ModelOutput,
    so the existing M4 orchestration workflow is preserved.

    Other modules, such as M5, can provide their own
    Pydantic output schema when using the same local LLM service.
    """

    def __init__(
        self,
        settings: M4Settings | None = None,
        *,
        output_schema: type[T] = M4ModelOutput,
        structured_llm=None,
    ) -> None:

        self.settings = settings or M4Settings()

        self.output_schema = output_schema

        if structured_llm is not None:
            # Dependency injection for tests and future alternate runtimes.
            self._structured_llm = structured_llm
            self._llm = None
            return

        self._llm = self._build_llm()

        self._structured_llm = self._llm.with_structured_output(
            self.output_schema,
            method="json_schema",
            include_raw=False,
        )

    def _build_llm(self) -> ChatOllama:
        return ChatOllama(
            model=self.settings.model_name,
            base_url=self.settings.ollama_base_url,
            temperature=self.settings.temperature,
            num_ctx=self.settings.num_ctx,
            num_predict=self.settings.num_predict,
            keep_alive=self.settings.keep_alive,
            reasoning=self.settings.reasoning,
            seed=self.settings.seed,
            validate_model_on_init=(
                self.settings.validate_model_on_init
            ),
            client_kwargs={
                "timeout": self.settings.request_timeout_seconds,
            },
        )

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> T:
        """
        Generate a validated structured response synchronously.
        """

        if not messages:
            raise ValueError(
                "M4LLMService requires at least one prompt message"
            )

        attempt = 0

        while True:
            try:
                result = self._structured_llm.invoke(
                    list(messages)
                )

                return self._ensure_model_output(
                    result
                )

            except Exception as exc:
                if not self._should_retry(
                    exc=exc,
                    attempt=attempt,
                ):
                    raise self._translate_exception(
                        exc
                    ) from exc

                self._sleep_before_retry(
                    attempt
                )

                attempt += 1

    async def ainvoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> T:
        """
        Generate a validated structured response asynchronously.
        """

        if not messages:
            raise ValueError(
                "M4LLMService requires at least one prompt message"
            )

        attempt = 0

        while True:
            try:
                result = await self._structured_llm.ainvoke(
                    list(messages)
                )

                return self._ensure_model_output(
                    result
                )

            except Exception as exc:
                if not self._should_retry(
                    exc=exc,
                    attempt=attempt,
                ):
                    raise self._translate_exception(
                        exc
                    ) from exc

                await asyncio.sleep(
                    self._retry_delay_seconds(attempt)
                )

                attempt += 1

    def _ensure_model_output(
        self,
        result,
    ) -> T:
        """
        Validate the model result against the configured
        Pydantic output schema.
        """

        if isinstance(
            result,
            self.output_schema,
        ):
            return result

        try:
            return self.output_schema.model_validate(
                result
            )

        except Exception as exc:
            raise M4LLMInvocationError(
                "Ollama returned output that could not be "
                "validated against the configured output schema"
            ) from exc

    def _should_retry(
        self,
        *,
        exc: Exception,
        attempt: int,
    ) -> bool:

        if attempt >= self.settings.max_retries:
            return False

        if isinstance(
            exc,
            (
                ConnectionError,
                httpx.TimeoutException,
                httpx.TransportError,
            ),
        ):
            return True

        if isinstance(exc, ResponseError):
            status_code = exc.status_code

            return (
                status_code == 408
                or status_code == 429
                or status_code >= 500
            )

        return False

    def _retry_delay_seconds(
        self,
        attempt: int,
    ) -> float:
        """
        Small capped exponential backoff suitable for a local service.
        """

        return min(
            0.5 * (2 ** attempt),
            4.0,
        )

    def _sleep_before_retry(
        self,
        attempt: int,
    ) -> None:

        time.sleep(
            self._retry_delay_seconds(attempt)
        )

    def _translate_exception(
        self,
        exc: Exception,
    ) -> M4LLMError:

        if isinstance(
            exc,
            (
                ConnectionError,
                httpx.ConnectError,
            ),
        ):
            return M4LLMConnectionError(
                "Unable to connect to Ollama at "
                f"{self.settings.ollama_base_url}"
            )

        if isinstance(exc, httpx.TimeoutException):
            return M4LLMInvocationError(
                "Ollama request exceeded the configured "
                f"{self.settings.request_timeout_seconds} second timeout"
            )

        if isinstance(exc, ResponseError):
            return M4LLMInvocationError(
                "Ollama request failed "
                f"(status={exc.status_code}): {exc.error}"
            )

        if isinstance(exc, M4LLMError):
            return exc

        return M4LLMInvocationError(
            f"Local LLM invocation failed: {exc}"
        )
