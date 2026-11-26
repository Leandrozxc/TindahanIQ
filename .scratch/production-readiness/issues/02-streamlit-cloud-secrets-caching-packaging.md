# 02: Streamlit Cloud secrets, caching, and packaging

**What to build:** TindahanIQ deploys cleanly on Streamlit Community Cloud using `requirements.txt` alongside `pyproject.toml`, reads production credentials from Streamlit Secrets (`st.secrets`) with `.env` fallback locally, caches database initialization across Streamlit script reruns, and invalidates cached Store analytics automatically on any write operation.

**Blocked by:** 01: Durable Turso persistence for Store data

**Status:** done

- [x] `requirements.txt` is generated/pinned in sync with `pyproject.toml` dependencies (including Turso and Streamlit UI packages) for Streamlit Community Cloud builds.
- [x] Application configuration loads `st.secrets` in `production` and `.env` locally without exposing `SecretStr` values in logs or UI.
- [x] Database initialization is cached across reruns and read-heavy BI queries are cached and invalidated on any CSV import, Product edit, Restock, Spoilage, Sales Transaction, or Store reset.
