# G0/G1 Lifecycle Artifacts

## Purpose

This package defines the repository-native evidence contract for the first two
governance phases:

```text
G0 Context Initialization
→ G1 Discovery & Alignment
→ eligible G2 planning/execution
```

A passing G1 record is evidence that the problem, scope, non-goals, options,
decision, constraints, and acceptance criteria are aligned. It is not execution,
merge, deployment, release, configuration, secret, or production-data authority.

## Canonical workspace

```text
.gwc/
├── g0/
│   └── context-snapshot.yaml
└── g1/
    ├── intake/g1-intake-brief.yaml
    ├── preflight/g1-preflight-report.yaml
    ├── brainstorming/g1-options.yaml
    └── decision/g1-decision-record.yaml
```

Templates live under `templates/g01/`. JSON Schemas live under `schemas/`.

## Gate behavior

`tools/validate_g01.py` fails closed. Its stable outcomes are:

- `PASS`: all five artifacts validate and cross-artifact invariants hold.
- `BLOCKED`: an artifact is missing, invalid, contradictory, incomplete, or
  references evidence that does not exist.
- `ERROR`: the validator itself could not load its configuration.

Exit codes are `0` for `PASS`, `1` for `BLOCKED`, and `2` for validator
configuration or I/O failure.

A G1 `PASS` requires:

1. G0 is `READY`, has no blockers, and every required source is available.
2. Intake is `READY`, with non-empty scope, non-goals, and verifiable acceptance
   criteria, and no unresolved questions.
3. Preflight is `PASS`, with no blocker or failed check.
4. Options are `READY`, unique, and contain the recommended and selected IDs.
5. Decision is `ACCEPTED`, explicit, references valid acceptance criteria, and
   records `PASS`.
6. The decision grants no authority and explicitly excludes `G4_MERGE`,
   `G5_DEPLOY`, and `G6_PRODUCTION`.

## Runtime generation

`tools/generate_g01_runtime.py` converts observed repository, task, request, and
risk facts into schema-valid G0 context, G1 intake, and G1 preflight artifacts.
It performs no connector or production calls; callers must supply the observed
facts through a `g01-runtime-input` YAML document.

```bash
python tools/generate_g01_runtime.py \
  --input templates/g01/g01-runtime-input.template.yaml \
  --workspace .gwc \
  --json
```

Runtime exit codes are:

- `0`: generated artifacts are valid and preflight is `PASS`.
- `1`: artifacts are valid but preflight is `NEEDS_INPUT` or `BLOCKED`.
- `2`: input/schema/I/O error; no partial artifact set is reported as written.

R0/R1 work selects `G2_AUTOMATIC_BOUNDED`. R2/R3 work selects
`G2_HUMAN_DIRECTION` and fails closed until explicit human direction is recorded.
The generator never grants merge, deployment, release, secret, or production
authority.

## Validation

```bash
python tools/validate_g01.py --workspace .gwc
python tools/validate_g01.py --workspace tests/fixtures/g01-valid --json
python -m unittest tests.test_g01_lifecycle tests.test_g01_runtime
```

The generic repository validator checks that the G0/G1 schemas and validator
exist and that every JSON Schema is valid Draft 2020-12.

## Scope boundary

This implementation does not ingest external skills, execute upstream scripts,
change repository authority, enable merge or deployment, or access production
configuration, credentials, or data.
