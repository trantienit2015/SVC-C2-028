"""AgentCore Platform v1.0 — SVC-C2-028 ValidateInput (outer pre_process slot)."""

# Step 1 · ValidateInput — reject empty/malformed NL scoring instruction.
# S-2: deterministic (rule/regex, NOT LLM) scan for lead/contact business PII
# (email, phone) → flag-and-sanitize before the text flows further (non-
# regulated business PII per the design review — flag, not reject).

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.security_checks import sanitize_lead_pii


class ValidateInputNode(FunctionNode):
    """Validate the inbound NL lead-scoring instruction."""

    # S-1: read-only validation of caller-supplied text.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Checking the request...",
            metadata={"step": "pre_process"},
        )
        raw = state.get("user_input", "")
        if not isinstance(raw, str) or not raw.strip():
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ValidateInput: scoring instruction is empty or missing"],
            }

        sanitized, pii_flags = sanitize_lead_pii(raw.strip())
        emit_trace_event(
            "input_validated",
            {"correlation_id": state.get("correlation_id"), "pii_flags": pii_flags},
            state,
        )
        return {
            "validated_input": sanitized,
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-2 domain hook (defense-in-depth; non-raising, per framework contract)."""
        raw = state.get("validated_input") or state.get("user_input") or ""
        sanitized, pii_flags = sanitize_lead_pii(raw)
        if pii_flags:
            emit_trace_event(
                "input_pii_flagged",
                {"correlation_id": state.get("correlation_id"), "pii_flags": pii_flags},
                state,
            )
        return {**state, "validated_input": sanitized}
