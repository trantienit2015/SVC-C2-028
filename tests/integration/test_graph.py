# SVC-C2-028 — Integration test: full-graph compile() + invoke().

from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import Graph


class FakeLLM:
    def complete(self, *a, **k):
        return "visited the pricing page, company size > 500, +20"

    def generate(self, *a, **k):
        return self.complete()


def test_full_graph_commits_scoring_write():
    agent = Graph(config={"llm": FakeLLM(), "max_retry": 1})
    agent.compile()
    ctx = InvocationContext(
        session_id="it-1", caller_trust_level=TrustLevel.INTERNAL, caller_id="tester"
    )
    result = agent.invoke(
        "set +20 for contacts who visited the pricing page and have company size > 500", ctx=ctx
    )
    assert result["status"] in (AgentStatus.SUCCESS, AgentStatus.SUCCESS.value)
    nh = result.get("node_history") or []
    assert len(nh) >= 5, f"expected >=5 nodes, got {len(nh)}: {nh}"
    out = result.get("output") or result.get("formatted_output")
    assert out and out.get("updated_lead_count") is not None


def test_empty_input_errors():
    agent = Graph(config={"llm": FakeLLM(), "max_retry": 1})
    agent.compile()
    ctx = InvocationContext(
        session_id="it-2", caller_trust_level=TrustLevel.INTERNAL, caller_id="tester"
    )
    result = agent.invoke("", ctx=ctx)
    assert result["status"] in (AgentStatus.ERROR, AgentStatus.ERROR.value)


def test_insufficient_trust_denies_write():
    agent = Graph(config={"llm": FakeLLM(), "max_retry": 1})
    agent.compile()
    ctx = InvocationContext(
        session_id="it-3", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="tester"
    )
    result = agent.invoke(
        "set +20 for contacts who visited the pricing page and have company size > 500", ctx=ctx
    )
    assert result["status"] in (AgentStatus.ERROR, AgentStatus.ERROR.value)
