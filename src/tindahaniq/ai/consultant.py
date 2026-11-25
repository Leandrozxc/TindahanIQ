"""Conversational AI Business Consultant orchestrator with deterministic tool execution."""

from __future__ import annotations

from tindahaniq.ai.prompts import build_system_instruction
from tindahaniq.ai.provider import GeminiProvider, LLMProvider
from tindahaniq.ai.sanitizer import sanitize_user_prompt, scrub_sensitive_output
from tindahaniq.ai.tools import BusinessToolRegistry
from tindahaniq.config import AppSettings
from tindahaniq.db.connection import DatabaseManager
from tindahaniq.exceptions import AIServiceError
from tindahaniq.logging_config import get_logger
from tindahaniq.models.ai import (
    ChatMessage,
    ConsultantResponse,
    ConversationSession,
    ProviderTurnResult,
    ToolResultMessage,
)


class AIConsultantService:
    """Coordinate user queries, live store context, deterministic BI tools, and LLM turns."""

    def __init__(
        self,
        db: DatabaseManager,
        settings: AppSettings,
        *,
        provider: LLMProvider | None = None,
        max_tool_rounds: int = 5,
    ) -> None:
        self._db = db
        self._settings = settings
        self._provider = provider
        self._max_tool_rounds = max(1, max_tool_rounds)
        self._tools = BusinessToolRegistry(db, store_name=settings.store_name)
        self._logger = get_logger("ai_consultant")

    def _get_provider(self) -> LLMProvider:
        if self._provider is None:
            self._provider = GeminiProvider(self._settings)
        return self._provider

    def ask(
        self,
        user_prompt: str,
        *,
        session: ConversationSession | None = None,
    ) -> ConsultantResponse:
        """Answer a business question grounded in deterministic tool calls."""
        clean_prompt = sanitize_user_prompt(user_prompt)
        provider = self._get_provider()

        snapshot = self._tools.get_store_snapshot()
        data_available = int(snapshot.get("active_products", 0)) > 0
        system_instruction = build_system_instruction(snapshot)
        tool_specs = self._tools.tool_specs()

        user_msg = ChatMessage(role="user", content=clean_prompt)
        working_history = [*session.messages, user_msg] if session is not None else [user_msg]

        steps: list[tuple[ProviderTurnResult, list[ToolResultMessage]]] = []
        invoked_tool_names: list[str] = []
        warnings: list[str] = []
        if not data_available:
            warnings.append(
                "No store inventory or sales records are loaded yet. "
                "Upload CSV files or add products for store-specific analysis."
            )

        final_text: str | None = None

        for _round in range(self._max_tool_rounds):
            turn = provider.generate_turn(
                conversation=working_history,
                current_turn_steps=steps,
                system_instruction=system_instruction,
                tools=tool_specs,
            )
            if not turn.tool_calls:
                final_text = turn.text
                break

            round_results: list[ToolResultMessage] = []
            for call in turn.tool_calls:
                self._logger.info("Executing AI tool `%s`", call.name)
                invoked_tool_names.append(call.name)
                result = self._tools.execute(call)
                round_results.append(result)
            steps.append((turn, round_results))
        else:
            # Tool round ceiling reached; request final natural-language synthesis without tools
            synthesis_turn = provider.generate_turn(
                conversation=working_history,
                current_turn_steps=steps,
                system_instruction=system_instruction,
                tools=(),
            )
            final_text = synthesis_turn.text

        if not final_text or not final_text.strip():
            raise AIServiceError(
                "LLM returned empty final answer after tool execution",
                user_message=(
                    "TindahanIQ could not complete a response for that question. "
                    "Please try asking again."
                ),
            )

        secrets_to_scrub: list[str] = []
        if self._settings.gemini_api_key is not None:
            secrets_to_scrub.append(self._settings.gemini_api_key.get_secret_value())

        safe_answer = scrub_sensitive_output(final_text.strip(), secret_values=secrets_to_scrub)
        unique_tools = tuple(dict.fromkeys(invoked_tool_names))

        if session is not None:
            session.append(user_msg)
            session.append(
                ChatMessage(
                    role="assistant",
                    content=safe_answer,
                    tools_used=unique_tools,
                )
            )

        return ConsultantResponse(
            answer=safe_answer,
            tools_used=unique_tools,
            data_available=data_available,
            warnings=tuple(warnings),
        )
