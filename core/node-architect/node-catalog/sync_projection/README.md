# sync_projection node family

Task: `REVAMP-GWC-022`  
Batch: `batch-06-sync-projection`  
Family: `sync_projection`  
Planned nodes: 9  
Authority boundary: `read_only`; applicability gates: `G2_EXECUTION_G3_PR`

This family defines controlled audit-projection nodes for DS Admin, Task Center, and external audit surfaces. Canonical repository, gate, PR, CI, and task evidence remains authoritative; projected state is never approval or execution authority.

## Scope

Allowed:

- add exactly 9 `sync_projection` node descriptors;
- add one family README;
- add a stdlib validator and focused unit tests;
- add package export entries;
- add a changelog fragment.

Forbidden:

- implementing DS Admin, Task Center, or connector runtimes;
- making projected state canonical;
- projecting secrets, credentials, production configuration, production data, or hidden reasoning;
- implementing the full 81-node catalog;
- runtime engine, scheduler, or worker implementation;
- merge, auto-merge, deploy, or release changes;
- package version changes.

## Nodes

| Node | Type | Applicability gates |
|---|---|---|
| `sync-projection-ds-admin-state-projection` | projection | G2, G3 |
| `sync-projection-task-center-sync` | connector | G2, G3 |
| `sync-projection-external-audit-event-projection` | projection | G2, G3 |
| `sync-projection-projection-source-authority-check` | gate | G2 |
| `sync-projection-projection-drift-detection` | workflow | G2, G3 |
| `sync-projection-projection-reconcile-readback` | workflow | G2, G3 |
| `sync-projection-projection-failure-routing` | workflow | G2, G3 |
| `sync-projection-projection-evidence-linking` | projection | G2, G3 |
| `sync-projection-projection-privacy-boundary-check` | gate | G2, G3 |

## Guardrails

```text
✅ exactly 9 nodes
✅ canonical=audit_projection
✅ authority_boundary=read_only
✅ gates are applicability metadata limited to G2_EXECUTION and G3_PR
✅ source authority, drift detection, readback, failure routing, evidence linking, and privacy boundary are explicit
✅ external projection is audit evidence only
❌ no G2/G3/G4/G5/G6 authority grant from projection state
❌ no runtime or connector implementation
❌ no package version change
```

## M4 runtime contracts

Runtime contracts extend the thin descriptors without turning projection state into authority. The evaluator layer is pure: it performs no connector call, network request, filesystem mutation, Jira transition, branch/PR action, approval, merge, deployment, release, or production operation.

| Descriptor | Runtime artifact | Schema | Evaluator | Maturity |
|---|---|---|---|---|
| `projection-source-authority-check.node.json` | `projection-source-authority-decision` | `schemas/projection-source-authority-decision.schema.json` | `tools/node_architect/projection_source_authority_check.py` | M4 deterministic |

### Projection source authority decision

`decide_projection_source_authority(...)` fails closed unless every requested projected field is bound to exact, current, canonical evidence. It rejects:

- missing canonical sources;
- projection/advisory-only authority;
- unbound or inferred fields;
- ambiguous or conflicting bindings;
- revision or digest mismatch;
- stale source or readback evidence;
- unknown deterministic derivation rules.

The output is a closed `schema_version: "1.0"` artifact with deterministic ordering and a `sha256:` decision digest. Output `observed_at` and `decision_digest` are excluded from digest input; evidence timestamps remain semantic. Every authority grant remains fixed to `false`, while `read_only_projection` remains fixed to `true`.

### Projection evidence linkset

`build_projection_evidence_linkset(...)` consumes a schema-valid `projection-source-authority-decision` from SCRUM-223 and emits an immutable, deterministic `projection-evidence-linkset`. Every supporting link carries an exact ref, revision and `sha256:` content digest; a display URL is navigation-only and can never substitute for immutable evidence.

The evaluator canonicalizes field paths and link ordering, collapses semantic duplicates, preserves explicit supersession history, and fails closed for blocked or mismatched source authority, missing immutable references, broken/stale/unverified evidence, digest conflicts, uncovered fields and expected-digest drift. It performs no connector call, URL fetch, filesystem read, persistence, target projection, approval, merge, deployment or production operation.

| Descriptor | Runtime artifact | Schema | Evaluator | Maturity |
|---|---|---|---|---|
| `projection-evidence-linking.node.json` | `projection-evidence-linkset` | `schemas/projection-evidence-linkset.schema.json` | `tools/node_architect/projection_evidence_linking.py` | M4 deterministic |

### Projection privacy boundary check

`decide_projection_privacy(...)` consumes a schema-valid, `READY` `projection-source-authority-decision` from SCRUM-223 (bound to the same task/repository/target) and a bounded candidate payload, then sanitizes it before any DS Admin, Task Center or external audit projection. It enforces a closed 12-class classification model and a mandatory protected-key detection list (`password`, `secret`, `token`, `access_token`, `refresh_token`, `authorization`, `credential`, `private_key`, `client_secret`, `cookie`, `session`, `connection_string`, `production_record`, `chain_of_thought`).

The evaluator fails closed (in deterministic precedence) for: invalid input; missing/blocked/mismatched source authority; an unclassified protected key; any `SECRET`/`CREDENTIAL`/`TOKEN`/`PRIVATE_KEY`/`PRODUCTION_DATA`/`HIDDEN_REASONING` value; a target policy that does not allow a classified field; an invalid redaction directive; payload size/depth limits; and any residual protected value surviving sanitization. Approved `PERSONAL_SENSITIVE`/`CONFIDENTIAL_METADATA`/`POLICY_REDACTED` fields are redacted (replaced with `[REDACTED]`) or removed per the explicit per-target policy; redaction records carry only field path, classification, action, replacement token and reason code — never the original value.

The output is a closed `schema_version: "1.0"` artifact with deterministic ordering and order-independent `sanitized_digest` (over the sanitized payload + non-sensitive semantic metadata) and `decision_digest`. Raw candidate values, timestamps and navigation URLs are excluded from the hash; any safe-value, policy-revision or redaction drift changes the applicable digest. Every authority grant remains fixed to `false`, while `read_only_projection` remains fixed to `true`.

| Descriptor | Runtime artifact | Schema | Evaluator | Maturity |
|---|---|---|---|---|
| `projection-privacy-boundary-check.node.json` | `projection-privacy-decision` | `schemas/projection-privacy-decision.schema.json` | `tools/node_architect/projection_privacy_boundary_check.py` | M4 deterministic |
