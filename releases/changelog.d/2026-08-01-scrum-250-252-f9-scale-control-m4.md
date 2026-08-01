# SCRUM-250–252 — F9 scale-control batch B2 to M4

- Add deterministic 9×9 catalog cardinality readiness with revision binding and duplicate/missing/unexpected node detection.
- Add bounded execution throttle decisions from capacity, active-batch, prior-terminal, failure-rate, and cooldown signals.
- Add exact-event/exact-branch/exact-SHA workflow observability with deterministic attempt selection, missing-run detection, connector-visibility classification, and SLO-ready metrics.
- Add Draft 2020-12 schemas and shared boundary/rejection fixtures.
- Preserve gate separation: these controls grant no merge, deployment, production, audit, or scale authority.
