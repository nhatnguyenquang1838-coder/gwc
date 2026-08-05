# SCRUM-185 Design (OPT-1)

Smallest compatible implementation of the live Jira contract: a closed approval-request schema, a pure deterministic generator, and focused M4 tests only.

- `approval_token` is a non-secret integrity identifier derived from canonical request content (task, repository, gate, action, exact bindings, scope_hash, request ID, actor target, issued/expiry, policy revision). It excludes raw secrets, credentials, comments, and projection metadata.
- Deterministic: identical canonical input yields identical token/command.
- The node never performs or authorizes the gated action; `authority_granted: false`.
- Preserves the existing descriptor and registry surface; leaves every later-gate action to its own gate.
