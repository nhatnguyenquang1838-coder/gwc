# SCRUM-142 Revisit Review — Non-Retroactive Remediation

## Decision

`REOPEN_REMEDIATION_REQUIRED`

Current authoritative repository base: `nhatnguyenquang1838-coder/gwc@c855336dc17f20115e640516107999b08e9d783e`.

## Findings

| Severity | Finding | Evidence | Required correction |
|---|---|---|---|
| BLOCKER | Committed G0/G1 files are custom summaries, not canonical schema instances. | PR #109 changed the five files; current contents lack canonical schema fields. | Replace all five and validate before any new write. |
| BLOCKER | No committed G2 execution envelope exists for the prior repository writes. | PR #109 changed exactly eight files; no `g2/**`. | Create a fresh, current-base envelope. Do not backdate it. |
| BLOCKER | No G3 delivery record or G4 merge artifact exists although PR #109 was created, promoted and merged. | No `g3/**` or `g4/**` in the PR or current task tree. | Treat prior sequence as an audit defect; use new G3/G4 gates for repair PR. |
| MAJOR | No post-merge G5 evidence is visible for merge `c855336dc17f20115e640516107999b08e9d783e`. | Commit workflow lookup returned no push/main runs through the connector. | Require exact post-merge lookup or accepted human-observed evidence after repair merge. |
| MAJOR | Graph is stale relative to SCRUM-105. | Original base `76644885...`; PR #108 merged durable runtime contracts before PR #109 merge. | Full UA refresh from current main and include all K1 surfaces. |
| MAJOR | Prior output was only “UA-compatible,” not an actual `/understand` execution. | PR body explicitly records no direct UA engine run. | Run the actual skill from a trusted local checkout. |
| MAJOR | Jira `Done` conflicts with missing canonical evidence. | Jira moved In Review → Done at 2026-07-26 20:32:56 +07. | Reopen as work-tracking projection while remediation is pending. |
| MINOR | The merged report still says G2 is required for a write that already occurred. | `ua-refresh-report.md` retained pre-write status language. | Rewrite report as completed refresh evidence after actual UA run. |

## Non-retroactive rule

This repair must not fabricate historical G2/G3/G4/G5 authorization. It creates a new bounded lane from current main and records the previous deficiency as audit evidence.

## Selected scope

Scope hash: `sha256:fccfa84b02f6e178b4d14342759c7eebc5149f7c7ece4b5df3808f6cdee8620b`

Approval command:

```text
APPROVE_G2_SCRUM_142_REVISIT_R2 sha256:fccfa84b02f6e178b4d14342759c7eebc5149f7c7ece4b5df3808f6cdee8620b c855336dc17f20115e640516107999b08e9d783e 2026-07-27T13:50:33Z
```
