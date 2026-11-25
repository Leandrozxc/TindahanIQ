# TindahanIQ

**TindahanIQ** is an AI-powered business intelligence assistant designed to help Filipino sari-sari store owners, neighborhood retailers, and micro-entrepreneurs make informed inventory, pricing, sales, and profitability decisions using their actual store records.

> **Current Milestone:** Phase 1 — Repository Initialization and Application Foundation  
> Core configuration, logging, error handling, Streamlit shell, and runtime health diagnostics are active. Business data ingestion, analytics engines, and AI consultation will be introduced incrementally across Phases 2–6.

---

## Prerequisites

- **Python 3.12+**
- **Git**

---

## Local Setup Instructions

1. **Create and activate a virtual environment** (from the repository root):

   **Windows (PowerShell):**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   **macOS / Linux:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install TindahanIQ and development tools in editable mode:**

   ```powershell
   python -m pip install --upgrade pip
   pip install -e ".[dev]"
   ```

3. **Configure environment variables:**

   Copy `.env.example` to `.env` (optional for Phase 1; sensible local defaults are built in):
   ```powershell
   Copy-Item .env.example .env
   ```
   > Never commit `.env` or real API keys to Git. `GEMINI_API_KEY` is optional until Phase 5.

---

## Running the Application

Start the Streamlit application from the repository root (with `.venv` activated):

```powershell
streamlit run src/tindahaniq/app.py
```

- **Interactive UI:** `http://localhost:8501`
- **JSON Health Probe:** `http://localhost:8501/?healthz=1`

---

## Testing & Code Quality

Run the automated test suite with coverage:

```powershell
pytest --cov=tindahaniq --cov-report=term-missing
```

Run linting and formatting checks:

```powershell
ruff check .
ruff format --check .
```

---

## Project Structure (Phase 1)

```text
tindahanIQ/
├── .env.example                  # Environment variable template (safe to commit)
├── .gitignore                    # Excludes secrets, .venv, local SQLite DBs, caches
├── pyproject.toml                # Package metadata, dependencies, pytest & ruff config
├── README.md                     # Setup and developer guide
├── data/                         # Runtime local SQLite storage directory (*.db gitignored)
├── src/
│   └── tindahaniq/
│       ├── __init__.py           # Package version
│       ├── app.py                # Streamlit entry point & System Health UI
│       ├── config.py             # Typed Pydantic Settings & SecretStr API key protection
│       ├── exceptions.py         # Domain exception hierarchy & user-safe messages
│       ├── health.py             # Deterministic runtime & storage health checks
│       └── logging_config.py     # Rerun-safe structured logging configuration
└── tests/
    ├── conftest.py               # Isolated environment fixtures
    ├── unit/                     # Configuration, exceptions, logging & health unit tests
    └── integration/              # Headless Streamlit AppTest smoke tests
```
