# Coding Guide — SCRUM-101

## Verified paths

- `projects/gwc/project-profile.yaml`
- `projects/gwc/project-instructions.md`
- `projects/gwc/project-extension.md`
- `docs/project-consumer-agent-instructions.md`

## Required approach

1. Re-read every target file from the exact protected base.
2. Locate and extend the current mechanism.
3. Add failing tests before behavior-changing edits.
4. Keep authority and evidence binding explicit.
5. Reject silent compatibility breaks.
6. Review the full diff for generated noise and scope drift.

## Prohibited changes

- No direct write to `main`.
- No merge, release, deployment or production operation.
- No weakening of G0-G6 authority.
- No free-form LLM text as executable guard or policy.
- No opportunistic refactor outside the Jira task.
