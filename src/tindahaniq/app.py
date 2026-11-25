"""Streamlit application entry point for TindahanIQ (Phase 1 Foundation)."""

from __future__ import annotations

import streamlit as st

from tindahaniq import __version__
from tindahaniq.config import AppSettings, load_settings
from tindahaniq.exceptions import get_user_safe_message
from tindahaniq.health import CheckStatus, SystemHealthReport, run_health_checks
from tindahaniq.logging_config import configure_logging, get_logger

STATUS_BADGES: dict[CheckStatus, str] = {
    "ok": "PASS",
    "notice": "NOTICE",
    "error": "FAIL",
}


def _render_sidebar(settings: AppSettings, report: SystemHealthReport) -> None:
    with st.sidebar:
        st.title(settings.app_name)
        st.caption("Smarter Business Decisions for Small Retailers")
        st.divider()
        st.markdown(f"**Active Store:** {settings.store_name}")
        st.markdown(f"**Default Currency:** {settings.currency_symbol} ({settings.currency_code})")
        st.markdown(f"**Environment:** `{settings.app_env}`")
        st.markdown(f"**Version:** `v{__version__}`")
        st.divider()
        if report.overall_status == "healthy":
            st.success("System Status: Healthy")
        else:
            st.error("System Status: Degraded")
        st.info(
            "Phase 1 Foundation initialized. Business intelligence modules will be "
            "enabled incrementally across Phases 2–6."
        )


def _render_health_panel(report: SystemHealthReport) -> None:
    st.subheader("System Health & Environment Diagnostics")

    col_status, col_env, col_ver = st.columns(3)
    col_status.metric("Overall Health", report.overall_status.upper())
    col_env.metric("Environment", report.environment)
    col_ver.metric("Application Version", f"v{report.app_version}")

    rows = [
        {
            "Check": item.name,
            "Status": STATUS_BADGES[item.status],
            "Details": item.detail,
        }
        for item in report.checks
    ]
    st.table(rows)
    st.caption(f"Last verified (UTC): {report.checked_at_utc}")


def main() -> None:
    """Initialize configuration, logging, and render the TindahanIQ application shell."""
    st.set_page_config(
        page_title="TindahanIQ — Business Intelligence Assistant",
        page_icon="🏪",
        layout="wide",
    )

    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        logger = get_logger("app")

        report = run_health_checks(settings)
        logger.debug("Health check completed with status=%s", report.overall_status)

        if st.query_params.get("healthz") == "1":
            st.json(report.to_dict())
            st.stop()

        _render_sidebar(settings, report)

        st.title(f"{settings.app_name} — Application Foundation")
        st.markdown(
            "Welcome to **TindahanIQ**, an AI-powered business intelligence assistant "
            "built for Filipino sari-sari store owners and neighborhood retailers."
        )
        st.divider()
        _render_health_panel(report)

    except Exception as exc:
        fallback_logger = configure_logging("ERROR")
        fallback_logger.exception("Unhandled error during application startup")
        st.error(get_user_safe_message(exc))


if __name__ == "__main__":
    main()
