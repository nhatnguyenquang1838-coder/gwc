# SCRUM-273 — Requirements

Task: [APR-MVP-03] AI implementation-agent adapter and bounded task execution
Parent epic: SCRUM-270 (Autonomous Pre-Prod Runtime MVP)
Consumes: SCRUM-271 (workflow/run graph contracts, Done), SCRUM-272 (standing pre-prod authority policy + run-manifest envelope, Done)

## Functional requirements

1. **Typed request contract** (`ai-task-execution-request.schema.json`) must bind:
   `run_id`, `task_id`, `repository`, `preprod_base_sha`, `working_branch`, `scope_hash`,
   `graph_revision`, `policy_revision`, `allowed_paths`, `prohibited_paths`,
   `authorized_actions`, `validation_commands`, `idempotency_key`.
2. **Typed result contract** (`ai-task-execution-result.schema.json`) must bind the same
   identity fields plus: exact `final_head_sha`, `changed_path_digest`, `validation_digest`,
   and `terminal_outcome` (enum, includes FAIL_CLOSED variants).
3. **Instruction pack builder** (`build_node_instruction_pack.py`) composes a typed pack
   from the task, repository context, G0/G1 decision, file scope, gate/node route and
   validation plan; provider-neutral (no provider-specific code).
4. **Provider-neutral adapter** (`ai_agent_adapter.py`) must:
   - require an isolated task workspace and branch from the current `preprod_base_sha`;
   - dispatch to a pluggable provider (initially `custom`/self-hosted runner; Hermes,
     Codex or another agent pluggable via the same interface);
   - enforce `allowed_paths`, `prohibited_paths`, `authorized_actions`, and SCRUM-272
     control-plane protected paths;
   - return a typed result with changed paths, commits, validation evidence, findings,
     checkpoints and next action;
   - fail closed when the provider is unavailable, output is malformed, a requested
     path/action is outside scope, or the agent attempts protected/control-plane changes;
   - permit bounded repair rounds only; every repair changes the head SHA and
     invalidates prior CI/review/G4 readiness evidence;
   - **never grant G3/G4/G5 authority** (no merge/deploy/release/production/credential calls);
   - never use a hidden manual fallback.
5. **Result validator** (`validate_ai_agent_result.py`) validates the result against the
   result schema and the scope envelope (path/action membership, digest binding).
6. **Idempotency / replay**: same `idempotency_key` plus same content digest returns the
   prior result; a different digest for the same key fails as a replay conflict.

## Acceptance criteria (from issue)

- AC-1: deterministic fake agent completes a bounded code fixture and produces a schema-valid result.
- AC-2: out-of-scope path/action, malformed output, provider timeout, duplicate request and unknown write fail closed or reconcile safely.
- AC-3: no hidden manual fallback is used.
- AC-4: agent execution never grants G3/G4/G5 authority.
- AC-5: same idempotency key + same digest returns prior result; different digest fails as replay conflict.
- AC-6: existing client runtime and checkpoint/recovery regressions remain green (no shared-surface mutation).
