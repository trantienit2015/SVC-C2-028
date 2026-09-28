"""AgentCore Platform v1.0 — SVC-C2-028 ConfirmScoringUpdate (outer post_process slot)."""

# Step 6 · ConfirmScoringUpdate — format the confirmation payload (updated
# lead count + applied-rule summary) returned to the caller.

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event


class ConfirmScoringUpdateNode(FunctionNode):
    """Build the caller-facing confirmation from the committed scoring write."""

    # S-1: read-only formatting, no privileged op.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Preparing the result...",
            metadata={"step": "post_process"},
        )
        updated_count = state.get("updated_lead_count", 0)
        criteria = state.get("scoring_criteria") or {}
        score_delta = criteria.get("score_delta")

        summary = (
            f"Applied score delta {score_delta:+d} to {updated_count} lead(s)"
            if isinstance(score_delta, int)
            else f"Updated {updated_count} lead(s)"
        )

        confirmation = {
            "updated_lead_count": updated_count,
            "applied_rule_summary": summary,
        }

        emit_trace_event(
            "scoring_update_confirmed",
            {"correlation_id": state.get("correlation_id"), "updated_lead_count": updated_count},
            state,
        )
        return {
            "applied_rule_summary": summary,
            "formatted_output": confirmation,
            "status": AgentStatus.SUCCESS.value,
        }
