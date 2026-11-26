# 04: Material Symbols and shadcn/Antd UI refresh

**What to build:** All emoji UI icons across navigation, Store header, KPI cards, insights, and action controls are replaced with native Streamlit Material Symbols (`:material/...:`), and core views adopt `streamlit-shadcn-ui` and `streamlit-antd-components` for a cohesive, non-emoji interface with full interactive workflow parity.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Zero emojis remain as UI icons across the sidebar, page headers, KPI strips, insight cards, and buttons (replaced with `:material/...:` or component icons).
- [x] `streamlit-shadcn-ui` and `streamlit-antd-components` are integrated into the approved UI stack and used cleanly alongside Plotly and the existing CSS theme.
- [x] All Streamlit `AppTest` UI workflow tests, `pytest`, and `ruff` checks pass with zero regressions.
