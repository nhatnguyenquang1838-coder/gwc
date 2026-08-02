# SCRUM-256 — Design

## Route

`client_request → route_scenario_validation → repo_delivery.ci-run-capture → runtime_checkpoint.checkpoint-persist → validation_quality.ci-evidence-capture → validation_quality.evidence-quality-check → validation_quality.g3-pass-decision → terminal_typed_result`

## Components

- `evidence_quality_check.py`: pure data-in/data-out decision, closed codes, stable digest, replay cache.
- `g3_pass_decision.py`: consumes exact-head validation and SCRUM-215 output; never creates later-gate authority.
- `client_runtime.py`: replaces placeholder handlers with the real implementations and blocks on non-PASS results.
- Draft 2020-12 schemas and focused regression tests.

## Authority

G2 permits only the approved branch and paths. G3 delivery is separate. G4/G5/G6 are excluded.
