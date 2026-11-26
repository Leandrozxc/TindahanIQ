# TindahanIQ: An AI-Powered Business Assistant for Small Retailers

**Course project:** CS365-F1 Final Project  
**Authors / Instructor:** Alegarbes, Duff Daren; Endrina, Arth Andrey C.; Macadangdang, Yoji C.; Pabatao, Leandro Miguel A.; Racaza, Psalm Elly • Instructor: Jun Albert S. Pardillo

---

## Overview

**TindahanIQ** is an AI-powered business intelligence assistant built with Python and Streamlit for Filipino **sari-sari store owners, neighborhood retailers, and micro-entrepreneurs**. It combines deterministic base-10 `Decimal` financial analytics with a tool-calling OpenAI-compatible AI Business Consultant so small retailers can understand their actual store records and make informed inventory, pricing, and profitability decisions in plain language.

### Core Modules

1. **Inventory Intelligence** — Detects out-of-stock and low-stock items (`CRITICAL`, `HIGH`, `LOW`, `HEALTHY`), calculates historical daily sales velocity and days until depletion, recommends whole-unit restock quantities, and allocates restocking priorities within a fixed PHP (`₱`) working-capital budget.
2. **Profitability Analyzer** — Deterministically computes gross revenue, Cost of Goods Sold (COGS), gross profit (`₱`), **gross profit margin (`%`)**, and **markup (`%`)** across individual products, categories, and the entire store.
3. **Sales Analytics** — Identifies top-selling and slow/zero-moving products, aggregates daily/weekly/monthly trends, calculates period-over-period growth deltas, and detects peak sales hours.
4. **Pricing Simulator** — Models hypothetical selling-price changes (`±₱` amount, target price, or `±%`) with optional customer volume sensitivity and breakeven volume calculations before shelf prices are changed.
5. **AI Business Consultant** — Answers natural-language retail questions grounded strictly in read-only deterministic calculation tools (zero numerical hallucination or mental math), with prompt-injection defenses for untrusted CSV uploads.

### Scope Boundaries (What TindahanIQ Does NOT Do)

- Does **not** execute supplier purchases, orders, or external financial transactions.
- Does **not** guarantee future sales, demand, or financial forecasts.
- Does **not** collect, store, or access private banking, e-wallet, or payment credentials.
- Does **not** replace certified accounting, legal, or tax advisory services.
- Never invents inventory counts, prices, or financial figures.

---

## Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Runtime** | Python `3.12+` | Core application language & exact `decimal.Decimal` math |
| **Web UI** | Streamlit (`>=1.40`), `streamlit-shadcn-ui`, `streamlit-antd-components` | Multipage dashboard, native `:material/...:` icons, split-view AI workspace & forms |
| **Persistence (Dev/Test)** | SQLite 3 (`sqlite3` stdlib) | Serverless local ACID relational storage (WAL + Foreign Keys) |
| **Persistence (Prod)** | Turso (libSQL via `httpx` Hrana v2) | Durable remote SQLite-compatible storage surviving Streamlit Cloud restarts |
| **Validation & Config** | Pydantic v2 + `pydantic-settings` | Strict domain schemas, CSV validation, `st.secrets` + `.env`, & `SecretStr` masking |
| **Data & CSV** | Pandas (`>=2.2`) | CSV encoding/header normalization & tabular display |
| **Visualization** | Plotly (`>=5.24`) | Interactive `₱`-formatted trend, category & simulation charts |
| **AI Integration** | OpenAI Python SDK (`openai`) | `gpt-6-luna` tool calling, `30s` timeout, `2` jittered retries, & optional fallback |
| **Quality & Tests** | `pytest`, `pytest-cov`, `ruff`, `AppTest` | Unit, integration, UI workflow, security & performance verification |

---

## Local Setup & Installation

### 1. Clone the Repository & Create a Virtual Environment

**Windows (PowerShell):**
```powershell
git clone https://github.com/Leandrozxc/TindahanIQ.git
cd TindahanIQ
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
git clone https://github.com/Leandrozxc/TindahanIQ.git
cd TindahanIQ
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```powershell
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

### 3. Configure Environment Variables

Copy `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and add your OpenAI-compatible API key (`OPENAI_API_KEY`) to enable the conversational AI Business Consultant:

```env
APP_NAME=TindahanIQ
APP_ENV=development
LOG_LEVEL=INFO
STORE_NAME=My Sari-Sari Store
CURRENCY_SYMBOL=₱
CURRENCY_CODE=PHP
DATABASE_PATH=data/tindahaniq.db
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://aiki-labs.up.railway.app/api/v1
OPENAI_MODEL=gpt-6-luna
OPENAI_MAX_COMPLETION_TOKENS=1024
```

> **Note:** Never commit `.env` to Git. All non-AI modules (Dashboard, Inventory & Budget Planner, Sales & Profitability Analytics, Pricing Simulator, and CSV Upload) work 100% offline even without an API key.

---

## Running the Application

```powershell
streamlit run src/tindahaniq/app.py
```

- **Web Interface:** `http://localhost:8501`
- **JSON Health Check:** `http://localhost:8501/?healthz=1`

---

## Production Deployment (Streamlit Community Cloud + Turso)

1. **Create a Turso Database:** Create a database in [Turso](https://turso.tech/) and generate an auth token (`TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`).
2. **Deploy on Streamlit Community Cloud:**
   - **Repository / Branch:** Your GitHub repository & target branch (`requirements.txt` and `pyproject.toml` are both at repo root).
   - **Main file path:** `src/tindahaniq/app.py`
   - **Python version:** `3.12` (or `3.13+`).
3. **Configure App Secrets (Settings → Secrets):**

```toml
APP_ENV = "production"
LOG_LEVEL = "INFO"
STORE_NAME = "My Sari-Sari Store"
CURRENCY_SYMBOL = "₱"
CURRENCY_CODE = "PHP"

TURSO_DATABASE_URL = "libsql://your-db-name.turso.io"
TURSO_AUTH_TOKEN = "your-turso-auth-token"

OPENAI_API_KEY = "your-primary-api-key"
OPENAI_BASE_URL = "https://aiki-labs.up.railway.app/api/v1"
OPENAI_MODEL = "gpt-6-luna"
OPENAI_MAX_COMPLETION_TOKENS = 1024

# Optional secondary fallback provider if primary proxy is unavailable
OPENAI_FALLBACK_BASE_URL = ""
OPENAI_FALLBACK_MODEL = ""
OPENAI_FALLBACK_API_KEY = ""
```

4. **Verify Production Health:** Open `https://<your-app>.streamlit.app/?healthz=1` and confirm `"overall_status": "healthy"` with `"Turso Persistence": "ok"` and `"AI Provider Key": "ok"`.

---

## Sample CSV Datasets

Ready-to-use Filipino sari-sari store CSV datasets are located in `data/samples/`:

- `data/samples/demo_sari_sari_inventory.csv` & `data/samples/demo_sari_sari_sales_14d.csv` — **18-product, 6-category, 14-day presentation dataset** ideal for live classroom demonstrations of week-over-week trends, slow movers, and `₱2,000` budget restock planning.
- `data/samples/sample_inventory.csv` & `data/samples/sample_sales.csv` — Compact 10-product baseline dataset (also loadable in one click from the empty-store onboarding card).

### Supported CSV Columns
- **Inventory CSV:** `product_name` *(req)*, `unit_cost` *(req)*, `selling_price` *(req)*, `current_stock` *(req)*, plus optional `sku`, `category`, `unit`, `reorder_point`, `lead_time_days` (also accepts common aliases such as `pangalan`, `puhunan`, `presyo`, `stock`).
- **Sales CSV:** `sold_at` / `date` *(req)*, `sku` or `product_name` *(req)*, `quantity_sold` *(req)*, plus optional `transaction_id` / `receipt_no` and `unit_price`.

---

## Automated Testing & Code Quality

Run the full unit, integration, security, UI, and performance test suite:

```powershell
pytest --cov=tindahaniq --cov-report=term-missing
```

Run linter and code formatting checks:

```powershell
ruff check .
ruff format --check .
```

---

## Technical Documentation

- [Production Architecture & Tech Stack Reference](docs/tech-stack.md)
- [System Architecture & Data Model](docs/architecture.md)
- [Architecture Decision Records](docs/adr/)
- [Domain Glossary](GLOSSARY.md)
- [Authoritative Business Intelligence Formulas](docs/formulas.md)
- [Phase 7 Quality Assurance & Security Report](docs/qa_report.md)
- [Live Demonstration Guide & Submission Checklist](docs/demo_checklist.md)
