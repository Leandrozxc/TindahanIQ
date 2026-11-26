# Project Instructions

## Stack & Architecture Reference

TindahanIQ is a **Python 3.12+ / Streamlit** single-store retail BI monolith deployed on **Streamlit Community Cloud** with **Turso (libSQL)** in production and local **SQLite 3** in dev/test.

Before making architectural, domain, or UI changes, consult these canonical references:
- **Tech Stack & Production Contracts:** `docs/tech-stack.md`
- **System Architecture & Schema:** `docs/architecture.md` and `docs/adr/`
- **Domain Terminology:** `GLOSSARY.md`
- **BI Formulas:** `docs/formulas.md`

## UI / UX Standards

Before performing any UI/UX work:
1. Read `UI_DESIGN_GUIDELINES.md` and treat its standards as mandatory.
2. Use the approved Streamlit UI stack: **Streamlit `>=1.40`** with **native Material Symbols (`:material/...:`)**, **`streamlit-shadcn-ui`**, **`streamlit-antd-components`**, **Plotly**, and `src/tindahaniq/ui/theme.py`.
3. **Never use emojis as UI icons**; always use `:material/...:` or component icons.
4. Preserve existing four-layer boundaries (no SQL or financial arithmetic in `ui/` or `ai/`), make all visible interactions functional, and verify with `pytest` and `ruff`.
