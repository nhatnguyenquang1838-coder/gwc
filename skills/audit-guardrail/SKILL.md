---
name: audit-guardrail
description: Perform the independent read-only exact-head audit triggered before standing G4 may merge an autonomous child PR to pre-prod; emit deterministic PASS/BLOCK evidence without merge authority.
when_to_use: Trigger at G4_PREPROD_AUDIT_TRIGGER and for historical Done-task reconciliation audits.
version: 0.1.0
project: gwc
owner: GWC
---

# Audit Guardrail Skill

## Boundary

This skill is read-only and fail-closed. It cannot approve, merge, mutate code, change tracker state, create authority, deploy, release, touch production config/data/secrets, or backfill historical evidence.

The auditor identity/context must be independent from the implementer. A same-context self-review is `BLOCK`.

## Exact evidence set

Audit the same task/repository/PR/current head across:
- canonical DAG and predecessor proof;
- parent authority lineage;
- G0 context;
- selected G1 decision only;
- derived G2 authority;
- current managed evidence;
- exact-head CI + required checks terminal success;
- independent G3 bound to the same head;
- scope/risk/path/action constraints;
- standing G4 applicability.

External canonical stores are valid when governing contracts designate them: GitHub PR/checks/Actions/comments/artifacts, Jira/DAG/tracker, repository managed evidence, and permitted authoritative receipt stores. Do not reject a historical task merely because a receipt is not repo-local.

## Deterministic receipt

Use `tools.node_architect.audit_guardrail.evaluate_g4_preprod_audit`. Output must bind exact base/head and include `audit_outcome=PASS|BLOCK`, blockers, evidence digest, receipt digest, `write_actions=[]`, `merge_authority=false`.

PASS feeds the separate standing G4 evaluator. BLOCK routes TaskController to bounded repair/retry or safe stop. Any head change stales the receipt and requires a fresh independent audit.

For historical Done-task audit, classify missing contemporaneous proof; never fabricate it.
