# DWC Repository Operations Contract

## Scope

This contract applies to the DWC runtime operating on
`nhatnguyenquang1838-coder/gwc` through the verified `DWC` connector.

It records repository permissions granted by higher-priority platform and
project runtime instructions. It does not independently weaken the canonical
core policy for other agents or repositories.

## Mission

Allow DWC to inspect, maintain, validate, and deliver bounded changes to this
repository through a guarded branch and Draft Pull Request while enforcing the
canonical GWC gate lifecycle.

## Mandatory boot and gate enforcement

Before any repository-changing action, DWC must read and follow:

1. `AGENTS.md`;
2. `core/Coding_Project_Governance_v1.0.md`;
3. `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`;
4. `core/E2E_DRAFT_PR_DELIVERY_RULE.md`;
5. `projects/gwc/project-profile.yaml`;
6. `projects/gwc/project-instructions.md`;
7. `projects/gwc/project-extension.md`;
8. `agents/dwc/capabilities.yaml`;
9. the task, target repository governance, package, spec, and workflow evidence
   relevant to the requested outcome.

DWC must resolve one execution mode before gate reporting:

- `chat_connector_only` — repository connectors are available, but no trusted
  local checkout/shell validator is available;
- `local_agent` — trusted local checkout, filesystem, shell, Git, and isolated
  worktree/session are available;
- `repo_ci` — running inside CI against committed artifacts.

## Connector precedence

When more than one repository connector is available, DWC must use them in this
order:

1. GitHub connector.
2. DWC connector.
3. DW1 connector.

DWC must not silently skip a higher-priority connector that is available and
authorized.

DWC must visibly report `GWC BOOT`, execution mode, G0, G1, G2, and G3 status
for repository-changing work. A gate may be reported as complete only when its
canonical repository artifact exists and validation has passed or trusted
validator evidence is cited.

DWC must not create a branch, update a file, create a commit, push a ref, or open
a Pull Request while required G0/G1 evidence is missing or invalid for the
current execution mode. It must not invoke a connector action first and backfill
the artifacts later.

## Execution mode rules

### chat_connector_only

DWC may inspect repository, task, PR, CI, and governance context. It may produce
a conversation-local gate packet and identify blockers.

DWC must not claim `G1_ALIGNMENT: PASS` or perform write-capable connector
actions in chat connector mode unless trusted external validator evidence and a
valid envelope already exist.

When validator evidence is unavailable, DWC must stop before writes with:

```text
G1_ALIGNMENT: BLOCKED — validator unavailable in chat_connector_only mode
```

### local_agent

DWC must materialize task-scoped G0/G1 artifacts, run
`tools/validate_g01.py`, retain validator evidence, and only then enter G2 or
create a guarded branch/worktree.

### repo_ci

DWC treats CI as a second boundary. CI may validate committed artifacts and
policy after a branch or PR exists, but CI success does not retroactively
authorize pre-write actions and never grants G4, G5, or G6 authority.

## Automatic inspection — G0

DWC may automatically perform read-only operations needed to understand a task:

- inspect repository metadata, branches, tree, files, binary artifacts, PRs,
  workflow runs, and workflow artifacts;
- read governance and project context from the protected base;
- compare refs, hashes, package versions, consumers, and CI evidence;
- inspect the matching task record from the active work-tracking provider.

Automatic inspection does not itself complete G0. DWC must create, obtain, or
cite the task-scoped G0 context artifact and validate that it is `READY` with no
blockers. Until then, only read-only actions are allowed.

## Automatic alignment — G1

DWC may automatically reconstruct the problem, scope, non-goals, constraints,
risks, acceptance criteria, options, and recommended decision.

Automatic analysis does not itself complete G1. DWC must create, obtain, or cite
the canonical G1 intake, preflight, options, and decision artifacts and run or
cite validator evidence for:

```text
python tools/validate_g01.py --workspace <task-workspace>
```

G1 is complete only when the result is `PASS`. A user instruction such as
“apply fix” may select the bounded outcome but does not replace the required G1
artifacts or validator.

## Automatic bounded execution — G2

DWC may execute a bounded, non-risk repository change only when all of the
following are true:

- G0 is `READY`;
- G1 is `PASS`;
- the user requested the outcome;
- repository identity and protected base are verified;
- exactly one valid task from the active work-tracking provider represents the work when required by profile;
- a valid execution or approval envelope matches the task, repository, base SHA,
  guarded branch, scope hash, file/module scope, risk, and intended actions;
- the scope is explicit and limited to the requested result;
- a dedicated allowed-prefix branch and isolated worktree/session are used;
- no protected branch is written directly;
- no secret, production configuration, production data, destructive action,
  financial impact, architecture change, security-boundary change, or broad
  blast radius is introduced unless explicit human direction is recorded;
- validation and complete diff review are performed before G3.

Before every write-capable connector call, DWC must verify that the exact action
is listed in the active envelope and valid for the current execution mode. If
not, DWC must stop with `GATE_ACTION_NOT_AUTHORIZED`.

Within a valid G2 boundary DWC may create the guarded branch, create or update
repository files required by the task, add tests and documentation, push
commits, inspect CI, and repair repository-fixable CI failures.

For generated integrity-artifact refreshes, DWC may auto-wrap the action in a
machine-generated approval envelope only when:

- the branch is guarded and not `main`;
- the artifact source is a verified generator;
- validation has passed;
- the action does not grant merge permission.

That envelope is an internal audit record for the bounded branch write and is
not a human approval token. It does not relax G4 or authorize merge.

## Draft PR delivery — G3

After G2 validation and complete diff review, DWC may create or update a Draft
Pull Request only within a valid G3 boundary. G3 then uses three internal stages:

```text
PR Assembly → Independent Review → Review Closure
```

The task-scoped `g3/delivery-record.yaml` must identify:

- repository, task, base SHA, working branch, Draft PR, and exact head SHA;
- changed paths, validation evidence, required CI evidence, exclusions, and residual risks;
- implementer and read-only reviewer identities;
- reviewer independence as `independent` or the weaker `fresh-context` fallback;
- applicable requirement, design, code, test, governance, delivery, and CI lanes;
- acceptance-criteria evidence and findings classified as `BLOCKER`, `MAJOR`, `MINOR`, or `NIT`;
- exact reviewed head SHA, scope hash, stale state, review decision, and final outcome.

DWC must not allow the reviewer to modify the delivery during G3. Blocking findings return to G2 for separately authorized revision. Any new branch head SHA invalidates previous review evidence and requires another read-only review.

G3 may pass only when `tools/validate_g3_delivery.py` returns `PASS` for the current delivery record, the review and required CI evidence match the exact current head SHA, all applicable lanes and acceptance criteria are satisfied, no unresolved `BLOCKER` remains, and every `MAJOR` is resolved or explicitly accepted by a human for that exact head SHA.

The Draft PR remains the user review boundary. Reviewer `PASS` is evidence only and never grants merge, deployment, release, or production authority.

### Ready-for-review connector action contract

When `github_mark_pr_ready_for_review` is available, DWC may invoke it only as G3 metadata completion after G3 `PASS`. The action must accept at minimum:

```text
owner
repo
pr_number
expected_head_sha
```

Before invoking it, DWC must verify the latest PR head SHA equals `expected_head_sha`, required CI is `success` for that exact SHA, review closure and the G3 delivery record are non-stale, the PR is still Draft, and there is no scope drift. The connector must fail closed if any of those checks cannot be verified.

This action grants no merge permission. It must not mark another PR ready, change the PR base, enable auto-merge, merge, deploy, release, modify production configuration, access credentials, or access production data. If the tool is unavailable, DWC must record a `ready-for-review blocker` and wait for manual UI promotion before G4.

## Asynchronous CI continuation

During G3 validation monitoring, DWC must not stop silently when PR CI is still running. It must keep the active work-tracking task in its validation state and record the current PR, branch, latest head SHA, next check time, and selected continuation mechanism.

DWC must choose the strongest available mechanism in this order:

1. GitHub CI event callback, including `github_ci_event_handle`, when available;
2. local sleep or polling when running as `local_agent`;
3. scheduler-backed continuation, including cron or platform Scheduled Tasks when available;
4. manual checkpoint when no async mechanism is available.

The default next-check interval is 3 minutes when supported. If the active runtime or scheduler supports only a longer cadence, DWC must use the supported cadence and report the limitation.

A scheduled continuation is valid only when a concrete next run is visible or recorded. If there is no next run, including a UI state such as `Chưa lên lịch`, DWC must treat the schedule as inactive.

If CI fails, DWC may inspect workflow logs and repair only repository-fixable failures within the active G2 scope. After every repair commit, DWC must record the new head SHA and treat prior CI, review, and G4-readiness evidence as stale. DWC must not merge, deploy, release, reload runtime, touch production configuration, handle credentials, run migrations, or access production data from a CI wait task unless a separate active approval covers that exact action.

## Proactive gate transitions

DWC must proactively generate the next gate's entry artifact and present the
approval command to the user upon completing any gate's exit criteria. This
ensures the user always has a clear, actionable next step without needing to
ask for it.

- Upon G1 `PASS`, immediately generate the G2 execution envelope and present
  the approval command to the user.
- Upon G2 exit, immediately generate the G3 delivery record and present the
  approval command to the user.
- Upon G3 `PASS`, mark the Draft PR ready for review when `github_mark_pr_ready_for_review` is available and current evidence is valid, then immediately generate the G4 merge approval request and present the approval command to the user.
- Upon G4 exit, automatically run read-only `G5_STATUS_VERIFY` for the merge commit. Generate a G5 approval command only for manual deploy, redeploy, release, publish, or runtime reload.
- Upon G5 exit, generate the G6 production-operation approval request only when
  production data, production configuration, migrations, credentials, or secrets
  are actually in scope. Otherwise record G6 as `not_applicable` and do not
  generate a G6 command.

Each generated command must be placed in a standalone fenced text block. DWC
must wait for the user to execute the command before proceeding. The user
retains sole authority to grant or deny the next gate.

## Human-direction categories

Explicit human direction is required before G2/G3 execution when the task has
any of these characteristics:

- financial impact;
- architecture change;
- security-boundary change;
- production configuration;
- credential or secret change;
- production data access;
- destructive or irreversible action;
- broad blast radius.

A user request that explicitly asks DWC to create the bounded PR for one of
these categories satisfies the human-direction requirement only for the exact
G2/G3 scope recorded in the artifacts. It does not grant merge, deploy, release,
or production authority.

## G4, G5, and G6

G4 merge, G5 deploy, and G6 production operations always require a separate
human decision recorded for the exact repository, task, PR or release, head SHA,
scope hash, action, environment, and expiry where applicable.

When G3 has passed and the connector exposes `github_mark_pr_ready_for_review`, DWC may mark the Draft PR ready for review after verifying the latest PR head SHA, required CI success, review closure, G3 evidence, and no scope drift. This action is G3 metadata completion only; it does not grant merge authority.

When an exact G4 approval command is active and the connector exposes
`github_merge_pr`, DWC must refresh PR state, verify the approved PR head SHA,
confirm required CI checks passed for that same head, verify that the PR is not
Draft and is ready for review, and then invoke `github_merge_pr` for that PR
only. If the connector does not expose the tool, DWC must record a manual-merge blocker instead of claiming merge execution. If the PR is still Draft and no
ready-for-review connector is available, DWC must record a ready-for-review
blocker and must not invoke merge.

G5 is status/deployment verification. Read-only `G5_STATUS_VERIFY` after G4 merge is automatic for the approved commit. When the project integrates Vercel or
other deployment status into GitHub Actions, G5 checks the relevant post-merge
workflow or deployment checks for the approved commit. DWC must not perform a
manual deploy, redeploy, release, publish, or runtime reload unless that exact
manual action is explicitly included in the G5 scope.

Approval for one gate never grants another gate.

## Permanent exclusions without the matching gate

DWC must not automatically:

- push directly to `main` or another protected branch;
- merge, enable auto-merge, close another actor's PR, or change a PR base;
- force-push, delete branches, or rewrite shared history;
- deploy, publish a release, or modify production configuration;
- create, expose, rotate, or commit credentials and secrets;
- read or write production data;
- perform destructive migrations or irreversible operations.

## Work-tracking state synchronization

DWC must keep the active work-tracking provider aligned with task progress before
continuing to the next major action. Use legal provider transitions only:

| Gate moment | Work-tracking target |
|---|---|
| G0/G1 work starts | `agent_running` |
| Proposal ready | `pending_review` |
| Plan selected | `pending_approval` |
| G2 write starts | `write_running` |
| PR created | `validation_running` |
| Validation complete | `completed` |
| Blocker | `blocked` |
| Irrecoverable failure | `failed` |

If the work-tracking provider was not updated at the correct time, DWC may perform a late
reconciliation only when it labels it as late reconciliation and cites current
repository/task evidence. It must not backfill evidence or claim the task was in
that state earlier.

## Bootstrap capability rollout

When a new connector capability is required to complete its own first rollout,
DWC must declare a bootstrap gap. The first merge or deployment may require a
manual human action or an existing pre-authorized platform route. After the new
runtime is deployed and its tool surface is verified, future executions must use
the connector capability and normal gate checks.

## Connector trace evidence

When a connector operation succeeds or fails after reaching the DW1/DWC backend, DWC should consume and report the structured envelope defined by `core/CONNECTOR_TRACE_CONTRACT_v1.0.md` and validated by `schemas/connector-trace.schema.json`.

DWC must not attribute a failure to a platform safety layer, connector policy, or GitHub API unless the structured trace or a platform-native error identifies that boundary. When the response lacks sufficient evidence, report `stage: unknown` and preserve the limitation.

Runtime backend conformance is a bootstrap gap until the repository owning the DW1 connector implementation adopts and deploys the contract. GWC contract presence alone is not runtime evidence.

## Sanitized evidence notes

DWC must not place full executable approval commands in commit messages, PR
titles, connector payloads, or long-lived comments. Use sanitized evidence
metadata such as gate, approval ID, scope-hash prefix, expected SHA, and expiry.

## Completion evidence

A DWC repository task is complete only when the required gate records exist,
the Draft PR exists, the latest head SHA is known, applicable validation is
recorded, CI state is reported, active work-tracking state is synchronized or late
reconciled, and exclusions and residual risks are stated accurately.
