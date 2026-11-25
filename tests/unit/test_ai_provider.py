"""Unit tests for GeminiProvider configuration guards, response parsing, and error mapping."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors as genai_errors
from google.genai import types

from tindahaniq.ai.provider import GeminiProvider
from tindahaniq.config import load_settings
from tindahaniq.exceptions import AIServiceError
from tindahaniq.models import ChatMessage, ToolResultMessage, ToolSpec


class _FakeModelsEndpoint:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class _FakeGenAIClient:
    def __init__(self, responses: list[Any]) -> None:
        self.models = _FakeModelsEndpoint(responses)


def test_gemini_provider_requires_api_key(isolated_env: Path) -> None:
    settings = load_settings(env_file=None)
    with pytest.raises(AIServiceError, match="Missing GEMINI_API_KEY"):
        GeminiProvider(settings)


def test_gemini_provider_parses_tool_calls_preserves_model_content_and_filters_thoughts(
    isolated_env: Path,
) -> None:
    settings = load_settings(env_file=None)

    fn_content = types.Content(
        role="model",
        parts=[
            types.Part(text="internal thinking...", thought=True),
            types.Part.from_function_call(
                name="analyze_profitability", args={"sort_by": "gross_profit"}
            ),
        ],
    )
    resp_1 = SimpleNamespace(candidates=[SimpleNamespace(content=fn_content)])

    text_content = types.Content(
        role="model",
        parts=[
            types.Part(text="hidden chain of thought", thought=True),
            types.Part.from_text(text="**Business Insight**\nCoca-Cola Mismo leads profits."),
        ],
    )
    resp_2 = SimpleNamespace(candidates=[SimpleNamespace(content=text_content)])

    fake_client = _FakeGenAIClient([resp_1, resp_2])
    provider = GeminiProvider(settings, client=fake_client)

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
    assert turn_1.tool_calls[0].name == "analyze_profitability"
    assert turn_1.text is None
    assert turn_1.raw_model_content is fn_content

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
    # Verify exact raw_model_content was passed back in step 2 contents
    sent_contents = fake_client.models.calls[1]["contents"]
    assert sent_contents[1] is fn_content


def test_gemini_provider_maps_rate_limit_and_empty_candidates(isolated_env: Path) -> None:
    settings = load_settings(env_file=None)
    rate_err = genai_errors.ClientError(
        429,
        {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}},
    )
    empty_resp = SimpleNamespace(candidates=[])

    provider = GeminiProvider(settings, client=_FakeGenAIClient([rate_err, empty_resp]))

    with pytest.raises(AIServiceError) as exc_429:
        provider.generate_turn(
            conversation=[ChatMessage(role="user", content="Hi")],
            current_turn_steps=(),
            system_instruction="sys",
            tools=(),
        )
    assert "rate limit" in exc_429.value.user_message.lower()

    with pytest.raises(AIServiceError):
        provider.generate_turn(
            conversation=[ChatMessage(role="user", content="Hi")],
            current_turn_steps=(),
            system_instruction="sys",
            tools=(),
        )
