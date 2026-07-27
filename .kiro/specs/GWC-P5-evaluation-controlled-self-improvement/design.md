# SCRUM-122 through SCRUM-126 Design - P5 Evaluation and Controlled Self-Improvement

The implementation reuses the existing durable history and Cytoscape projection surfaces rather than introducing a second routing engine. The base registry stays as-is; the new P5 layer is an additive overlay that explains how an evaluation run compares stable and candidate decisions, metrics and promotion state.

## Data model

The chain is represented by one versioned evaluation record with:

- the primary Jira task id `SCRUM-122`;
- the linked chain `SCRUM-122` through `SCRUM-126`;
- a durable run history section for checkpoint and replay evidence;
- a metric section for planning, runtime, outcome and catalog quality;
- a shadow-planner section for confidence, canary eligibility and stable fallback;
- a comparison section for stable-versus-candidate route and decision comparison;
- a promotion section for the experimental -> retired lifecycle.

The record is schema-backed and remains projection-only. It can be validated locally without contacting production systems.

## Viewer binding

`tools/node_architect/viewer/run_history_adapter.py` continues to render durable execution history. A new P5 overlay module renders the comparison record as additional Cytoscape nodes and visual-only edges. The adapter shows stable and candidate summaries, metric cards, and promotion stages, but all edges remain non-executable.

`tools/node_architect/viewer/registry_adapter.py` becomes the single renderer entrypoint and accepts the new evaluation record as an optional overlay input alongside run history and scenario decisions.

## Validation

`tools/validate_p5_evaluation.py` checks that:

- the chain id and linked task ids match the SCRUM-122 through SCRUM-126 batch;
- the required metric set is present;
- shadow execution remains side-effect free when not eligible;
- confidence and canary decisions fail closed when the record is incomplete;
- promotion cannot auto-advance without a human-governed approval signal;
- projection records never grant gate authority.

The regression tests exercise the validator and the viewer overlay together so that the chain remains replayable and projection-only.

## Out of scope

The P5 work does not replace the current runtime graph, change production release flows, or add any new authority path for Jira or Slack. It does not require a second planner; it only makes the existing stable/candidate comparison explicit.

