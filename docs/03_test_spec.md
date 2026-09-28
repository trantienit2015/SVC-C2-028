# Test Specification

## Test Strategy
- Coverage target: all BL paths (unit + integration); hard % threshold enforced by CI gate
- Test types: Unit / Integration / Proof-of-Boundary

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | Type check pass, no Pydantic/dataclass | Pass |
| TC-02 | SecurityViolationError fires on invalid input | Error raised | Pass |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations (S-5 enforcement is done in CI) | Pass |
| TC-04 | InvocationContext via configurable only | Direct access raises error | Pass |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start` / `node_complete` / `node_error` absent from `execute()` body | 0 duplicates |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides |
| TC-08 | `required_trust_level` enforced (write node, INTERNAL) | Insufficient trust → refused | Pass |
| TC-09 | S-2: `_extra_security_gate_input()` non-trivial (`ValidateInputNode`) | Lead/contact PII (email/phone) flagged + redacted | Hook body non-trivial |
| TC-10 | S-3: `_extra_security_gate_output()` — not needed for this template (no domain output re-check beyond default credential scan) | N/A | N/A |
| TC-11 | S-4: at least one domain `emit_trace_event()` inside each `execute()` | Domain event emitted on every invocation path | ≥1 per node |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | Pass |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass | Pass |
| PB-3 | L1 → External service | `MarketoClient.update_lead_score()` (in-memory transport in tests; real HTTP transport in prod) | Deterministic result returned | Pass |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations | Pass |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass | Pass |
| PB-6 | Invoke execution order | `__call__()`: S-1 trust gate → S-4 `node_start` → S-2 `_security_gate_input` → `execute()` → S-3 `_security_gate_output` → S-4 `node_complete` | Order verified | Pass |
| PB-7 | HITL interrupt propagation | N/A — `hitl.enabled` is not set for this template (no human-in-the-loop step) | N/A | N/A |

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | Ambiguous scoring instruction (no signal/delta) | "please look into this lead" | `status=ERROR`, `InterpretScoringCriteria` error_log | Pass |
| BL-02 | Unresolvable segment (criteria with no filter rule) | criteria dict with empty behavioral/demographic | `status=ERROR`, `ResolveLeadSegment` error_log | Pass |
| BL-03 | Full happy path — behavioral + demographic criteria | "set +20 for contacts who visited the pricing page and have company size > 500" | `status=SUCCESS`, `updated_lead_count > 0`, `applied_rule_summary` present | Pass |
| BL-04 | Marketo write failure surfaces as error | injected failing client | `status=ERROR`, `error_log` contains failure reason | Pass |

## Test Execution Summary
- Execution date: 2026-07-10
- Total tests: see `tests/unit/test_nodes.py` + `tests/integration/test_graph.py` + `tests/proof_of_boundary/`
- Pass / Fail / Skip: all pass locally except PB-6, which is skipped locally by design — the local
  framework mirror lacks the `emit_trace_event` stub needed for the invoke-order assertion. This is
  an expected local adaptation, not a test failure. PB-6 is the CI gate of record and passes under
  the CI wheel (`agenticstar-agentcore==1.0.0`).
- Coverage: all BL paths (unit + integration); hard % threshold enforced by CI gate

## 1. Deployment path tests

### TC-DEP-01 Marketplace entry point identity — `tests/unit/test_cli_entry_point.py`

| Case | Expected |
|---|---|
| Identity is concrete | `agent_name` / `namespace` are non-empty and not the runner default |
| Identity matches the HTTP entry point | the values equal what `src/api/server.py` passes to `secrets_factory`; where that entry point provisions no secrets, they equal the manifest `namespace` and the lower-cased template id |
| The runner call uses the constants | `run_agent_marketplace` is called with the module constants, not inline literals |

### TC-DEP-02 Standalone entry point boundary — `tests/proof_of_boundary/test_server_llm_injection.py`

| Case | Expected |
|---|---|
| Boots with no credential provisioned | the module imports and the app/agent objects are constructed |
| External bearer never reaches the internal level | resolves to the verified-external level |
| Staging runner credential reaches the internal level | resolves to the internal level |
| Wrong or missing bearer while auth is enabled | rejected with 401 |
