# SCRUM-247–249 — F9 scale-control controls to M4

- Add deterministic batch-admission evaluation bound to exact previous-batch G5 evidence, blocker state, freshness, and approved node budget.
- Add fail-closed batch cardinality and single-active-batch controls with no partial admission.
- Add exact previous-batch G5 verification for connector-confirmed push/main evidence and explicitly labelled human-observed evidence when connector observability is incomplete.
- Add Draft 2020-12 decision schemas and boundary/rejection fixtures.
- Preserve all gate separations: these controls grant no merge, deploy, production, audit, or scale authority.
