"""Typed Streamlit session_state management for navigation, preferences, and chat."""

from __future__ import annotations

from typing import Literal

import streamlit as st

from tindahaniq.config import AppSettings
from tindahaniq.models.ai import ConversationSession

PageKey = Literal[
    "dashboard",
    "ai_assistant",
    "inventory",
    "sales_profit",
    "pricing_sim",
    "upload_data",
    "system_help",
]

PAGE_ITEMS: tuple[tuple[PageKey, str], ...] = (
    ("dashboard", "📊  Dashboard"),
    ("ai_assistant", "🤖  AI Assistant"),
    ("inventory", "📦  Inventory"),
    ("sales_profit", "📈  Sales Analytics"),
    ("pricing_sim", "🏷️  Pricing Simulator"),
    ("upload_data", "📤  Upload Data"),
    ("system_help", "⚙️  Settings & Help"),
)

VALID_PAGES: frozenset[str] = frozenset(key for key, _ in PAGE_ITEMS)


def init_session_state(settings: AppSettings) -> None:
    """Initialize required session_state keys idempotently on each script run."""
    if "active_page" not in st.session_state or st.session_state["active_page"] not in VALID_PAGES:
        st.session_state["active_page"] = "dashboard"
    if "store_display_name" not in st.session_state:
        st.session_state["store_display_name"] = settings.store_name
    if "lookback_days" not in st.session_state:
        st.session_state["lookback_days"] = 14
    if "coverage_days" not in st.session_state:
        st.session_state["coverage_days"] = 7
    if "chat_session" not in st.session_state or not isinstance(
        st.session_state["chat_session"], ConversationSession
    ):
        st.session_state["chat_session"] = ConversationSession(
            store_name=str(st.session_state["store_display_name"])
        )
    if "pending_ai_prompt" not in st.session_state:
        st.session_state["pending_ai_prompt"] = None
    if "flash_success" not in st.session_state:
        st.session_state["flash_success"] = None


def get_active_page() -> PageKey:
    """Return the currently selected navigation page key."""
    page = str(st.session_state.get("active_page", "dashboard"))
    if page in VALID_PAGES:
        return page  # type: ignore[return-value]
    return "dashboard"


def navigate_to(page: PageKey) -> None:
    """Switch the active navigation view."""
    if page in VALID_PAGES:
        st.session_state["active_page"] = page


def get_chat_session() -> ConversationSession:
    """Return the active user's ConversationSession instance."""
    session = st.session_state["chat_session"]
    assert isinstance(session, ConversationSession)
    session.store_name = str(st.session_state.get("store_display_name", session.store_name))
    return session


def consume_flash_success() -> str | None:
    """Pop and return a one-time success notification if queued."""
    msg = st.session_state.get("flash_success")
    st.session_state["flash_success"] = None
    return str(msg) if msg else None


def set_flash_success(message: str) -> None:
    """Queue a one-time success banner across `st.rerun()`."""
    st.session_state["flash_success"] = message
