# SVC-C2-028 — Unit tests: per-node success + error/edge paths.

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.build_score_payload_node import BuildScorePayloadNode
from src.nodes.call_marketo_api_node import CallMarketoApiNode
from src.nodes.confirm_scoring_update_node import ConfirmScoringUpdateNode
from src.nodes.interpret_scoring_criteria_node import InterpretScoringCriteriaNode
from src.nodes.resolve_lead_segment_node import ResolveLeadSegmentNode
from src.nodes.validate_input_node import ValidateInputNode


class TestValidateInputNode:
    def test_success(self):
        r = ValidateInputNode().execute(
            {"user_input": "set +20 for contacts who visited the pricing page", "correlation_id": "c"}
        )
        assert r["status"] == AgentStatus.SUCCESS
        assert r["validated_input"]

    def test_empty_error(self):
        assert ValidateInputNode().execute({"user_input": ""})["status"] == AgentStatus.ERROR

    def test_pii_redacted(self):
        r = ValidateInputNode().execute(
            {"user_input": "score +10 for jane.doe@example.com visitors", "correlation_id": "c"}
        )
        assert r["status"] == AgentStatus.SUCCESS
        assert "jane.doe@example.com" not in r["validated_input"]
        assert "[REDACTED_EMAIL]" in r["validated_input"]

    def test_extra_security_gate_input_sanitizes(self):
        node = ValidateInputNode()
        result = node._extra_security_gate_input(
            {"validated_input": "call +1-555-123-4567 about +15 score", "correlation_id": "c"}
        )
        assert isinstance(result, dict)
        assert "555" not in result["validated_input"] or "[REDACTED_PHONE]" in result["validated_input"]


class TestInterpretScoringCriteriaNode:
    def test_fallback_parse(self):
        r = InterpretScoringCriteriaNode().execute(
            {"validated_input": "visited the pricing page, company size > 500, +20", "correlation_id": "c"}
        )
        assert r["status"] == AgentStatus.SUCCESS
        assert r["scoring_criteria"]["score_delta"] == 20
        assert "page_visit" in r["scoring_criteria"]["behavioral_signals"]

    def test_llm_path(self):
        class LLM:
            def complete(self, *a, **k):
                return "clicked email link, +10"

        r = InterpretScoringCriteriaNode(llm=LLM()).execute(
            {"validated_input": "some instruction", "correlation_id": "c"}
        )
        assert r["status"] == AgentStatus.SUCCESS
        assert r["scoring_criteria"]["score_delta"] == 10

    def test_ambiguous_error(self):
        r = InterpretScoringCriteriaNode().execute({"validated_input": "please look into this lead"})
        assert r["status"] == AgentStatus.ERROR

    def test_empty_error(self):
        assert InterpretScoringCriteriaNode().execute({"validated_input": ""})["status"] == AgentStatus.ERROR


class TestResolveLeadSegmentNode:
    def test_resolves_segment(self):
        r = ResolveLeadSegmentNode().execute(
            {
                "scoring_criteria": {
                    "behavioral_signals": ["page_visit"],
                    "demographic_filters": {"company_size": {"op": ">", "value": 500}},
                    "score_delta": 20,
                },
                "correlation_id": "c",
            }
        )
        assert r["status"] == AgentStatus.SUCCESS
        assert len(r["lead_segment"]["filters"]) == 2

    def test_missing_criteria_error(self):
        assert ResolveLeadSegmentNode().execute({"correlation_id": "c"})["status"] == AgentStatus.ERROR

    def test_unresolvable_error(self):
        r = ResolveLeadSegmentNode().execute(
            {"scoring_criteria": {"behavioral_signals": [], "demographic_filters": {}, "score_delta": 5}}
        )
        assert r["status"] == AgentStatus.ERROR

    def test_passthrough_on_error(self):
        assert ResolveLeadSegmentNode().execute({"status": AgentStatus.ERROR})["status"] == AgentStatus.ERROR


class TestBuildScorePayloadNode:
    def test_builds_payload(self):
        r = BuildScorePayloadNode().execute(
            {
                "lead_segment": {"filters": [{"type": "behavioral", "attribute": "page_visit"}], "logical_operator": "AND"},
                "scoring_criteria": {"score_delta": 20},
                "correlation_id": "c",
            }
        )
        assert r["status"] == AgentStatus.SUCCESS
        payload = json.loads(r["marketo_payload"])
        assert payload["scoreDelta"] == 20

    def test_missing_fields_error(self):
        assert BuildScorePayloadNode().execute({"correlation_id": "c"})["status"] == AgentStatus.ERROR

    def test_passthrough_on_error(self):
        assert BuildScorePayloadNode().execute({"status": AgentStatus.ERROR})["status"] == AgentStatus.ERROR


class TestCallMarketoApiNode:
    def test_commits_write_default_client(self):
        r = CallMarketoApiNode().execute(
            {
                "marketo_payload": json.dumps(
                    {"filters": [{"type": "behavioral", "attribute": "page_visit"}], "logicalOperator": "AND", "scoreDelta": 20}
                ),
                "correlation_id": "c",
            }
        )
        assert r["status"] == AgentStatus.SUCCESS
        assert r["updated_lead_count"] > 0

    def test_no_payload_error(self):
        assert CallMarketoApiNode().execute({"correlation_id": "c"})["status"] == AgentStatus.ERROR

    def test_client_error_surfaces(self):
        class BadClient:
            def update_lead_score(self, payload):
                raise RuntimeError("boom")

        r = CallMarketoApiNode(client=BadClient()).execute(
            {"marketo_payload": json.dumps({"scoreDelta": 10}), "correlation_id": "c"}
        )
        assert r["status"] == AgentStatus.ERROR

    def test_passthrough_on_error(self):
        assert CallMarketoApiNode().execute({"status": AgentStatus.ERROR})["status"] == AgentStatus.ERROR


class TestConfirmScoringUpdateNode:
    def test_builds_confirmation(self):
        r = ConfirmScoringUpdateNode().execute(
            {
                "updated_lead_count": 12,
                "scoring_criteria": {"score_delta": 20},
                "correlation_id": "c",
            }
        )
        assert r["status"] == AgentStatus.SUCCESS
        assert r["formatted_output"]["updated_lead_count"] == 12
        assert "20" in r["applied_rule_summary"]


class TestTrustDeclarations:
    def test_write_node_requires_internal(self):
        assert CallMarketoApiNode.required_trust_level == TrustLevel.INTERNAL

    def test_all_declare_trust(self):
        for cls in (
            ValidateInputNode,
            InterpretScoringCriteriaNode,
            ResolveLeadSegmentNode,
            BuildScorePayloadNode,
            CallMarketoApiNode,
            ConfirmScoringUpdateNode,
        ):
            assert isinstance(cls.required_trust_level, TrustLevel)

    def test_s1_trust_gate_denies_insufficient_caller(self):
        node = CallMarketoApiNode()
        state = {
            "caller_trust_level": TrustLevel.ANONYMOUS.value,
            "marketo_payload": json.dumps({"scoreDelta": 10}),
            "correlation_id": "c",
        }
        result = node(state)  # via __call__, S-1 gate runs before execute()
        assert result["status"] == AgentStatus.ERROR.value
        assert "S-1 trust gate denied" in result["error_log"][0]

    def test_s1_trust_gate_allows_sufficient_caller(self):
        node = CallMarketoApiNode()
        state = {
            "caller_trust_level": TrustLevel.INTERNAL.value,
            "marketo_payload": json.dumps({"scoreDelta": 10}),
            "correlation_id": "c",
        }
        result = node(state)
        assert result["status"] == AgentStatus.SUCCESS
