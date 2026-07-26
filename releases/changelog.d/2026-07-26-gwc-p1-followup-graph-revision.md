# GWC P1 follow-up: graph revision schema export

- Add standalone `schemas/runtime/graph-revision.schema.json`.
- Refactor `schemas/runtime/runtime-graph.schema.json` to reuse the exported graph revision schema without changing payload shape.
- Add focused tests for graph revision validation and runtime graph `$ref` wiring.
- Export the graph revision schema through `projects/gwc/package.yaml`.

Authority: docs/schema/test only. No runtime reload, release, deployment, production configuration, credential change, migration, or production-data access.
