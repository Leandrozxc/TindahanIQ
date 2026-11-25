"""Pydantic models and session state containers for the AI Business Consultant."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ChatRole = Literal["user", "assistant"]


class ToolSpec(BaseModel):
    """JSON-schema declaration for a deterministic read-only business tool."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters_schema: dict[str, Any]


class ToolCallRequest(BaseModel):
    """Single function/tool invocation requested by the LLM."""

    model_config = ConfigDict(frozen=True)

    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResultMessage(BaseModel):
    """Structured deterministic output returned from executing a tool call."""

    model_config = ConfigDict(frozen=True)

    call_id: str
    name: str
    payload: dict[str, Any]


class ProviderTurnResult(BaseModel):
    """Normalized single-step output from an LLM provider."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    text: str | None = None
    tool_calls: tuple[ToolCallRequest, ...] = ()
    raw_model_content: Any | None = None


class ChatMessage(BaseModel):
    """Immutable message stored in a user-assistant consultation session."""

    model_config = ConfigDict(frozen=True)

    role: ChatRole
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tools_used: tuple[str, ...] = ()


class ConsultantResponse(BaseModel):
    """Final grounded response returned by `AIConsultantService.ask`."""

    model_config = ConfigDict(frozen=True)

    answer: str
    tools_used: tuple[str, ...] = ()
    data_available: bool = True
    warnings: tuple[str, ...] = ()


class ConversationSession:
    """Bounded in-memory conversation transcript with Markdown export support."""

    def __init__(
        self,
        *,
        store_name: str = "My Sari-Sari Store",
        max_messages: int = 40,
    ) -> None:
        self.store_name = store_name
        self.max_messages = max(2, max_messages)
        self._messages: list[ChatMessage] = []

    @property
    def messages(self) -> tuple[ChatMessage, ...]:
        """Return immutable snapshot of current conversation history."""
        return tuple(self._messages)

    def append(self, message: ChatMessage) -> None:
        """Append a message and trim oldest entries if exceeding `max_messages`."""
        self._messages.append(message)
        if len(self._messages) > self.max_messages:
            overflow = len(self._messages) - self.max_messages
            del self._messages[:overflow]

    def clear(self) -> None:
        """Remove all messages from the session history."""
        self._messages.clear()

    def export_markdown(self) -> str:
        """Export the session conversation to a clean Markdown document."""
        exported_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"# TindahanIQ — Consultation Transcript ({self.store_name})",
            f"_Exported: {exported_at}_",
            "",
        ]
        if not self._messages:
            lines.append("_No messages in this session._")
            return "\n".join(lines)

        for msg in self._messages:
            speaker = "Store Owner" if msg.role == "user" else "TindahanIQ Copilot"
            ts = msg.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
            lines.append(f"### {speaker} ({ts})")
            if msg.tools_used:
                tools_str = ", ".join(f"`{t}`" for t in msg.tools_used)
                lines.append(f"_Verified via tools: {tools_str}_")
                lines.append("")
            lines.append(msg.content)
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
