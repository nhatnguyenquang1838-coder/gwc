# BMAD Procedure Adapter Contract v1.0

Status: canonical GWC integration contract for SCRUM-119.

## Authority

GWC owns canonical gate state and decides whether a procedure may run. BMAD executes only a registered, versioned procedure inside an exact permission envelope. A BMAD result is evidence and recommendation; it is never gate approval.

BMAD MUST NOT:

- approve or transition G2, G4, G5 or G6;
- mutate `.gwc/**`;
- broaden task scope or change repository/base/head binding;
- write outside declared BMAD/project-owned paths;
- merge, deploy, release, migrate, mutate credentials/secrets or perform production operations;
- write Jira, Notion or Slack unless GWC invokes a separately authorized exact projection adapter.

## Procedure registry

The canonical set is `architecture-analysis`, `story-preparation`, `tdd-implementation`, `code-review` and `release-readiness`. Registry entries declare exact version, execution mode, inputs, outputs, action/path permissions, timeout and retry policy.

## Request contract

A request binds:

- task ID and GWC run ID;
- repository, base SHA and optional exact head SHA;
- procedure ID/version and adapter version;
- GWC scope hash and permission envelope;
- expected outputs, timeout, retry policy and idempotency key;
- pinned BMAD source repository/commit/provider state;
- optional UA and Task-Me artifact references.

The adapter rejects the request before side effects when any binding or permission fails.

## Result contract

A result returns terminal status, evidence references, changed paths, checks/tests, findings, residual risks, provenance, checkpoint state and a read-only GWC recommendation. `scope_change_required` is proposal/blocker only.

## Permission model

`read_only_analysis` permits read and evidence output only. `bounded_repository_write` additionally requires matching G2 evidence and allows only normalized declared paths/actions. `prohibited` covers all authority and production actions.

## Idempotency and resume

The idempotency key is unique per request digest. A duplicate returns the prior result or `DUPLICATE_IDEMPOTENCY_KEY`; it never repeats side effects. Resume requires the same task, repository, procedure version, request digest, scope hash and compatible checkpoint revision.

## Failure classification

- `INVALID_INPUT`
- `SCOPE_VIOLATION`
- `UNSUPPORTED_PROCEDURE`
- `PARTIAL_RESULT`
- `TOOL_UNAVAILABLE`
- `STALE_CHECKPOINT`
- `DUPLICATE_IDEMPOTENCY_KEY`
- `PROVIDER_NOT_PUBLISHED`

## Provider provenance

Current BMAD is `6.10.0-pinned`, source `nhatnguyenquang1838-coder/BMAD-METHOD@bb45db4aa4496c69239f9c0629c290fd1b072fc9`, state `ready-unpublished`. This exact pin may be used for design/validation; publication-dependent execution must return `PROVIDER_NOT_PUBLISHED`. No implicit latest version is allowed.
