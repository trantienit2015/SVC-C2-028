"""AgentCore Platform v1.0 — SVC-C2-028 inner domain workflow graph."""

# Inner BaseGraph for the Cat 2 Marketo scoring pipeline. Instantiated by
# MarketoScoringGraphNode.get_subgraph() in graph.py. Linear topology:
#   START → interpret_scoring_criteria → resolve_lead_segment
#         → build_score_payload → call_marketo_api → END
# Downstream nodes pass through on incoming ERROR so an early failure is
# preserved rather than overwritten by a later SUCCESS.

from typing import Any

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_status import AgentStatus
from langgraph.graph import END, START

from src.nodes.build_score_payload_node import BuildScorePayloadNode
from src.nodes.call_marketo_api_node import CallMarketoApiNode
from src.nodes.interpret_scoring_criteria_node import InterpretScoringCriteriaNode
from src.nodes.resolve_lead_segment_node import ResolveLeadSegmentNode
from src.schemas.state import State


class MarketoScoringWorkflowGraph(BaseGraph):
    """Inner graph: interpret → resolve → build → Marketo write."""

    @property
    def name(self) -> str:
        return "marketo_scoring_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        llm = self.config.get("llm") if hasattr(self, "config") else None
        client = self.config.get("marketo_client") if hasattr(self, "config") else None
        self._nodes["interpret_scoring_criteria"] = InterpretScoringCriteriaNode(llm=llm)
        self._nodes["resolve_lead_segment"] = ResolveLeadSegmentNode()
        self._nodes["build_score_payload"] = BuildScorePayloadNode()
        self._nodes["call_marketo_api"] = CallMarketoApiNode(client=client)

    def add_edges(self) -> None:
        self._sg.add_edge(START, "interpret_scoring_criteria")
        self._sg.add_edge("interpret_scoring_criteria", "resolve_lead_segment")
        self._sg.add_edge("resolve_lead_segment", "build_score_payload")
        self._sg.add_edge("build_score_payload", "call_marketo_api")
        self._sg.add_edge("call_marketo_api", END)

    def route(self, state: dict[str, Any]) -> str:
        return END if state.get("status") == AgentStatus.ERROR.value else "call_marketo_api"

    def get_output(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "scoring_criteria": state.get("scoring_criteria"),
            "lead_segment": state.get("lead_segment"),
            "marketo_payload": state.get("marketo_payload"),
            "updated_lead_count": state.get("updated_lead_count"),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
