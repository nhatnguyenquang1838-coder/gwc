# G4 Approval Subject / Evidence Container Contract v1.0

## Purpose

Eliminate recursive G4 approval invalidation when the canonical G4 evidence
artifact is committed on top of the semantic merge subject.

## Canonical model

G4 has two distinct identities:

1. **Approval subject** — the exact pre-container PR head and approved semantic
   paths/actions whose scope hash is presented to the human.
2. **Evidence/current-tip container** — the descendant PR head that may add only
   task-scoped `.gwc/tasks/<task-id>/g4/**` evidence and is bound by trusted
   PR-native G4 receipt readback.

The G4 artifact is evidence *about* the approval subject. It is never part of
its own approval subject.

## Invariants

- `G4_APPROVAL_SUBJECT_IS_NOT_G4_EVIDENCE_CONTAINER`.
- `G4_ARTIFACT_MUST_NOT_SELF_REFERENCE_ITS_CONTAINER_COMMIT`.
- A `merge_approved_pr` semantic scope containing `.gwc/tasks/<task-id>/g4/**`
  is invalid and must fail closed with `SCOPE_SELF_REFERENCE`.
- The current PR head must equal or descend from the approval-subject head.
- The complete subject-to-current delta must contain only
  `.gwc/tasks/<task-id>/g4/**` for the subject approval to remain valid.
- Any source, test, workflow, configuration, unrelated governance, or other
  non-G4-evidence delta after the approval subject invalidates G4 readiness.
- Trusted receipt `approved_head_sha` binds the exact executable current PR tip.
- Trusted receipt `scope_hash_prefix` binds the immutable approval-subject scope.
- Materializing the first G4 evidence artifact must not require a second G4
  artifact or recursive reapproval solely because the evidence container moved
  the PR tip.
- Human approval and trusted receipt remain separate from merge execution; this
  contract never grants merge authority by itself.

## Canonical validation

Use `tools/node_architect/g4_subject_container.py` after repository readback has
proved ancestry and the complete subject-to-current changed-path set. The
validator is pure and returns PASS/BLOCKED only. It never performs a connector
write or grants authority.

`tools/node_architect/scope_hash_calculation.py` independently rejects any
`merge_approved_pr` scope that tries to hash the task's own G4 evidence path
back into the approval subject.

This is the G4 counterpart of the G3 external-current-tip/self-reference
separation: immutable semantic subject plus trusted external current-tip proof.
