# G2 Change Plan

## Objective

Enforce a canonical .gwc/tasks/<task-id>/ artifact contract for write-applicable G2-G6 work. Every applicable gate must have a task-bound artifact before its write-capable action; later gates must never be inferred from an earlier gate.

## Exact implementation scope

- AGENTS.md
- core/GATE_LIFECYCLE_CONTRACT_v1.0.md
- core/E2E_DRAFT_PR_DELIVERY_RULE.md
- core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md
- schemas/approval-envelope.schema.json
- tools/validate_g01.py
- tests/test_chatgpt_agent_runbook_continuation.py
- tests/test_gate_lifecycle_process_contract.py
- tests/test_g01_lifecycle.py
- docs/g01-lifecycle.md
- .gwc/tasks/task_50c03a0f-6444-47f0-8d64-61dd69232fbb/g0/context-snapshot.yaml
- .gwc/tasks/task_50c03a0f-6444-47f0-8d64-61dd69232fbb/g1/intake/g1-intake-brief.yaml
- .gwc/tasks/task_50c03a0f-6444-47f0-8d64-61dd69232fbb/g1/preflight/g1-preflight-report.yaml
- .gwc/tasks/task_50c03a0f-6444-47f0-8d64-61dd69232fbb/g1/brainstorming/g1-options.yaml
- .gwc/tasks/task_50c03a0f-6444-47f0-8d64-61dd69232fbb/g1/decision/g1-decision-record.yaml
- .gwc/tasks/task_50c03a0f-6444-47f0-8d64-61dd69232fbb/g2/execution-envelope.yaml

## Authorized G2 actions

- Claim and update the DS Admin work item through legal State Engine transitions.
- Create a guarded branch/worktree.
- Modify only the exact files listed above.
- Run sandboxed validators and focused tests.
- Push the guarded working branch when delivery evidence is ready.

## Exclusions

Protected main writes, merge, auto-merge, deployment, release, production configuration, credentials/secrets, migrations, production data, force-push, branch deletion, shared-history rewrite, and PR-base changes.

## Validation

Run YAML/JSON schema validation, python3 tools/validate_g01.py, git diff --check, focused lifecycle/artifact tests, secret/scope review, and complete diff review before G3.
