# SCRUM-204 — Universal resume-token node contract

Task: `SCRUM-204`

- Add the instruction-backed `runtime_checkpoint.resume-token-generation` node and G2 route.
- Bind generated resume tokens to task, run, scope, base/head, checkpoint state, lease, fencing, and next-action context.
- Preserve legacy checkpoint/resume-token validation while failing closed for expanded-contract tampering or authority escalation.
- Validate the node instruction contract and runtime route across normal, fastlane, e2e, hotfix, and rescue modes.

This G2 artifact does not authorize merge, deployment, release, production changes, or later gate execution.
