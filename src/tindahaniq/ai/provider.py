"""LLM provider protocol and OpenAI-compatible SDK adapter."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Protocol
from uuid import uuid4

import openai
from openai import OpenAI

from tindahaniq.config import AppSettings
from tindahaniq.exceptions import AIServiceError
from tindahaniq.models.ai import (
    ChatMessage,
    ProviderTurnResult,
    ToolCallRequest,
    ToolResultMessage,
    ToolSpec,
)


class LLMProvider(Protocol):
    """Provider-agnostic interface for multi-turn function-calling generation."""

    def generate_turn(
        self,
        *,
        conversation: Sequence[ChatMessage],
        current_turn_steps: Sequence[tuple[ProviderTurnResult, Sequence[ToolResultMessage]]],
        system_instruction: str,
        tools: Sequence[ToolSpec],
    ) -> ProviderTurnResult:
        """Generate the next assistant text or tool-call request."""


class OpenAIProvider:
    """OpenAI-compatible adapter backed by the official `openai` Python SDK."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        client: Any | None = None,
    ) -> None:
        self._model = settings.openai_model
        self._max_completion_tokens = settings.openai_max_completion_tokens
        if client is not None:
            self._client = client
            return

        if not settings.has_ai_api_key or settings.openai_api_key is None:
            raise AIServiceError(
                "Missing OPENAI_API_KEY configuration",
                user_message=(
                    "The AI Business Consultant is not configured yet. "
                    "Add `OPENAI_API_KEY` to your `.env` file to enable AI chat."
                ),
            )
        api_key = settings.openai_api_key.get_secret_value().strip()
        base_url = settings.openai_base_url.strip()
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def generate_turn(
        self,
        *,
        conversation: Sequence[ChatMessage],
        current_turn_steps: Sequence[tuple[ProviderTurnResult, Sequence[ToolResultMessage]]],
        system_instruction: str,
        tools: Sequence[ToolSpec],
    ) -> ProviderTurnResult:
        """Invoke OpenAI Chat Completions with conversation history and tool schemas."""
        messages = _build_openai_messages(system_instruction, conversation, current_turn_steps)
        request_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_completion_tokens": self._max_completion_tokens,
            "temperature": 0.2,
        }
        if tools:
            request_kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.parameters_schema,
                    },
                }
                for spec in tools
            ]

        try:
            response = self._client.chat.completions.create(**request_kwargs)
        except openai.APIStatusError as exc:
            raise _translate_openai_api_error(exc) from exc
        except (openai.APIConnectionError, openai.APITimeoutError) as exc:
            raise AIServiceError(
                f"Network error calling OpenAI provider ({exc.__class__.__name__})",
                user_message=(
                    "Could not reach the AI Business Consultant right now. "
                    "Please check your internet connection and try again."
                ),
            ) from exc
        except Exception as exc:
            raise AIServiceError(
                f"Unexpected error calling OpenAI provider ({exc.__class__.__name__})",
                user_message=(
                    "Could not reach the AI Business Consultant right now. "
                    "Please check your internet connection and try again."
                ),
            ) from exc

        return _parse_openai_response(response)


def _build_openai_messages(
    system_instruction: str,
    conversation: Sequence[ChatMessage],
    current_turn_steps: Sequence[tuple[ProviderTurnResult, Sequence[ToolResultMessage]]],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_instruction}]
    for msg in conversation:
        role = "user" if msg.role == "user" else "assistant"
        messages.append({"role": role, "content": msg.content})

    for model_turn, tool_results in current_turn_steps:
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": model_turn.text,
            "tool_calls": [
                {
                    "id": tc.call_id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in model_turn.tool_calls
            ],
        }
        messages.append(assistant_msg)

        for tr in tool_results:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tr.call_id,
                    "content": json.dumps(tr.payload),
                }
            )

    return messages


def _parse_openai_response(response: Any) -> ProviderTurnResult:
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise AIServiceError(
            "OpenAI returned zero choices",
            user_message=(
                "The AI assistant could not generate a response for that request. "
                "Please rephrase your question and try again."
            ),
        )

    message = getattr(choices[0], "message", None)
    raw_tool_calls = getattr(message, "tool_calls", None) or []
    tool_calls: list[ToolCallRequest] = []

    for tc in raw_tool_calls:
        fn = getattr(tc, "function", None)
        fn_name = getattr(fn, "name", None)
        if not fn_name:
            continue
        raw_args = getattr(fn, "arguments", None)
        if isinstance(raw_args, dict):
            parsed_args = dict(raw_args)
        elif isinstance(raw_args, str) and raw_args.strip():
            try:
                loaded = json.loads(raw_args)
                parsed_args = dict(loaded) if isinstance(loaded, dict) else {}
            except json.JSONDecodeError:
                parsed_args = {}
        else:
            parsed_args = {}
        call_id = str(getattr(tc, "id", None) or f"call_{uuid4().hex[:8]}")
        tool_calls.append(
            ToolCallRequest(
                call_id=call_id,
                name=str(fn_name),
                arguments=parsed_args,
            )
        )

    raw_content = getattr(message, "content", None)
    text = raw_content.strip() if isinstance(raw_content, str) and raw_content.strip() else None

    return ProviderTurnResult(
        text=text,
        tool_calls=tuple(tool_calls),
        raw_model_content=message,
    )


def _translate_openai_api_error(exc: openai.APIStatusError) -> AIServiceError:
    code = getattr(exc, "status_code", None)
    message_str = str(exc).upper()

    if code == 429 or "RATE_LIMIT" in message_str or "QUOTA" in message_str:
        return AIServiceError(
            f"OpenAI rate limit or quota exceeded (code={code})",
            user_message=(
                "The AI Business Consultant hit its API rate limit or credit quota. "
                "Please wait a moment or check your API credits."
            ),
            details={"status_code": 429},
        )
    if code in {401, 403} or ("API_KEY" in message_str or "API KEY" in message_str):
        return AIServiceError(
            f"OpenAI authentication/key error (code={code})",
            user_message=(
                "Your `OPENAI_API_KEY` was rejected by the AI provider. "
                "Please check the key in your `.env` file."
            ),
            details={"status_code": code},
        )
    if code == 404:
        return AIServiceError(
            f"OpenAI model or endpoint not found (code={code})",
            user_message=(
                "The configured `OPENAI_MODEL` or `OPENAI_BASE_URL` was not found. "
                "Check your `.env` settings and restart the app."
            ),
            details={"status_code": code},
        )
    return AIServiceError(
        f"OpenAI API error (code={code})",
        user_message=(
            "The AI provider returned a temporary service error. "
            "Your store dashboards and calculators remain available."
        ),
        details={"status_code": code},
    )
