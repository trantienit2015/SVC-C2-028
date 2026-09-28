# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `Graph` (`src/graph/graph.py`)
- **L1 Base**: `AgentBaseGraph` (outer) — Cat 2 pattern: outer `AgentBaseGraph` + `GraphNode` in the
  `main` slot wrapping an inner `BaseGraph` domain workflow (`src/graph/domain_workflow_graph.py`).
- **Three-Layer Separation**:
  - State: flat TypedDict composition (`src/schemas/state.py`, `NotRequired[...]` on every
    agent-specific field — state-safety)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (outer `register_nodes()` for the 3 fixed slots; inner `register_nodes()`
    for the 4 domain steps)

## Architecture Overview

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | Framework defaults (schema_version, session_id, trust_level) | — | — | `InitializeNode` (default) |
| pre_process (`ValidateInputNode`) | Reject empty/malformed NL; S-2 lead/contact PII flag-and-sanitize | `user_input` | `validated_input` | `FunctionNode` |
| main (`MarketoScoringGraphNode`, outer) | Dispatch into the inner Marketo scoring workflow | `validated_input` | `scoring_criteria`, `lead_segment`, `marketo_payload`, `updated_lead_count` | `GraphNode` |
| → inner: `InterpretScoringCriteriaNode` | LLM parses behavioral + demographic signals + score delta | `user_input` (inner) | `scoring_criteria` | `FunctionNode` |
| → inner: `ResolveLeadSegmentNode` | Resolve criteria into Marketo audience filter | `scoring_criteria` | `lead_segment` | `FunctionNode` |
| → inner: `BuildScorePayloadNode` | Construct + validate Marketo payload | `lead_segment`, `scoring_criteria` | `marketo_payload` | `FunctionNode` |
| → inner: `CallMarketoApiNode` (write, S-1 INTERNAL) | Commit scoring write to Marketo REST API | `marketo_payload` | `updated_lead_count` | `FunctionNode` |
| post_process (`ConfirmScoringUpdateNode`) | Format confirmation (updated count + rule summary) | `updated_lead_count`, `scoring_criteria` | `applied_rule_summary`, `formatted_output` | `FunctionNode` |
| finalize | Framework defaults (response_metadata, total_time_ms) | — | — | `FinalizeNode` (default) |

### Data Flow

```
START → initialize → pre_process(ValidateInput) → main(GraphNode) → post_process(ConfirmScoringUpdate) → finalize → END
                                                        │
                                     ┌──────────────────┴──────────────────────────────┐
                                     │ inner subgraph (BaseGraph):                      │
                                     │ START → InterpretScoringCriteria                 │
                                     │       → ResolveLeadSegment                       │
                                     │       → BuildScorePayload                        │
                                     │       → CallMarketoApi (write) → END             │
                                     └───────────────────────────────────────────────────┘
```

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `scoring_criteria` | `NotRequired[dict]` | Parsed behavioral/demographic signals + score delta | No |
| `lead_segment` | `NotRequired[dict]` | Resolved Marketo audience filter | No |
| `marketo_payload` | `NotRequired[str]` (JSON) | Validated scoring-rule/adjustment payload | No |
| `updated_lead_count` | `NotRequired[int]` | Count of leads updated by the Marketo write | No |
| `applied_rule_summary` | `NotRequired[str]` | Human-readable summary of the applied rule | No |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, caller_trust_level)
- [x] SecurityViolationError (framework-enforced)
- [x] S-2: `_extra_security_gate_input()` on `ValidateInputNode` — re-checks/redacts lead/contact
      PII (email, phone) in `validated_input` (defense-in-depth after the framework's default scan)
- [x] S-4: `emit_trace_event()` — at least one domain event per `execute()` on every node
      (`input_validated`, `scoring_criteria_interpreted`, `lead_segment_resolved`,
      `score_payload_built`, `marketo_write_committed`/`marketo_write_failed`,
      `scoring_update_confirmed`) + GraphNode dispatch/completion events

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass → framework `@final` gate always runs automatically;
>   extend via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` (`MarketoScoringGraphNode`) → deliberate no-op at this layer; the inner
>   subgraph's own nodes apply S-1/S-2/S-3/S-4 per node

### Composition Pattern

- **Pattern**: `GraphNode` (outer `main` slot) wrapping an inner `BaseGraph` subgraph (Cat 2)
- **Composition target**: `src/graph/domain_workflow_graph.py::MarketoScoringWorkflowGraph`
- **Error propagation strategy**: `propagate` (inner `ERROR` re-raised as `SubgraphError`, fail-fast)

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | `AgentBaseGraph` | `AutonomousBaseGraph` | `AgentBaseGraph` | Fixed multi-step pipeline (Cat 2), not an autonomous loop |
| Composition pattern | Flat 3-slot (Cat 1 style) | Outer `AgentBaseGraph` + `GraphNode` + inner `BaseGraph` | Outer+GraphNode+inner | `gate-composition` requires this shape for Cat 2 |
| Write-node trust level | `VERIFIED_EXTERNAL` | `INTERNAL` | `INTERNAL` | Live CRM write on lead records — the design review step 5 |

## 1. Deployment entry points

The agent is reachable through two entry points, and both resolve their runtime inputs the same way.

| Entry point | File | Used by |
|---|---|---|
| Standalone HTTP | `src/api/server.py` | staging rehearsal, direct invocation |
| Marketplace one-shot Pod | `cli.py` | the platform runner (container `CMD`) |

Both read runtime parameters from `config/config.yaml` — the manifest carries discovery metadata
only — and both scope secrets to the same location (`namespace=svc`, `agent_name=svc-c2-028`), so a
secret provisioned for one path resolves identically on the other.

**Deployment-provided LLM client.** The three Azure OpenAI connection values
(`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` — the bare resource endpoint — and
`AZURE_OPENAI_DEPLOYMENT`) are resolved through the agent's own secret provider, never from the
process environment. Both entry points build the client only when all three resolve and pass it in
as `config["llm"]`; when any is absent the key stays unset and the graph keeps its deterministic
path. The manifest declares the three secrets and the provider extra.

**Progress events.** Each pipeline stage emits a non-terminal progress event at its start, so a
caller sees the run advancing. Outside the Marketplace runtime the emitter resolves to a no-op, so
the same code is safe on every path. Terminal events belong to the platform runner and are never
emitted by this agent.

**Caller authentication at the standalone entry point.** A caller that no upstream middleware
vouched for stays anonymous unless it presents a deployment-level credential: the external bearer
token grants the verified-external level, and a separate staging-only runner credential is the only
way to reach the internal level. Trust established upstream is never changed.
