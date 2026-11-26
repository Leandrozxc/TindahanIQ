# 0003. Deterministic BI Engine and Read-Only AI Tools with Bounded Fallback

**Status:** accepted

All monetary arithmetic is computed deterministically in Python (`services/bi/formulas.py`) using `decimal.Decimal` over integer centavos, and `AIConsultantService` is restricted to 7 read-only tools with a `30s` request timeout (`5s` connect), at most `2` jittered retries on transient `429`/`5xx`/network errors, and a deterministic pre-grounding fallback.

## Context & Trade-offs

Allowing an LLM to generate raw SQL or perform financial math introduces SQL-injection risk, prompt-injection escalation from uploaded CSVs, and floating-point or hallucinated currency errors. Restricting the AI to sanitized, read-only tool outputs guarantees numerical accuracy and ledger integrity, while bounded timeouts, retries, and an optional secondary OpenAI-compatible fallback endpoint (`OPENAI_FALLBACK_*`) protect live demos against upstream proxy cold starts or rate limits without blocking the offline BI dashboards.
