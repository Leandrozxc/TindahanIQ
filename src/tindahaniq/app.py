"""Streamlit application entry point for TindahanIQ."""

from __future__ import annotations

import streamlit as st

from tindahaniq.config import load_settings
from tindahaniq.exceptions import get_user_safe_message
from tindahaniq.health import run_health_checks
from tindahaniq.logging_config import configure_logging, get_logger
from tindahaniq.ui import run_ui


def main() -> None:
    """Initialize configuration, logging, health probe, and render the TindahanIQ UI."""
    st.set_page_config(
        page_title="TindahanIQ — Smarter Business Decisions",
        page_icon="🏪",
        layout="wide",
    )

    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        logger = get_logger("app")

        if st.query_params.get("healthz") == "1":
            report = run_health_checks(settings)
            logger.debug("Health probe status=%s", report.overall_status)
            st.json(report.to_dict())
            st.stop()

        run_ui(settings)

    except Exception as exc:
        fallback_logger = configure_logging("ERROR")
        fallback_logger.exception("Unhandled error during Streamlit execution")
        st.error(get_user_safe_message(exc))


if __name__ == "__main__":
    main()
