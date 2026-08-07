feat(gwc): add SCRUM-271 autonomous pre-prod evidence runtime vertical slice

- add an additive workflow-dispatch evidence runtime with exact-base checkout
- add canonical run-graph and G0→G6 gate-story schemas and renderers
- add bounded, idempotent PR-description evidence rendering
- add exact-head G4 PR-evidence receipt/check binding PR body, graph, story, and evidence digests
- fail closed for `main` target, malformed markers, missing events, route drift, and stale evidence
- preserve G4/G5/G6 authority separation; no merge, deploy, release, or production authority is added
