"""Unit tests for OpenAIProvider configuration guards, response parsing, and error mapping."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from tindahaniq.ai.provider import OpenAIProvider
from tindahaniq.config import load_settings
from tindahaniq.exceptions import AIServiceError
from tindahaniq.models import ChatMessage, ToolResultMessage, ToolSpec


class _FakeCompletionsEndpoint:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class _FakeChatNamespace:
    def __init__(self, responses: list[Any]) -> None:
        self.completions = _FakeCompletionsEndpoint(responses)


class _FakeOpenAIClient:
    def __init__(self, responses: list[Any]) -> None:
        self.chat = _FakeChatNamespace(responses)


def _make_status_error(status_code: int, message: str) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://aiki-labs.up.railway.app/api/v1/chat/completions")
    response = httpx.Response(status_code, request=request, json={"error": {"message": message}})
    return openai.APIStatusError(message, response=response, body={"error": {"message": message}})


def test_openai_provider_requires_api_key(isolated_env: Path) -> None:
    settings = load_settings(env_file=None)
    with pytest.raises(AIServiceError, match="Missing OPENAI_API_KEY"):
        OpenAIProvider(settings)


def test_openai_provider_parses_tool_calls_and_serializes_tool_results(
    isolated_env: Path,
) -> None:
    settings = load_settings(env_file=None)

    tc = SimpleNamespace(
        id="call_abc123",
        function=SimpleNamespace(
            name="analyze_profitability",
            arguments=json.dumps({"sort_by": "gross_profit"}),
        ),
    )
    msg_1 = SimpleNamespace(content=None, tool_calls=[tc])
    resp_1 = SimpleNamespace(choices=[SimpleNamespace(message=msg_1)])

    msg_2 = SimpleNamespace(
        content="**Business Insight**\nCoca-Cola Mismo leads profits.",
        tool_calls=None,
    )
    resp_2 = SimpleNamespace(choices=[SimpleNamespace(message=msg_2)])

    fake_client = _FakeOpenAIClient([resp_1, resp_2])
    provider = OpenAIProvider(settings, client=fake_client)

    spec = ToolSpec(
        name="analyze_profitability",
        description="Analyze profits",
        parameters_schema={"type": "object", "properties": {}},
    )
    conv = [ChatMessage(role="user", content="Which item is most profitable?")]

    turn_1 = provider.generate_turn(
        conversation=conv,
        current_turn_steps=(),
        system_instruction="System prompt",
        tools=(spec,),
    )
    assert len(turn_1.tool_calls) == 1
    assert turn_1.tool_calls[0].call_id == "call_abc123"
    assert turn_1.tool_calls[0].name == "analyze_profitability"
    assert turn_1.tool_calls[0].arguments == {"sort_by": "gross_profit"}
    assert turn_1.text is None

    tool_res = ToolResultMessage(
        call_id=turn_1.tool_calls[0].call_id,
        name="analyze_profitability",
        payload={"status": "ok", "top": "BEV-001"},
    )
    turn_2 = provider.generate_turn(
        conversation=conv,
        current_turn_steps=[(turn_1, [tool_res])],
        system_instruction="System prompt",
        tools=(spec,),
    )
    assert turn_2.tool_calls == ()
    assert turn_2.text == "**Business Insight**\nCoca-Cola Mismo leads profits."

    sent_messages = fake_client.chat.completions.calls[1]["messages"]
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[2]["role"] == "assistant"
    assert sent_messages[2]["tool_calls"][0]["id"] == "call_abc123"
    assert sent_messages[3]["role"] == "tool"
    assert sent_messages[3]["tool_call_id"] == "call_abc123"


def test_openai_provider_maps_rate_limit_auth_not_found_and_empty_choices(
    isolated_env: Path,
) -> None:
    settings = load_settings(env_file=None)
    rate_err = _make_status_error(429, "Rate limit exceeded")
    auth_err = _make_status_error(401, "Invalid API key provided")
    not_found_err = _make_status_error(404, "Model gpt-6-luna not found")
    empty_resp = SimpleNamespace(choices=[])

    provider = OpenAIProvider(
        settings,
        client=_FakeOpenAIClient([rate_err, auth_err, not_found_err, empty_resp]),
    )

    with pytest.raises(AIServiceError) as exc_429:
        provider.generate_turn(
            conversation=[ChatMessage(role="user", content="Hi")],
            current_turn_steps=(),
            system_instruction="sys",
            tools=(),
        )
    assert "rate limit" in exc_429.value.user_message.lower()

    with pytest.raises(AIServiceError) as exc_401:
        provider.generate_turn(
            conversation=[ChatMessage(role="user", content="Hi")],
            current_turn_steps=(),
            system_instruction="sys",
            tools=(),
        )
    assert "openai_api_key" in exc_401.value.user_message.lower()

    with pytest.raises(AIServiceError) as exc_404:
        provider.generate_turn(
            conversation=[ChatMessage(role="user", content="Hi")],
            current_turn_steps=(),
            system_instruction="sys",
            tools=(),
        )
    assert "openai_model" in exc_404.value.user_message.lower()

    with pytest.raises(AIServiceError):
        provider.generate_turn(
            conversation=[ChatMessage(role="user", content="Hi")],
            current_turn_steps=(),
            system_instruction="sys",
            tools=(),
        )
