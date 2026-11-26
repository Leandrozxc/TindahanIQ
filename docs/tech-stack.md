# TindahanIQ — Production Architecture & Tech Stack Reference

> **Canonical Agent Reference:** This document defines the authoritative technology stack, production architecture, runtime contracts, and engineering standards for **TindahanIQ**. All code, dependencies, and UI work must align with this reference.

---

## 1. System Scope & Shape

- **Product:** Single-store, local-first retail Business Intelligence & AI Advisory assistant for Filipino sari-sari stores.
- **Topology:** Single-process Python/Streamlit monolith deployed on **Streamlit Community Cloud** with durable external **Turso (libSQL)** persistence in `production` and local **SQLite 3** in `development`/`testing`.
- **Non-Goals:** Multi-tenant auth/accounts, external POS/payment execution, or LLM-generated SQL/arithmetic.

---

## 2. Official Technology Stack

| Layer | Technology / Library | Status | Role & Constraints |
| :--- | :--- | :--- | :--- |
| **Runtime & Packaging** | Python `>=3.12`, `pyproject.toml`, `requirements.txt` | Existing + Prod | Core language; `pyproject.toml` is source of truth, `requirements.txt` supports Streamlit Cloud builds. |
| **Web Framework** | Streamlit (`>=1.40,<2.0`) | Existing | Multipage shell (`ui/shell.py`), session state (`ui/state.py`), `@st.cache_resource` / `@st.cache_data`, `?healthz=1` probe. |
| **UI & Icon Extensions** | Native `:material/...:` Symbols, `streamlit-shadcn-ui`, `streamlit-antd-components`, `ui/theme.py` | Target Prod | Cohesive non-emoji icon system, cards, badges, segmented controls, and CSS tokens. **Zero emojis as UI icons.** |
| **Data Visualization** | Plotly (`>=5.24,<7.0`) | Existing | Interactive `₱`-formatted trend, category, and pricing simulation charts (`ui/components/charts.py`). |
| **Data & CSV Processing** | Pandas (`>=2.2,<4.0`), stdlib `csv`, `hashlib` | Existing | CSV encoding/header normalization, tabular display, SHA-256 duplicate batch detection. |
| **Validation & Config** | Pydantic v2 (`>=2.9`), `pydantic-settings` (`>=2.6`), `python-dotenv` | Existing | Strict domain/analytics schemas, `SecretStr` masking, `.env` (local) + `st.secrets` (Streamlit Cloud). |
| **Arithmetic Precision** | Python `decimal.Decimal` (`ROUND_HALF_UP`) | Existing | Exact base-10 financial math (`1 PHP = 100 centavos`). Never use `float` for money. |
| **Persistence (Local)** | SQLite 3 (`sqlite3` stdlib, WAL + FK) | Existing | Local `development` (`data/tindahaniq.db`) and `testing` (`:memory:`). |
| **Persistence (Prod)** | Turso (`libsql` / `libsql-experimental`) | Target Prod | Durable remote SQLite-compatible storage surviving Streamlit Cloud container restarts (`TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`). |
| **AI / LLM Integration** | OpenAI Python SDK (`openai>=1.50,<3.0`) | Existing | Chat Completions tool calling (`gpt-6-luna` via `OPENAI_BASE_URL`), 5-round loop, 7 read-only BI tools. |
| **Testing & Quality** | `pytest`, `pytest-cov`, Streamlit `AppTest`, `ruff` | Existing | Unit, integration, UI workflow, security, and performance tests; lint & format (`line-length = 100`). |

---

## 3. Production Architecture & Runtime Contracts

### 3.1 Four-Layer Unidirectional Architecture

Dependencies flow strictly downward:
1. **Presentation (`src/tindahaniq/ui/`):** `app.py`, `shell.py`, 7 pages (`ui/pages/`), reusable components (`ui/components/`). Never performs BI math or SQL.
2. **AI Orchestration (`src/tindahaniq/ai/`):** `AIConsultantService`, `OpenAIProvider`, `BusinessToolRegistry` (7 read-only tools), `sanitizer.py`, `prompts.py`.
3. **Domain & BI (`src/tindahaniq/services/`):** Deterministic `bi/formulas.py`, BI analyzers (`profitability.py`, `sales_analytics.py`, `inventory_intel.py`, `pricing_sim.py`), and operational services (`inventory_service.py`, `sales_service.py`, `consistency_service.py`, `csv_importer.py`).
4. **Persistence & Models (`src/tindahaniq/db/`, `models/`, `utils/`):** `DatabaseManager`, parameterized `?` repositories (`ProductRepository`, `SalesRepository`, `ImportBatchRepository`), Pydantic v2 schemas, `schema.sql`.

### 3.2 Persistence, Caching & Rerun Performance

- **Environment Routing:**
  - `development` / `testing`: Local SQLite via `DATABASE_PATH` (WAL mode, `PRAGMA foreign_keys = ON`, `BEGIN IMMEDIATE`).
  - `production`: Turso (`TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN`), preserving the exact `schema.sql` DDL and `?` parameterized queries.
- **Streamlit Caching Strategy:**
  - Use `@st.cache_resource` for `DatabaseManager` initialization and one-time `initialize_schema()` so schema DDL does not re-execute on every UI rerun.
  - Use `@st.cache_data` for read-heavy BI queries, explicitly clearing cached data on any write (`CSVImportService`, `InventoryService`, `SalesService`, `reset_store_data()`).

### 3.3 Configuration & Secrets Contract

- **Local (`development`):** Loaded from `.env` via `AppSettings` (`pydantic-settings`).
- **Streamlit Community Cloud (`production`):** Configured in **Streamlit Secrets** (`st.secrets`) and mirrored/loaded into `AppSettings` without exposing secrets in logs or UI.
- **Required/Optional Keys:**
  - `APP_ENV` (`development` | `testing` | `production`), `LOG_LEVEL`, `STORE_NAME`, `CURRENCY_SYMBOL` (`₱`), `CURRENCY_CODE` (`PHP`)
  - `DATABASE_PATH` (local) / `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN` (production)
  - `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_MAX_COMPLETION_TOKENS`
  - Optional fallback: `OPENAI_FALLBACK_BASE_URL`, `OPENAI_FALLBACK_MODEL`, `OPENAI_FALLBACK_API_KEY`
- **Health Probe:** `/?healthz=1` returns deterministic JSON health status (`src/tindahaniq/health.py`).

### 3.4 AI Resilience & Security Policy

- **Timeouts & Retries:** `OpenAIProvider` enforces `timeout=30.0`s (`connect=5.0`s) and `max_retries=2` with short exponential backoff + jitter on `429`, `502`, `503`, `504`, `APIConnectionError`, and `APITimeoutError`.
- **Fallback Chain:**
  1. Native OpenAI-compatible tool calling (up to 5 rounds).
  2. Automatic deterministic pre-grounding (`_build_grounded_fallback_context()`) if the endpoint omits tool calls.
  3. Optional secondary OpenAI-compatible fallback (`OPENAI_FALLBACK_*`) if primary fails.
  4. Graceful user-safe `AIServiceError` message; all non-AI BI dashboards remain 100% functional.
- **Security Guardrails:** Input prompt sanitization, CSV untrusted-string scrubbing (`<system>`, `[INST]`, control chars, `_data_notice` fencing), CSV formula-injection escaping (`escape_csv_formula()`), `SecretStr` output scrubbing, and parameterized SQL (`LIKE` wildcards escaped).

---

## 4. Verification & Deployment Commands

```powershell
# Run full test suite with coverage
pytest --cov=tindahaniq --cov-report=term-missing

# Lint and format check
ruff check .
ruff format --check .

# Run locally
streamlit run src/tindahaniq/app.py
```

---

## 5. Related Documentation

- [Domain Glossary](../GLOSSARY.md) — Canonical business terminology (`Store`, `Product`, `SKU`, `Sales Transaction`, `Stock Adjustment`, `Restock`, `Spoilage`).
- [System Architecture & Data Model](architecture.md) — Layer diagram, invariants, and SQL schema summary.
- [Authoritative BI Formulas](formulas.md) — Exact `Decimal` formulas for profitability, sales, inventory, and pricing.
- [Architecture Decision Records](adr/) — `0001` (Turso), `0002` (Streamlit + Material/shadcn UI), `0003` (Deterministic BI & AI guardrails).
- [UI Design Guidelines](../UI_DESIGN_GUIDELINES.md) — Visual hierarchy, anti-AI-slop rules, and accessibility standards.
