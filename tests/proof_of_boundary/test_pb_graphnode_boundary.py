# GraphNode boundary coverage — outer `main`-slot wrapper.
#
# PB-6 (test_pb_invoke_order.py) only discovers concrete BaseNode subclasses under
# src/nodes/. MarketoScoringGraphNode lives in src/graph/graph.py (scaffold canonical
# placement for the outer main-slot wrapper), so it is a real S-1 security boundary
# (first node in the outer backbone to receive caller input) that PB-6 never probes.
# This module closes that gap: S-1 trust-gate enforcement, explicit boundary field
# mapping (criterion #9 — no raw pass-through), and delegated S-2/S-3 gating into the
# inner subgraph.

import pytest
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import MarketoScoringGraphNode
from src.nodes.interpret_scoring_criteria_node import InterpretScoringCriteriaNode


class TestGraphNodeS1TrustGate:
    def test_insufficient_caller_denied_before_execute(self):
        node = MarketoScoringGraphNode()
        state = {
            "caller_trust_level": TrustLevel.ANONYMOUS.value,
            "user_input": "score lead 42",
            "correlation_id": "c1",
        }
        result = node(state)  # via __call__ — S-1 gate runs before get_subgraph()/execute()
        assert result["status"] == AgentStatus.ERROR.value
        assert "S-1 trust gate denied" in result["error_log"][0]

    def test_declared_trust_level_is_valid_enum(self):
        assert isinstance(MarketoScoringGraphNode.required_trust_level, TrustLevel)
        assert MarketoScoringGraphNode.required_trust_level == TrustLevel.INTERNAL


class TestGraphNodeBoundaryMapping:
    def test_extract_input_only_reads_contract_fields(self):
        node = MarketoScoringGraphNode()
        state = {
            "validated_input": "score lead 42",
            "user_input": "raw caller text — must not leak if validated_input present",
            "correlation_id": "c1",
        }
        assert node.extract_input(state) == "score lead 42"

    def test_merge_output_maps_fields_explicitly_not_raw_passthrough(self):
        node = MarketoScoringGraphNode()
        state = {"correlation_id": "c1"}
        sub_result = {
            "scoring_criteria": {"rule": "engagement"},
            "lead_segment": {"segment": "hot"},
            "marketo_payload": '{"scoreDelta": 10}',
            "updated_lead_count": 3,
            "status": AgentStatus.SUCCESS.value,
            "internal_subgraph_debug": "must not leak into parent state",
        }
        merged = node.merge_output(state, sub_result)
        assert "internal_subgraph_debug" not in merged
        assert merged["updated_lead_count"] == 3
        assert merged["status"] == AgentStatus.SUCCESS.value


class TestInnerSubgraphDelegatedGating:
    """GraphNode delegates S-2/S-3 gating to the inner subgraph's own FunctionNode
    boundary (framework/nodes/graph_node.py) rather than re-implementing it at the
    wrapper — the inner entry node still runs the default S-2/S-3 gates via its own
    BaseNode.__call__(), so the boundary is not bypassed, only relocated."""

    def test_inner_entry_node_has_default_security_gates(self):
        # Local wheel rc1 stub does not ship `_security_gate_input/output` on
        # FunctionNode (same artifact as the TC-06/TC-07 @final
        # checks). CI wheel 1.0.0 is the gate of record; skip locally when absent.
        if not hasattr(FunctionNode, "_security_gate_input"):
            pytest.skip("local wheel rc1 stub lacks _security_gate_input/output — CI wheel is gate of record")
        node = InterpretScoringCriteriaNode()
        assert hasattr(node, "_security_gate_input")
        assert hasattr(node, "_security_gate_output")
