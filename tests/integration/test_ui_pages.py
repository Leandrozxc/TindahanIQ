"""Multi-page headless Streamlit AppTest suite verifying empty and populated UX flows."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from tindahaniq.config import PROJECT_ROOT

APP_SCRIPT = str(PROJECT_ROOT / "src" / "tindahaniq" / "app.py")


def test_navigation_across_all_pages_on_empty_and_populated_store(
    isolated_env: Path,
) -> None:
    at = AppTest.from_file(APP_SCRIPT)
    at.run(timeout=25)
    assert not at.exception

    # 1. Empty store onboarding: navigate across pages safely with 0 products
    for nav_key in (
        "nav_ai_assistant",
        "nav_inventory",
        "nav_sales_profit",
        "nav_pricing_sim",
        "nav_upload_data",
        "nav_system_help",
        "nav_dashboard",
    ):
        at.button(key=nav_key).click().run(timeout=25)
        assert not at.exception

    # 2. Click "Load Sample Sari-Sari Store Dataset (Demo)" from empty Dashboard onboarding
    at.button(key="dash_load_sample").click().run(timeout=25)
    assert not at.exception
    metric_values = [m.value for m in at.metric]
    assert "10" in metric_values
    assert "₱455.00" in metric_values

    # 3. Verify AI Assistant split view renders KPI strip, insights rail, and missing-key notice
    at.button(key="nav_ai_assistant").click().run(timeout=25)
    assert not at.exception
    assert any("AI Business Assistant" in t.value for t in at.title)
    assert len(at.warning) >= 1

    # 4. Verify Inventory Intelligence & Budget Planner tabs render cleanly
    at.button(key="nav_inventory").click().run(timeout=25)
    assert not at.exception
    assert any("Inventory & Restock Management" in t.value for t in at.title)
    assert len(at.dataframe) >= 2

    # 5. Verify Sales Analytics & Profitability Analyzer charts and tables
    at.button(key="nav_sales_profit").click().run(timeout=25)
    assert not at.exception
    assert any("Sales Analytics & Profitability" in t.value for t in at.title)

    # 6. Verify Pricing Simulator interactive calculation & mode switch
    at.button(key="nav_pricing_sim").click().run(timeout=25)
    assert not at.exception
    assert any("Pricing Simulator" in t.value for t in at.title)
    at.radio(key="sim_mode_radio").set_value("Change by Percentage (%)").run(timeout=25)
    assert not at.exception

    # 7. Verify Upload Data batch history & Settings/Consistency check
    at.button(key="nav_upload_data").click().run(timeout=25)
    assert not at.exception
    assert len(at.dataframe) >= 1

    at.button(key="nav_system_help").click().run(timeout=25)
    assert not at.exception
    assert len(at.success) >= 1
