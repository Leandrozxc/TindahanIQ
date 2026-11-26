"""Conversational AI Business Consultant orchestrator with deterministic tool execution."""

from __future__ import annotations

import json
import re

from tindahaniq.ai.prompts import build_system_instruction
from tindahaniq.ai.provider import LLMProvider, OpenAIProvider
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
    ToolCallRequest,
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
        store_name: str | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._provider = provider
        self._max_tool_rounds = max(1, max_tool_rounds)
        effective_store = (store_name or settings.store_name).strip() or settings.store_name
        self._tools = BusinessToolRegistry(db, store_name=effective_store)
        self._logger = get_logger("ai_consultant")

    def _get_provider(self) -> LLMProvider:
        if self._provider is None:
            self._provider = OpenAIProvider(self._settings)
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
                if _round == 0 and data_available and not invoked_tool_names:
                    grounded_block, grounded_tools = self._build_grounded_fallback_context(
                        clean_prompt
                    )
                    invoked_tool_names.extend(grounded_tools)
                    fallback_turn = provider.generate_turn(
                        conversation=working_history,
                        current_turn_steps=(),
                        system_instruction=f"{system_instruction}\n\n{grounded_block}",
                        tools=(),
                    )
                    final_text = fallback_turn.text or turn.text
                else:
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
        if self._settings.openai_api_key is not None:
            secrets_to_scrub.append(self._settings.openai_api_key.get_secret_value())
        if self._settings.openai_fallback_api_key is not None:
            secrets_to_scrub.append(self._settings.openai_fallback_api_key.get_secret_value())

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

    def _build_grounded_fallback_context(self, user_prompt: str) -> tuple[str, list[str]]:
        """Pre-run deterministic BI tools when an OpenAI-compatible endpoint omits tool calling."""
        calls: list[ToolCallRequest] = [
            ToolCallRequest(call_id="fb_overview", name="get_store_overview", arguments={}),
            ToolCallRequest(
                call_id="fb_profit",
                name="analyze_profitability",
                arguments={"sort_by": "gross_profit", "top_n": 15},
            ),
            ToolCallRequest(
                call_id="fb_sales",
                name="analyze_sales_trends",
                arguments={"granularity": "daily", "top_n": 8},
            ),
            ToolCallRequest(
                call_id="fb_restock",
                name="get_restock_recommendations",
                arguments={"needs_restock_only": False},
            ),
        ]

        budget_match = re.search(r"(?:₱|php)?\s*([\d,]+(?:\.\d+)?)", user_prompt, re.IGNORECASE)
        if "budget" in user_prompt.lower() or "restock" in user_prompt.lower():
            budget_val = 2000.0
            if budget_match:
                try:
                    parsed = float(budget_match.group(1).replace(",", ""))
                    if parsed >= 50:
                        budget_val = parsed
                except ValueError:
                    pass
            calls.append(
                ToolCallRequest(
                    call_id="fb_budget",
                    name="plan_budget_restock",
                    arguments={"budget_php": budget_val},
                )
            )

        results: dict[str, object] = {}
        used: list[str] = []
        for call in calls:
            self._logger.info("Fallback deterministic tool `%s`", call.name)
            res = self._tools.execute(call)
            results[call.name] = res.payload
            used.append(call.name)

        block = (
            "## 9. Grounded Deterministic Store Data\n"
            "Native tool calling was unavailable on this model endpoint, so TindahanIQ "
            "executed its deterministic BI tools for you below. Answer strictly using these "
            "authoritative figures and do NOT claim tools are unavailable:\n"
            f"```json\n{json.dumps(results, ensure_ascii=False)}\n```"
        )
        return block, used
