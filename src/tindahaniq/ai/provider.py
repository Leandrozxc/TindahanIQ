"""LLM provider protocol and official Google GenAI SDK adapter."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol
from uuid import uuid4

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

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


class GeminiProvider:
    """Google Gemini adapter backed by the official `google-genai` SDK."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        client: Any | None = None,
    ) -> None:
        self._model = settings.gemini_model
        if client is not None:
            self._client = client
            return

        if not settings.has_ai_api_key or settings.gemini_api_key is None:
            raise AIServiceError(
                "Missing GEMINI_API_KEY configuration",
                user_message=(
                    "The AI Business Consultant is not configured yet. "
                    "Add `GEMINI_API_KEY` to your `.env` file to enable AI chat."
                ),
            )
        api_key = settings.gemini_api_key.get_secret_value().strip()
        self._client = genai.Client(api_key=api_key)

    def generate_turn(
        self,
        *,
        conversation: Sequence[ChatMessage],
        current_turn_steps: Sequence[tuple[ProviderTurnResult, Sequence[ToolResultMessage]]],
        system_instruction: str,
        tools: Sequence[ToolSpec],
    ) -> ProviderTurnResult:
        """Invoke Gemini `generate_content` with conversation history and tool schemas."""
        contents = _build_gemini_contents(conversation, current_turn_steps)
        gemini_tools = (
            [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=spec.name,
                            description=spec.description,
                            parameters_json_schema=spec.parameters_schema,
                        )
                        for spec in tools
                    ]
                )
            ]
            if tools
            else None
        )
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=gemini_tools,
            temperature=0.2,
        )

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=config,
            )
        except genai_errors.APIError as exc:
            raise _translate_gemini_api_error(exc) from exc
        except Exception as exc:
            raise AIServiceError(
                f"Unexpected error calling Gemini provider ({exc.__class__.__name__})",
                user_message=(
                    "Could not reach the AI Business Consultant right now. "
                    "Please check your internet connection and try again."
                ),
            ) from exc

        return _parse_gemini_response(response)


def _build_gemini_contents(
    conversation: Sequence[ChatMessage],
    current_turn_steps: Sequence[tuple[ProviderTurnResult, Sequence[ToolResultMessage]]],
) -> list[types.Content]:
    contents: list[types.Content] = []
    for msg in conversation:
        role = "user" if msg.role == "user" else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg.content)],
            )
        )

    for model_turn, tool_results in current_turn_steps:
        if isinstance(model_turn.raw_model_content, types.Content):
            contents.append(model_turn.raw_model_content)
        else:
            model_parts = [
                types.Part.from_function_call(name=tc.name, args=tc.arguments)
                for tc in model_turn.tool_calls
            ]
            contents.append(types.Content(role="model", parts=model_parts))

        response_parts = [
            types.Part.from_function_response(name=tr.name, response=tr.payload)
            for tr in tool_results
        ]
        contents.append(types.Content(role="user", parts=response_parts))

    return contents


def _parse_gemini_response(response: Any) -> ProviderTurnResult:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise AIServiceError(
            "Gemini returned zero candidates",
            user_message=(
                "The AI assistant could not generate a response for that request. "
                "Please rephrase your question and try again."
            ),
        )

    first_content = getattr(candidates[0], "content", None)
    parts = getattr(first_content, "parts", None) or []

    tool_calls: list[ToolCallRequest] = []
    text_fragments: list[str] = []

    for part in parts:
        fn_call = getattr(part, "function_call", None)
        if fn_call is not None and getattr(fn_call, "name", None):
            raw_args = getattr(fn_call, "args", None) or {}
            call_id = str(getattr(fn_call, "id", None) or f"call_{uuid4().hex[:8]}")
            tool_calls.append(
                ToolCallRequest(
                    call_id=call_id,
                    name=str(fn_call.name),
                    arguments=dict(raw_args),
                )
            )
            continue

        is_thought = bool(getattr(part, "thought", False))
        part_text = getattr(part, "text", None)
        if not is_thought and isinstance(part_text, str) and part_text:
            text_fragments.append(part_text)

    combined_text = "".join(text_fragments).strip() or None
    if not tool_calls and combined_text is None:
        fallback_text = getattr(response, "text", None)
        if isinstance(fallback_text, str) and fallback_text.strip():
            combined_text = fallback_text.strip()

    return ProviderTurnResult(
        text=combined_text,
        tool_calls=tuple(tool_calls),
        raw_model_content=first_content,
    )


def _translate_gemini_api_error(exc: genai_errors.APIError) -> AIServiceError:
    code = getattr(exc, "code", None)
    status_str = str(getattr(exc, "status", "") or "").upper()
    message_str = str(getattr(exc, "message", "") or "").upper()

    if code == 429 or "RESOURCE_EXHAUSTED" in status_str:
        return AIServiceError(
            f"Gemini rate limit exceeded (code={code})",
            user_message=(
                "The AI Business Consultant hit its free-tier rate limit. "
                "Please wait a moment and try your question again."
            ),
            details={"status_code": 429},
        )
    if code in {400, 401, 403} and (
        "API_KEY" in status_str
        or "PERMISSION_DENIED" in status_str
        or "UNAUTHENTICATED" in status_str
        or "API KEY" in message_str
        or "API_KEY" in message_str
    ):
        return AIServiceError(
            f"Gemini authentication/key error (code={code})",
            user_message=(
                "Your `GEMINI_API_KEY` was rejected by Google Gemini. "
                "Please check the key in your `.env` file."
            ),
            details={"status_code": code},
        )
    if code == 404 or "NOT_FOUND" in status_str:
        return AIServiceError(
            f"Gemini model not found/unavailable (code={code}, status={status_str})",
            user_message=(
                "The configured `GEMINI_MODEL` is unavailable or not supported for your API key. "
                "Update `GEMINI_MODEL` in your `.env` file (for example, `gemini-3.5-flash-lite`) "
                "and restart the app."
            ),
            details={"status_code": code},
        )
    return AIServiceError(
        f"Gemini API error (code={code}, status={status_str})",
        user_message=(
            "The AI provider returned a temporary service error. "
            "Your store dashboards and calculators remain available."
        ),
        details={"status_code": code},
    )
