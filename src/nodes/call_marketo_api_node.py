"""AgentCore Platform v1.0 — SVC-C2-028 CallMarketoApi (inner node, write)."""

# Step 5 · CallMarketoApi — the write step: commit the scoring rule/adjustment
# to Marketo.
# S-1: this is a privileged write on live CRM lead records, so
# required_trust_level = INTERNAL (the design review step 5).
# S-3: the Marketo OAuth credential is resolved via ctx.secrets.require() at
# the entry point and the client is injected — never os.environ, never in state.
# S-4: emit a domain event on every write (success and failure).

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.marketo_service import MarketoClient, from_json


class CallMarketoApiNode(FunctionNode):
    """Commit the scoring-rule/adjustment write to Marketo (privileged write)."""

    # S-1: privileged external write → internal-only caller.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.INTERNAL

    def __init__(self, client: MarketoClient | None = None):
        # Client injected (transport carries the resolved secret in prod). Default
        # in-memory client keeps the node instantiable/testable with no network.
        self._client = client or MarketoClient()

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("status") in (AgentStatus.ERROR.value, AgentStatus.ERROR.value):
            return {"status": AgentStatus.ERROR.value}

        payload = from_json(state.get("marketo_payload"))
        if not payload:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["CallMarketoApi: no marketo_payload to submit"],
            }

        try:
            result = self._client.update_lead_score(payload)
        except Exception as exc:  # noqa: BLE001 — surface as error status, log with correlation
            emit_trace_event(
                "marketo_write_failed",
                {"correlation_id": state.get("correlation_id"), "error": type(exc).__name__},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"CallMarketoApi: write failed ({type(exc).__name__})"],
            }

        updated_count = result.get("updated_lead_count", 0)
        emit_trace_event(
            "marketo_write_committed",
            {"correlation_id": state.get("correlation_id"), "updated_lead_count": updated_count},
            state,
        )
        return {
            "updated_lead_count": updated_count,
            "status": AgentStatus.SUCCESS.value,
        }
