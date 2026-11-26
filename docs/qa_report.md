# TindahanIQ — Phase 7 Quality Assurance & Integration Testing Report

## 1. Executive Quality Summary

- **Overall Status:** **PASSED** (`94` automated tests passing, `0` failures, **92%** overall line coverage across `3,618` statements).
- **Linter & Formatting (`ruff`):** `0` errors across `86` tracked Python source and test files.
- **Data & Mathematical Integrity:** 100% deterministic `Decimal` arithmetic reconciled across product, category, store, and daily/weekly/monthly time-series aggregations, plus ledger conservation (`current_stock == SUM(inventory_adjustments.quantity_delta)`).

---

## 2. Defects Discovered & Resolved During Phase 7 QA

| Defect ID | Severity | Component | Description | Resolution & Regression Test |
| :--- | :--- | :--- | :--- | :--- |
| **DEFECT-01** | Medium (Security) | `ui/pages/inventory.py`, `utils/validation.py` | **CSV Formula Injection on Restock Export:** Exporting `tindahaniq_restock_list.csv` wrote untrusted product names directly without escaping spreadsheet formula prefixes (`=`, `+`, `-`, `@`), posing an Excel formula execution risk if malicious CSV names were imported earlier. | Implemented `escape_csv_formula()` (preserving legitimate negative currency strings like `-₱40.50` while prefixing formula strings with `'`) and applied it to all exported CSV cells. Verified in `test_e2e_qa_reconciliation.py`. |
| **DEFECT-02** | Low (Query Accuracy) | `db/repositories/product_repo.py` | **SQLite `LIKE` Wildcard Leakage:** Searching products with literal `%` or `_` (e.g., `"100% Pure Calamansi Juice"`) matched unrelated products because `%` and `_` were not escaped in the `LIKE` pattern. | Escaped `\`, `%`, and `_` and added `ESCAPE '\'` to `search_products`. Verified in `test_e2e_qa_reconciliation.py`. |
| **DEFECT-03** | Low (AI Robustness) | `ai/tools.py` | **Unvalidated Integer Casts on Optional Tool Args:** Malformed non-numeric strings passed by an LLM for `window_days`, `top_n`, `lookback_days`, or `target_coverage_days` raised raw `ValueError` instead of structured `ValidationError`. | Replaced raw `int(...)` casts with `parse_non_negative_int(..., min_value=1)`. Verified in `test_e2e_qa_reconciliation.py`. |
| **DEFECT-04** | Low (State Sync) | `ui/context.py`, `ui/shell.py`, `ai/consultant.py` | **Session Store Name Desync in AI Context:** Updating `Store Display Name` in `Settings & Help` updated sidebar/page headers and chat Markdown exports, but `AIConsultantService` still read the static `.env` `store_name` when constructing its live store snapshot. | Added `store_name` override propagation from `st.session_state["store_display_name"]` into `build_app_context()` and `AIConsultantService`. Verified in `test_e2e_qa_reconciliation.py`. |

---

## 3. Test Coverage Matrix by Verification Track

| QA Track | Test Files | Verified Scenarios | Result |
| :--- | :--- | :--- | :--- |
| **1. Unit & Formula Verification** | `test_validation.py`, `test_models.py`, `test_operational_models.py`, `test_bi_formulas.py`, `test_config.py`, `test_health.py`, `test_exceptions_and_logging.py` | Currency/centavo roundtrips, SKU collision hashing, date formats, margin vs. markup math, rational ceiling restocks, breakeven volume %, secret masking, health probes. | **PASS** |
| **2. CSV Ingestion & Persistence** | `test_repositories.py`, `test_csv_importer.py` | UTF-8 BOM, Tagalog/alias headers, partial row rejections with 1-based line numbers, SHA-256 duplicate batch guard, receipt `(external_ref, product_id)` uniqueness, atomic transaction rollbacks, `dry_run` preview. | **PASS** |
| **3. Operational & Ledger Consistency** | `test_inventory_service.py`, `test_sales_service.py`, `test_consistency_service.py`, `test_e2e_qa_reconciliation.py` | Product CRUD, archive/restore, walk-in POS sale deduction, multi-item basket rollback, historical price-snapshot isolation, tampered ledger/revenue detection, cross-module conservation laws. | **PASS** |
| **4. AI Consultant & Safety Guardrails** | `test_ai_sanitizer_and_prompts.py`, `test_ai_provider.py`, `test_ai_consultant.py`, `test_e2e_qa_reconciliation.py` | All 6 Proposal Page 3 retail questions, empty-store handling, multi-SKU ambiguity, `<system>`/`[INST]` prompt-injection neutralization, credential redaction, `429` rate-limit translation, `max_tool_rounds` synthesis fallback. | **PASS** |
| **5. Streamlit UI & Workflows** | `test_app_smoke.py`, `test_ui_helpers_and_charts.py`, `test_ui_pages.py`, `test_ui_workflows.py` | All 7 pages on empty & populated stores, sample dataset loading, product creation, POS sale form, stock adjustment form, edit/archive/restore, preferences save, CSV result summaries, Plotly figures. | **PASS** |

---

## 4. Security Review Summary

1. **SQL Injection:** All queries across `ProductRepository`, `SalesRepository`, `ImportBatchRepository`, and `ConsistencyService` use strict `?` parameter binding; `LIKE` wildcards are explicitly escaped.
2. **Cross-Site Scripting (XSS):** Custom HTML rows in `insights_rail.py` and `theme.py` pass dynamic strings through `html.escape(...)`.
3. **Prompt Injection & Untrusted CSV Data:** Uploaded CSV product names, SKUs, and categories are stripped of control characters, length-bounded, scrubbed of `<system>`/`[INST]` role delimiters, and tagged with `_data_notice` inside read-only JSON tool results. The AI has zero write, SQL, filesystem, or code-execution tools.
4. **Credential & Git Safety:** `GEMINI_API_KEY` is stored as Pydantic `SecretStr`, scrubbed from assistant outputs if ever echoed, and excluded from Git via `.gitignore` (`.env`, `*.db*`, `.venv/`).

---

## 5. Performance Review

Executed automated benchmark (`test_performance_benchmark_500_products_and_5000_sales`) on SQLite WAL storage:
- **Dataset Scale:** `500` active retail SKUs across `8` categories + `5,000` timestamped sales transactions (`>12,000` units sold across ~17 days).
- **End-to-End Duration (CSV Validation + SQLite Batch Insert + Profitability Analyzer + Sales Analytics + Budget Restock Planner + Pricing Simulator):** **~4.5 seconds total** (BI analytics calculations alone complete in **< 0.3 seconds**), well within interactive local retail requirements.
