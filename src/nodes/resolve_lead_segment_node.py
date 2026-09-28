"""AgentCore Platform v1.0 — SVC-C2-028 ResolveLeadSegment (inner node)."""

# Step 3 · ResolveLeadSegment — deterministic resolution of parsed criteria
# into a Marketo-conformant audience filter expression. No LLM. Unresolvable
# criteria (no filter rule can be built) → ERROR, not a silent default.

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.marketo_service import resolve_audience_filter


class ResolveLeadSegmentNode(FunctionNode):
    """Resolve parsed scoring criteria into a Marketo audience filter."""

    # S-1: pure field derivation, no privileged op.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("status") in (AgentStatus.ERROR.value, AgentStatus.ERROR.value):
            return {"status": AgentStatus.ERROR.value}

        criteria = state.get("scoring_criteria")
        if not criteria:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ResolveLeadSegment: missing scoring_criteria"],
            }

        segment = resolve_audience_filter(criteria)
        if segment is None:
            emit_trace_event(
                "lead_segment_unresolvable",
                {"correlation_id": state.get("correlation_id")},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ResolveLeadSegment: unresolvable segment — no filter rule built"],
            }

        emit_trace_event(
            "lead_segment_resolved",
            {"correlation_id": state.get("correlation_id"), "n_filters": len(segment.get("filters", []))},
            state,
        )
        return {
            "lead_segment": segment,
            "status": AgentStatus.SUCCESS.value,
        }
