# SCRUM-273 — Design

## Module layout (all new, isolated under tools/node_architect/)

```
schemas/node-architect/ai-task-execution-request.schema.json
schemas/node-architect/ai-task-execution-result.schema.json
tools/node_architect/build_node_instruction_pack.py
tools/node_architect/ai_agent_adapter.py
tools/node_architect/validate_ai_agent_result.py
tests/test_ai_agent_adapter.py
```

## Data contracts

### request (ai-task-execution-request.schema.json)
Object, `additionalProperties: false`, required:
`run_id, task_id, repository, preprod_base_sha, working_branch, scope_hash,
graph_revision, policy_revision, allowed_paths[], prohibited_paths[],
authorized_actions[], validation_commands[], idempotency_key`.
`preprod_base_sha` matches `^[0-9a-f]{40}$`; `scope_hash` matches `^sha256:[0-9a-f]{64}$`;
`allowed_paths` / `authorized_actions` are non-empty unique string arrays.

### result (ai-task-execution-result.schema.json)
Object, `additionalProperties: false`, required:
`run_id, task_id, repository, scope_hash, idempotency_key, final_head_sha,
changed_paths[], changed_path_digest, validation_digest, terminal_outcome,
provider, findings[], checkpoints[], next_action`.
`terminal_outcome` enum: `SUCCESS`, `FAIL_CLOSED`, `REPLAY_CONFLICT`, `TIMEOUT`,
`MALFORMED_OUTPUT`, `OUT_OF_SCOPE`, `RECONCILED`. `final_head_sha` 40-hex.

## Adapter design (ai_agent_adapter.py)

- Pure orchestration + enforcement; providers are pluggable via a `Provider` protocol.
- `execute(request, *, provider, root, now=None) -> dict`:
  1. validate request against schema; on failure -> `FAIL_CLOSED` result (AC-2).
  2. resolve isolated workspace; branch from `preprod_base_sha`; on missing/locked
     branch -> `FAIL_CLOSED`.
  3. build instruction pack via `build_node_instruction_pack`.
  4. compute content digest of (request identity + pack); check idempotency store:
     same key+same digest -> return prior result (AC-5); same key+diff digest ->
     `REPLAY_CONFLICT` (AC-5).
  5. call `provider.run(pack)`; if provider unavailable/timeout -> `TIMEOUT`/`FAIL_CLOSED`.
  6. validate raw output via `validate_ai_agent_result`; malformed -> `MALFORMED_OUTPUT`.
  7. enforce scope: every changed path ∈ `allowed_paths` and ∉ `prohibited_paths` and ∉
     SCRUM-272 control-plane protected paths; every action ∈ `authorized_actions`;
     unknown/out-of-scope write -> `OUT_OF_SCOPE` (AC-2, AC-4).
  8. run `validation_commands`; record `validation_digest` (sha256 of joined outputs).
  9. bounded repair loop (max N rounds): a repair re-commits, changes `final_head_sha`,
     and **invalidates** any cached CI/review/G4-readiness evidence (re-evaluated, not reused).
  10. persist result to idempotency store; return typed result.
- No calls to merge/deploy/release/prod/credential tools; `g3_g4_g5_authority_granted` is
  always `false` (AC-4).

## Provider pluggability

- `Provider` protocol: `name: str`, `run(pack) -> dict` (returned dict is the agent's
  raw output). `CustomRunnerProvider` is the default (`custom`/self-hosted). A
  `DeterministicFakeProvider` is provided for tests (AC-1) and replays a bounded fixture.
- Hermes/Codex adapters implement the same protocol with no graph change.

## Test plan (tests/test_ai_agent_adapter.py)

- Deterministic fake completes a bounded fixture -> `SUCCESS` + schema-valid result (AC-1).
- Out-of-scope path -> `OUT_OF_SCOPE`; unknown write -> `OUT_OF_SCOPE` (AC-2).
- Malformed provider output -> `MALFORMED_OUTPUT` (AC-2).
- Provider timeout -> `TIMEOUT` (AC-2).
- Duplicate request same digest -> returns prior result; different digest -> `REPLAY_CONFLICT` (AC-5).
- No provider / manual fallback path -> `FAIL_CLOSED`; assert no fallback used (AC-3).
- Assert `g3_g4_g5_authority_granted is False` and no forbidden action recorded (AC-4).
