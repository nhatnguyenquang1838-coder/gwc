# Base Drift Policy

The base drift evaluator classifies protected-base SHA changes after approval so bounded work can continue safely without treating every base update as a hard block.

Base drift is handled as a GWC interrupt flow. The runtime must checkpoint the active parent node, suspend it, evaluate the drift, and then resume, revalidate, reroute for reapproval, or stop.

## Decisions

- `SAFE_CONTINUE`: unrelated documentation, tests, changelog, or unrelated source changes. Authority is preserved and the runtime resumes automatically after audit.
- `REVALIDATE`: application code, dependency, schema, validator, or approved-scope-adjacent changes. Authority is preserved pending affected checks; side effects remain blocked until evidence refresh passes.
- `REAPPROVE`: governance, security, authorization, registry, workflow engine, runtime boundary, acceptance, risk, or authorized-action changes. Active authority is invalidated and a new approval envelope is required.
- `STOP`: secrets, credentials, production config, production data, destructive operations, history rewrite, or unassessable state. The route fails closed.

## Interrupt flow

```text
base drift detected
→ checkpoint parent node
→ push BASE_DRIFT interrupt frame
→ assess changed files and approved scope
→ classify SAFE_CONTINUE / REVALIDATE / REAPPROVE / STOP
→ verify resume or reroute conditions
→ pop frame, reroute, or stop
```

`SAFE_CONTINUE` and successful `REVALIDATE` must not ask the human for a generic `continue` command. They resume automatically after the required audit and evidence checks pass.

## Evidence

Every evaluation must record:

- `old_base_sha`
- `new_base_sha`
- `changed_files`
- `scope_overlap`
- `risk_assessment`
- `evaluator_decision`
- `reason_codes`
- `authority_effect`
- `evidence_effect`
- `continuation`

## Continuation rule

`SAFE_CONTINUE` preserves the active G2 envelope when the changed files are unrelated to approved scope and authority, risk, task, repository, branch, and authorized actions remain unchanged.

`REVALIDATE` preserves approval but blocks continuation until affected checks pass. A failed revalidation routes to repair when still inside the approved scope, otherwise to `REAPPROVE` or `STOP`.

Only `REAPPROVE` or `STOP` invalidates the envelope.

## Approval envelope extension

The approval envelope may carry this base-context block:

```yaml
base_context:
  approved_base_sha: null
  execution_base_sha: null
  drift_status: null
  drift_evaluation_id: null
  evaluator: null
  evaluated_at: null
```

## Existing-node integration

The interrupt mechanism does not increase the controlled 81-node catalog. It reuses existing runtime nodes:

- repository base-drift/CAS checks detect the interrupt;
- checkpoint capture and persistence suspend the parent safely;
- state reconciliation performs assessment and affected-evidence refresh;
- resume-token generation and validation restore the parent or continue the next node;
- gate-authority and failure-recovery routes handle reapproval and stop outcomes.

These mappings model routing and evidence lifecycle only. They do not implement a runtime engine, scheduler, merge, deploy, production, credential, secret, migration, or destructive operation capability.

## Validation

Run:

```text
python tools/evaluate_base_drift.py --test
python tools/validate_interrupt_flow.py --test
python tools/node_architect/validate_node_catalog_runtime_checkpoint.py
python tools/validate_instructions.py
python tools/build_project_package.py gwc --output dist
```

The evaluator scenarios should classify:

- `README.md` -> `SAFE_CONTINUE`
- `src/runtime.py` -> `REVALIDATE`
- `core/policy.md` -> `REAPPROVE`
- `.env` -> `STOP`
- approved-scope overlap -> at least `REVALIDATE`
