# Node Instruction Contract v1.0

## Purpose

This contract defines the mandatory structure and guarantees for every Node Architect instruction pack. It ensures that every node execution provides complete guidance to the agent and produces canonical evidence/logs.

## Invariant

MODE_DOES_NOT_BYPASS_NODE_RUNTIME: All execution modes (fastlane, e2e, hotfix, rescue, normal) must execute the full node runtime pipeline:
1. GWC boot
2. agent task claim intake
3. gate authority
4. node route resolution
5. node instruction contract
6. node evidence/log recording
7. next-node or next-gate resolution

Execution modes may alter validation depth, batching, or continuation strategy—but **must not bypass** any runtime step.

## Instruction Pack Structure

Every node instruction pack MUST include:

```json
{
  "node_id": "string",
  "gate": "G0_CONTEXT | G1_ALIGNMENT | G2_EXECUTION | G3_PR | G4_MERGE | G5_DEPLOY | G6_PRODUCTION_DATA | NONE",
  "purpose": "string",
  "entry_conditions": {
    "prerequisite_gate": "string",
    "artifacts_required": ["string"],
    "conditions": [{ "type": "condition_type", "expression": "string" }]
  },
  "inputs": {
    "required": [{"name": "string", "type": "string", "description": "string"}],
    "optional": [{"name": "string", "type": "string", "description": "string"}]
  },
  "allowed_actions": ["action_type", ...],
  "forbidden_actions": ["action_type", ...],
  "outputs": {
    "required_artifacts": ["string"],
    "evidence_contract": "string",
    "logs_contract": "string"
  },
  "evidence_required": {
    "type": "descriptor | artifact | emitted",
    "schema": "string",
    "location": ".gwc/tasks/<task-id>/g<gate>/..."
  },
  "logs_required": {
    "type": "event | decision | state",
    "format": "json",
    "persistence": "local | emitted | checkpoint"
  },
  "next": {
    "next_node": "string | null",
    "next_gate": "string | null",
    "next_route": "string",
    "route_resolution": "string"
  },
  "retry": {
    "max_attempts": "integer",
    "backoff": "string",
    "exponential_base": "number",
    "retryable_errors": ["string"]
  },
  "rollback": {
    "prerequisite": "string",
    "action": "string",
    "conditions": ["string"]
  },
  "authority_boundary": {
    "grants_gate_authority": "boolean",
    "grants_write_authority": "boolean",
    "grants_merge_authority": "boolean"
  }
}
```

## Core Requirements

### 1. Node ID and Gate Binding

Every instruction pack MUST declare:
- `node_id`: Unique identifier matching the node registry
- `gate`: The gate boundary this node executes within (G0-G6 or NONE)

### 2. Entry Conditions

The node MUST specify:
- `prerequisite_gate`: Which gate must be complete before this node runs
- `artifacts_required`: List of required gate artifacts
- `conditions`: Expression-based validation rules

### 3. Input Contract

- `required` inputs MUST be provided before node execution
- `optional` inputs may be omitted with default behavior
- Each input MUST declare type and purpose

### 4. Action Boundaries

- `allowed_actions`: What the node CAN do (read, write, branch, commit, push, etc.)
- `forbidden_actions`: What the node CANNOT do (merge, deploy, production access, etc.)

### 5. Output Contract

Every node MUST produce:
- `required_artifacts`: List of output artifacts
- `evidence_contract`: Schema reference for evidence
- `logs_contract`: Schema reference for logs

### 6. Evidence and Logs

Nodes MUST produce:
- **Evidence**: Machine-readable proof of execution (descriptor, artifact, or emitted event)
- **Logs**: Human-readable audit trail (event, decision, state)

### 7. Next Resolution

Every node MUST specify:
- `next_node`: The subsequent node ID or null
- `next_gate`: The next gate boundary or null
- `next_route`: The route profile identifier
- `route_resolution`: How next-node is determined

### 8. Retry and Rollback

Nodes MUST define:
- `retry`: Max attempts, backoff strategy, retryable error types
- `rollback`: Prerequisites, rollback action, conditions

### 9. Authority Boundary

Nodes MUST declare:
- `grants_gate_authority`: Whether this node can grant gate authority
- `grants_write_authority`: Whether this node can perform writes
- `grants_merge_authority`: Whether this node can merge

**CRITICAL**: Node instructions and route decisions NEVER grant G2/G3/G4/G5/G6 authority. They are guidance only.

## Validation

The validator `tools/node_architect/validate_node_instruction.py` MUST verify:

1. Schema compliance
2. Entry conditions are resolvable
3. Inputs are complete and typed
4. Actions are properly bounded
5. Evidence and logs contracts exist
6. Next resolution is deterministic
7. Retry and rollback parameters are valid

## Failure Codes

```text
NODE_INSTRUCTION_MISSING
NODE_EVIDENCE_CONTRACT_MISSING
NODE_LOG_CONTRACT_MISSING
NODE_NEXT_ROUTE_MISSING
NODE_ENTRY_CONDITIONS_FAILED
NODE_INPUTS_INCOMPLETE
NODE_ACTION_VIOLATION
NODE_EVIDENCE_FAILED
NODE_LOG_FAILED
NODE_NEXT_RESOLVE_FAILED
NODE_RETRY_EXCEEDED
NODE_ROLLBACK_FAILED
```

## Execution Pipeline

```
[1] LOAD INSTRUCTION PACK
      ↓
[2] VALIDATE ENTRY CONDITIONS
      ↓
[3] RESOLVE INPUTS
      ↓
[4] EXECUTE ALLOWED ACTIONS
      ↓
[5] RECORD EVIDENCE
      ↓
[6] RECORD LOGS
      ↓
[7] RESOLVE NEXT NODE/GATE
      ↓
[8] PERSIST CHECKPOINT
```

## Compatibility

- Node instruction packs are additive to the gate lifecycle contract
- They do not replace G0-G6 artifacts or approval envelopes
- They bind to the exact task, repository, base SHA, and branch