"""AgentCore Platform v1.0 — SVC-C2-028 InterpretScoringCriteria (inner node, LLM)."""

# Step 2 · InterpretScoringCriteria — LLM parses compound behavioral (page
# visit/form fill/email click) + demographic (company size) signals + score
# delta from the free-text instruction. First inner node → parses user_input
# (the string passed by the GraphNode). LLM injected via constructor;
# deterministic regex fallback keeps the node instantiable/testable with no
# external dependency. Ambiguous instruction (no signal/delta found) → ERROR,
# not a silent default.

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.marketo_service import parse_scoring_criteria


class InterpretScoringCriteriaNode(FunctionNode):
    """Interpret compound behavioral + demographic scoring criteria from NL."""

    # S-1: LLM interpretation, no privileged/external write.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        text = state.get("validated_input") or state.get("user_input") or ""
        if not text.strip():
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["InterpretScoringCriteria: no instruction to interpret"],
            }

        if self._llm is not None:
            raw = self._llm.complete(
                [
                    {
                        "role": "user",
                        "content": "Parse this Marketo lead-scoring instruction. Identify behavioral signals "
                        "(page_visit/form_fill/email_click), demographic filters (company size), "
                        "and the score delta (e.g. +20, -10).\n" + text,
                    }
                ]
            )
            criteria = parse_scoring_criteria(raw if isinstance(raw, str) else text)
        else:
            criteria = parse_scoring_criteria(text)

        if criteria is None:
            emit_trace_event(
                "scoring_criteria_ambiguous",
                {"correlation_id": state.get("correlation_id")},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["InterpretScoringCriteria: ambiguous criteria — no signal/delta parsed"],
            }

        emit_trace_event(
            "scoring_criteria_interpreted",
            {"correlation_id": state.get("correlation_id"), "score_delta": criteria.get("score_delta")},
            state,
        )
        return {
            "scoring_criteria": criteria,
            "status": AgentStatus.SUCCESS.value,
        }
