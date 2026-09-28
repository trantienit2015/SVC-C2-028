"""AgentCore Platform v1.0 — SVC-C2-028 outer graph (Cat 2).

Cat 2 = AgentBaseGraph (outer backbone) + GraphNode in the `main` slot wrapping
an inner BaseGraph workflow. Backbone:
  initialize → pre_process(ValidateInput) → main(GraphNode) → post_process(ConfirmScoringUpdate) → finalize

The GraphNode wrapper lives in THIS file (not src/nodes/) matching the scaffold canonical
layout: the outer `main`-slot wrapper stays alongside graph composition rather than the
per-domain node package. Boundary coverage for it lives in
tests/proof_of_boundary/test_pb_graphnode_boundary.py (PB-6 only discovers src/nodes/).
"""

from typing import Any, ClassVar

from framework.graph.agent_base_graph import AgentBaseGraph
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.nodes.confirm_scoring_update_node import ConfirmScoringUpdateNode
from src.nodes.validate_input_node import ValidateInputNode
from src.schemas.state import State


class MarketoScoringGraphNode(GraphNode):
    """`main` slot — dispatches into the inner Marketo scoring workflow."""

    # S-1: outer main-slot wrapper — first node in the outer backbone that dispatches
    # into the Marketo write pipeline. Matches config/agent.yaml required_trust_level
    # (INTERNAL) since the wrapped subgraph terminates in call_marketo_api_node (write).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.INTERNAL
    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, llm: Any | None = None, marketo_client: Any | None = None):
        super().__init__()
        self._llm = llm
        self._client = marketo_client

    def get_subgraph(self) -> AgentBaseGraph:
        from src.graph.domain_workflow_graph import MarketoScoringWorkflowGraph

        sg = MarketoScoringWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        # S-4: runs inside GraphNode.execute() — audit dispatch into the subgraph.
        # Progress (non-terminal) event for the caller, emitted as the subgraph step
        # begins. Outside the Marketplace runtime this is a no-op emitter.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Working on the request...",
            metadata={"step": "main"},
        )
        emit_trace_event(
            "scoring_workflow_dispatched",
            {"correlation_id": state.get("correlation_id")},
            state,
        )
        value = state.get("validated_input", state.get("user_input", ""))
        return value if isinstance(value, str) else str(value)

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        # S-4: runs inside GraphNode.execute() — audit subgraph outcome.
        emit_trace_event(
            "scoring_workflow_completed",
            {"correlation_id": state.get("correlation_id"), "updated_lead_count": sub_result.get("updated_lead_count")},
            state,
        )
        return {
            "scoring_criteria": sub_result.get("scoring_criteria"),
            "lead_segment": sub_result.get("lead_segment"),
            "marketo_payload": sub_result.get("marketo_payload"),
            "updated_lead_count": sub_result.get("updated_lead_count"),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {
            "llm": self._llm,
            "marketo_client": self._client,
        }


class Graph(AgentBaseGraph):
    """Outer Cat 2 graph for SVC-C2-028 Marketo Lead Scoring Agent."""

    @property
    def name(self) -> str:
        return "svc-c2-028"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()
        llm = self.config.get("llm") if hasattr(self, "config") else None
        client = self.config.get("marketo_client") if hasattr(self, "config") else None
        self._nodes["pre_process"] = ValidateInputNode()
        self._nodes["main"] = MarketoScoringGraphNode(llm=llm, marketo_client=client)
        self._nodes["post_process"] = ConfirmScoringUpdateNode()

    # add_edges() not overridden — backbone wiring belongs to the framework.
