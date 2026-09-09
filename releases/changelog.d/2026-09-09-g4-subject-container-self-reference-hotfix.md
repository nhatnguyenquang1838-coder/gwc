# G4 approval-subject / evidence-container self-reference hotfix

- Fail closed when `merge_approved_pr` semantic scope includes its own
  `.gwc/tasks/<task-id>/g4/**` evidence container.
- Add the canonical G4 subject/container contract and pure validation helper.
- Preserve the established SCRUM-233/SCRUM-234 model: G4 semantic subject is
  immutable; trusted receipt binds the descendant executable PR tip.
- Add SCRUM-669 regression coverage so G4 evidence materialization does not
  trigger recursive scope re-hashing or a second evidence commit.
- No merge/deploy/production authority is granted by this hotfix.
