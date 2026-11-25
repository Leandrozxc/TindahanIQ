"""Untrusted CSV data sanitization, prompt-injection fencing, and leak prevention."""

from __future__ import annotations

import re
from collections.abc import Sequence

from tindahaniq.exceptions import ValidationError

# Strip non-printable control characters except newline/tab where explicitly allowed
STRICT_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
PROMPT_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+")
MULTI_SPACE_RE = re.compile(r" {2,}")

# Neutralize role/system delimiter tags that could be smuggled inside CSV fields
INJECTION_DELIMITER_RE = re.compile(
    r"(?i)(?:<\s*/?\s*(?:system|instruction|prompt|tool_call|function_call)\b[^>]*>"
    r"|\[\s*/?\s*INST\s*\]"
    r"|<\|(?:im_start|im_end|system|user|assistant)\|>)"
)

INTERNAL_PROMPT_SENTINEL = "TINDAHANIQ_INTERNAL_SYSTEM_SPEC_V1"


def sanitize_untrusted_store_text(value: str, *, max_length: int = 120) -> str:
    """Clean catalog/CSV text before embedding it inside AI tool response payloads."""
    cleaned = STRICT_CONTROL_RE.sub(" ", str(value))
    cleaned = INJECTION_DELIMITER_RE.sub("[filtered]", cleaned)
    cleaned = cleaned.replace("```", "'''").replace('"""', "'''")
    cleaned = MULTI_SPACE_RE.sub(" ", cleaned).strip()
    if len(cleaned) > max_length:
        return cleaned[: max_length - 3].rstrip() + "..."
    return cleaned


def sanitize_user_prompt(prompt: object, *, max_length: int = 2000) -> str:
    """Validate and clean a user chat query prior to sending to the LLM."""
    if not isinstance(prompt, str):
        raise ValidationError(
            "Non-string chat prompt",
            user_message="Please enter a text question for TindahanIQ.",
            details={"field": "prompt"},
        )
    cleaned = PROMPT_CONTROL_RE.sub("", prompt).strip()
    if not cleaned:
        raise ValidationError(
            "Blank chat prompt",
            user_message="Please type a question about your store before sending.",
            details={"field": "prompt"},
        )
    if len(cleaned) > max_length:
        raise ValidationError(
            f"Chat prompt length {len(cleaned)} exceeds {max_length}",
            user_message=f"Please shorten your question to {max_length} characters or fewer.",
            details={"field": "prompt", "max_length": max_length},
        )
    return cleaned


def scrub_sensitive_output(
    text: str,
    *,
    secret_values: Sequence[str] = (),
) -> str:
    """Redact any accidental credential or internal system-prompt sentinel from model output."""
    scrubbed = text
    if INTERNAL_PROMPT_SENTINEL in scrubbed:
        scrubbed = scrubbed.replace(INTERNAL_PROMPT_SENTINEL, "[REDACTED]")
    for secret in secret_values:
        candidate = secret.strip()
        if candidate and len(candidate) >= 6 and candidate in scrubbed:
            scrubbed = scrubbed.replace(candidate, "[REDACTED_CREDENTIAL]")
    return scrubbed
