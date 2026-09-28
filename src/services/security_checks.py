"""AgentCore Platform v1.0 — SVC-C2-028 S-2 lead/contact PII scan (deterministic).

Per the the security spec: lead/contact business PII
(email address, phone number) is non-regulated business PII in this scope —
flag-and-sanitize, not reject. Regex-based, not model-based.
"""

from __future__ import annotations

import re

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_PATTERN = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b")


def sanitize_lead_pii(text: str) -> tuple[str, list[str]]:
    """Redact lead/contact business PII (email, phone) before it flows further.

    Returns (sanitized_text, flags) — flags is a list of pattern names found
    (for audit logging), never the raw PII value itself.
    """
    flags: list[str] = []
    sanitized = text

    if _EMAIL_PATTERN.search(sanitized):
        flags.append("email_address")
        sanitized = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", sanitized)

    if _PHONE_PATTERN.search(sanitized):
        flags.append("phone_number")
        sanitized = _PHONE_PATTERN.sub("[REDACTED_PHONE]", sanitized)

    return sanitized, flags
