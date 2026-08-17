import asyncio
import time
from typing import Sequence

import httpx
from langchain_core.messages import BaseMessage
from langchain_ollama import ChatOllama
from ollama import ResponseError

from src.orchestration.settings import M4Settings
from src.schemas.m4_contract import M4ModelOutput


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
    - enforce M4ModelOutput structured output
    - provide synchronous and asynchronous invocation
    - retry transient local Ollama failures
    - convert provider/runtime errors into M4-specific exceptions

    Prompt construction and citation validation intentionally live in
    separate orchestration components.
    """

    def __init__(
        self,
        settings: M4Settings | None = None,
        *,
        structured_llm=None,
    ) -> None:
        self.settings = settings or M4Settings()

        if structured_llm is not None:
            # Dependency injection for tests and future alternate runtimes.
            self._structured_llm = structured_llm
            self._llm = None
            return

        self._llm = self._build_llm()

        self._structured_llm = self._llm.with_structured_output(
            M4ModelOutput,
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
    ) -> M4ModelOutput:
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
    ) -> M4ModelOutput:
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
    ) -> M4ModelOutput:
        if isinstance(result, M4ModelOutput):
            return result

        try:
            return M4ModelOutput.model_validate(
                result
            )
        except Exception as exc:
            raise M4LLMInvocationError(
                "Ollama returned output that could not be "
                "validated as M4ModelOutput"
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
