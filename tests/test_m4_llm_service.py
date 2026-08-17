import pytest
import httpx
from langchain_core.messages import HumanMessage

from src.orchestration import (
    M4LLMInvocationError,
    M4LLMService,
    M4Settings,
)
from src.schemas import M4ModelOutput


class FakeStructuredLLM:
    def __init__(
        self,
        result=None,
        error=None,
    ):
        self.result = result
        self.error = error
        self.invoke_calls = 0
        self.ainvoke_calls = 0

    def invoke(self, messages):
        self.invoke_calls += 1

        if self.error is not None:
            raise self.error

        return self.result

    async def ainvoke(self, messages):
        self.ainvoke_calls += 1

        if self.error is not None:
            raise self.error

        return self.result

class FlakyStructuredLLM:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.invoke_calls = 0

    def invoke(self, messages):
        self.invoke_calls += 1

        outcome = self.outcomes.pop(0)

        if isinstance(outcome, Exception):
            raise outcome

        return outcome

def test_transient_timeout_is_retried(monkeypatch):
    fake = FlakyStructuredLLM(
        outcomes=[
            httpx.ReadTimeout("temporary timeout"),
            make_output(),
        ]
    )

    service = M4LLMService(
        settings=make_settings(max_retries=2),
        structured_llm=fake,
    )

    retry_attempts = []

    monkeypatch.setattr(
        service,
        "_sleep_before_retry",
        lambda attempt: retry_attempts.append(attempt),
    )

    result = service.invoke(
        [HumanMessage(content="Test")]
    )

    assert result == make_output()
    assert fake.invoke_calls == 2
    assert retry_attempts == [0]

def test_retry_limit_is_respected(monkeypatch):
    fake = FlakyStructuredLLM(
        outcomes=[
            httpx.ReadTimeout("timeout 1"),
            httpx.ReadTimeout("timeout 2"),
            httpx.ReadTimeout("timeout 3"),
        ]
    )

    service = M4LLMService(
        settings=make_settings(max_retries=2),
        structured_llm=fake,
    )

    monkeypatch.setattr(
        service,
        "_sleep_before_retry",
        lambda attempt: None,
    )

    with pytest.raises(
        M4LLMInvocationError,
        match="exceeded the configured",
    ):
        service.invoke(
            [HumanMessage(content="Test")]
        )

    # Initial attempt + 2 retries
    assert fake.invoke_calls == 3

def make_settings(
    *,
    max_retries: int = 0,
) -> M4Settings:
    return M4Settings(
        max_retries=max_retries,
        _env_file=None,
    )


def make_output() -> M4ModelOutput:
    return M4ModelOutput(
        answer="Termination requires notice [E1].",
        citation_ids=["E1"],
        confidence=0.9,
    )


def test_sync_invoke_returns_structured_output():
    fake = FakeStructuredLLM(
        result=make_output()
    )

    service = M4LLMService(
        settings=make_settings(),
        structured_llm=fake,
    )

    result = service.invoke(
        [HumanMessage(content="Test")]
    )

    assert isinstance(
        result,
        M4ModelOutput,
    )

    assert result.citation_ids == ["E1"]
    assert fake.invoke_calls == 1


@pytest.mark.asyncio
async def test_async_invoke_returns_structured_output():
    fake = FakeStructuredLLM(
        result=make_output()
    )

    service = M4LLMService(
        settings=make_settings(),
        structured_llm=fake,
    )

    result = await service.ainvoke(
        [HumanMessage(content="Test")]
    )

    assert isinstance(
        result,
        M4ModelOutput,
    )

    assert result.citation_ids == ["E1"]
    assert fake.ainvoke_calls == 1


def test_dict_output_is_validated_into_model():
    fake = FakeStructuredLLM(
        result={
            "answer": "Supported statement [E1].",
            "citation_ids": ["E1"],
            "confidence": 0.8,
        }
    )

    service = M4LLMService(
        settings=make_settings(),
        structured_llm=fake,
    )

    result = service.invoke(
        [HumanMessage(content="Test")]
    )

    assert isinstance(
        result,
        M4ModelOutput,
    )

    assert result.confidence == 0.8


def test_invalid_structured_result_is_rejected():
    fake = FakeStructuredLLM(
        result={
            "answer": "Broken result",
            "citation_ids": ["E0"],
            "confidence": 2.0,
        }
    )

    service = M4LLMService(
        settings=make_settings(),
        structured_llm=fake,
    )

    with pytest.raises(
        M4LLMInvocationError,
        match="could not be validated",
    ):
        service.invoke(
            [HumanMessage(content="Test")]
        )


def test_empty_messages_are_rejected():
    service = M4LLMService(
        settings=make_settings(),
        structured_llm=FakeStructuredLLM(
            result=make_output()
        ),
    )

    with pytest.raises(
        ValueError,
        match="at least one prompt message",
    ):
        service.invoke([])


@pytest.mark.asyncio
async def test_async_empty_messages_are_rejected():
    service = M4LLMService(
        settings=make_settings(),
        structured_llm=FakeStructuredLLM(
            result=make_output()
        ),
    )

    with pytest.raises(
        ValueError,
        match="at least one prompt message",
    ):
        await service.ainvoke([])


def test_non_retryable_error_is_wrapped():
    fake = FakeStructuredLLM(
        error=ValueError("bad request")
    )

    service = M4LLMService(
        settings=make_settings(),
        structured_llm=fake,
    )

    with pytest.raises(
        M4LLMInvocationError,
        match="Local LLM invocation failed",
    ):
        service.invoke(
            [HumanMessage(content="Test")]
        )

    assert fake.invoke_calls == 1
