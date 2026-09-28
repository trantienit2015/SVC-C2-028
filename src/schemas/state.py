"""AgentCore Platform v1.0 — SVC-C2-028 state schema."""

# ADR-005: State must be a flat TypedDict — never Pydantic BaseModel.
# Extend AgentState with agent-specific fields only. No credentials/secrets.
# state-safety: agent-specific fields are NotRequired[...] (a pipeline node may run
# before an upstream node has written the field).

from typing import Any, NotRequired

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """State for the Marketo Lead Scoring Agent."""

    # inner: InterpretScoringCriteria (LLM)
    scoring_criteria: NotRequired[dict[str, Any]]

    # inner: ResolveLeadSegment
    lead_segment: NotRequired[dict[str, Any]]

    # inner: BuildScorePayload
    # ADR-005: nested payload is JSON-string-encoded before storage in State;
    # see src/services/marketo_service.py to_json/from_json.
    marketo_payload: NotRequired[str]

    # inner: CallMarketoApi (write)
    updated_lead_count: NotRequired[int]

    # post_process: ConfirmScoringUpdate
    applied_rule_summary: NotRequired[str]
