"""AgentCore Platform v1.0 — SVC-C2-028 Marketo scoring-criteria parsing + client.

Service layer: deterministic parsing/normalization helpers for compound
behavioral + demographic scoring criteria, lead-segment resolution into a
Marketo-conformant audience filter, and a thin Marketo REST API client
abstraction. No business routing beyond field derivation, no credentials
embedded here — the real client is injected with a resolved secret; the
default in-memory transport keeps nodes instantiable/testable with no network.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Protocol

_BEHAVIORAL_KEYWORDS = {
    "page_visit": ("visited", "viewed", "page visit", "browsed"),
    "form_fill": ("form fill", "filled out", "submitted a form", "form submission"),
    "email_click": ("clicked", "email click", "opened an email", "email open"),
}

_DELTA_PATTERN = re.compile(r"([+-]\s?\d+)")
_COMPANY_SIZE_PATTERN = re.compile(
    r"company size\s*(>|>=|<|<=)?\s*(\d+)|employ\w*\s*(>|>=|<|<=)?\s*(\d+)", re.IGNORECASE
)


def parse_scoring_criteria(text: str) -> dict[str, Any] | None:
    """Deterministic fallback parse of compound behavioral + demographic NL criteria.

    Returns None when no recognizable signal or score delta is found (ambiguous
    instruction — the node maps this to status=ERROR, not a silent default).
    """
    low = (text or "").lower()

    behavioral = [signal for signal, kws in _BEHAVIORAL_KEYWORDS.items() if any(k in low for k in kws)]

    delta_match = _DELTA_PATTERN.search(text or "")
    if delta_match is None:
        return None

    score_delta = int(delta_match.group(1).replace(" ", ""))

    demographic = {}
    size_match = _COMPANY_SIZE_PATTERN.search(text or "")
    if size_match:
        op = size_match.group(1) or size_match.group(3) or ">"
        size = size_match.group(2) or size_match.group(4)
        demographic["company_size"] = {"op": op, "value": int(size)}

    if not behavioral and not demographic:
        return None

    return {
        "behavioral_signals": behavioral,
        "demographic_filters": demographic,
        "score_delta": score_delta,
    }


def resolve_audience_filter(criteria: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve parsed scoring criteria into a Marketo-conformant audience filter.

    Returns None when the criteria cannot be resolved into any filter rule
    (unresolvable segment — the node maps this to status=ERROR, no silent default).
    """
    filters: list[dict[str, Any]] = []

    for signal in criteria.get("behavioral_signals", []):
        filters.append({"type": "behavioral", "attribute": signal})

    demographic = criteria.get("demographic_filters", {})
    company_size = demographic.get("company_size")
    if company_size:
        filters.append(
            {
                "type": "demographic",
                "attribute": "company_size",
                "operator": company_size["op"],
                "value": company_size["value"],
            }
        )

    if not filters:
        return None

    return {"filters": filters, "logical_operator": "AND"}


def build_scoring_payload(lead_segment: dict[str, Any], score_delta: int) -> dict[str, Any]:
    """Assemble the Marketo scoring-rule/adjustment payload."""
    return {
        "filters": lead_segment.get("filters", []),
        "logicalOperator": lead_segment.get("logical_operator", "AND"),
        "scoreDelta": score_delta,
    }


def to_json(payload: dict[str, Any]) -> str:
    """Serialize a node-internal dict for storage in State (ADR-005 flat primitives)."""
    return json.dumps(payload)


def from_json(raw: str | None) -> dict[str, Any] | None:
    """Deserialize a JSON-string State field back into a dict; None passthrough."""
    return json.loads(raw) if raw else None


class Transport(Protocol):
    """Surface the injected object must expose."""

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]: ...


class MarketoClient:
    """Thin Marketo REST API client for lead scoring writes.

    In production, ``credential`` is a secret handle resolved via
    ctx.secrets.require() and passed by the node; the transport is injected.
    The default in-memory transport records the update so unit/integration
    tests run with no network and no credential.
    """

    def __init__(self, transport: "Transport | None" = None) -> None:
        self._transport = transport

    def update_lead_score(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST the scoring-rule/adjustment payload — returns {updated_lead_count}."""
        if self._transport is not None:
            return self._transport.post("/rest/v1/leads.json", payload)
        # In-memory fallback: deterministic-ish synthetic result for tests.
        seed = uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(payload, sort_keys=True)).int
        return {"updated_lead_count": (seed % 50) + 1}
