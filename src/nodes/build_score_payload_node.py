"""AgentCore Platform v1.0 — SVC-C2-028 BuildScorePayload (inner node)."""

# Step 4 · BuildScorePayload — construct + validate the Marketo scoring-rule/
# adjustment payload (field types + required fields) before the write call.

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.marketo_service import build_scoring_payload, to_json


class BuildScorePayloadNode(FunctionNode):
    """Build and validate the Marketo scoring payload."""

    # S-1: pure payload construction, no privileged op.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("status") in (AgentStatus.ERROR.value, AgentStatus.ERROR.value):
            return {"status": AgentStatus.ERROR.value}

        lead_segment = state.get("lead_segment")
        criteria = state.get("scoring_criteria") or {}
        score_delta = criteria.get("score_delta")

        if not lead_segment or not isinstance(score_delta, int):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["BuildScorePayload: missing lead_segment or score_delta"],
            }

        payload = build_scoring_payload(lead_segment, score_delta)
        if not payload.get("filters"):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["BuildScorePayload: payload validation failed — no filters"],
            }

        emit_trace_event(
            "score_payload_built",
            {"correlation_id": state.get("correlation_id"), "score_delta": score_delta},
            state,
        )
        return {
            "marketo_payload": to_json(payload),
            "status": AgentStatus.SUCCESS.value,
        }
