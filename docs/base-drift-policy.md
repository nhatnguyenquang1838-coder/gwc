# Base Drift Policy

The base drift evaluator classifies protected-base SHA changes after approval
so bounded work can continue safely without treating every base update as a
hard block.

## Decisions

- `SAFE_CONTINUE`: documentation, tests, changelog, and unrelated source
  changes.
- `REVALIDATE`: application code, dependency, and schema changes.
- `REAPPROVE`: governance, security, authorization, registry, workflow engine,
  and runtime boundary changes.
- `STOP`: secrets, credentials, production config, production data, and
  destructive operations.

## Evidence

Every evaluation must record:

- `old_base_sha`
- `new_base_sha`
- `changed_files`
- `scope_overlap`
- `risk_assessment`
- `evaluator_decision`

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

## Validation

Run:

```text
python tools/evaluate_base_drift.py --test
python tools/validate_instructions.py
python tools/build_project_package.py gwc --output dist
```

The evaluator scenarios should classify:

- `README.md` -> `SAFE_CONTINUE`
- `src/runtime.py` -> `REVALIDATE`
- `core/policy.md` -> `REAPPROVE`
- `.env` -> `STOP`
