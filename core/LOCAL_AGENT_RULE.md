
# Local Agent Rule

## Scope

This rule applies to an agent running on a user's local machine with access to
a local filesystem, shell, repository checkout, Git, and worktrees.

## Pre-approval local activity

After the applicable read-only inspection gate, the local agent may create
proposal artifacts only in an isolated non-repository session directory.

Recommended structure:

```text
<session-root>/<task-id>/proposal/
├── written-proposal.md
├── change-plan.yaml
├── overview.mmd
├── detailed.svg
├── detailed.png
├── approval-envelope.yaml
└── artifact-hashes.txt
```

Creating these proposal artifacts does not authorize repository writes.

## Repository boundary before exact G2 approval

Before a valid exact scoped approval token, the local agent must not:

- create a Git branch;
- create a Git worktree;
- modify tracked repository files;
- create Kiro specs inside the repository;
- install dependencies;
- run repository-controlled scripts or hooks;
- commit;
- push;
- open or update a Pull Request;
- claim or update an external work item unless explicitly authorized;
- modify any remote service.

## Proposal requirements

Before requesting G2, the agent must materialize and validate:

- written scope;
- change plan;
- Mermaid overview;
- detailed SVG;
- PNG derived from the visual source;
- artifact hashes;
- approval envelope;
- canonical scope hash.

Failure code:

```text
PROPOSAL_ARTIFACTS_INCOMPLETE
```

The agent must not request G2 after this failure.

## Exact approval

Valid format:

```text
APPROVE <approval_id> <first-16-characters-of-scope_hash>
```

The token must match the current unexpired envelope exactly.

## Post-approval execution

After exact approval, the agent may create the approved branch/worktree,
modify only approved files, run inspected validation, push the approved
branch, and create or update the Draft PR when these actions are present in
the envelope.

## Mandatory reapproval

Stop and generate a scope delta when:

- base SHA changes;
- another actor changes the working branch;
- files or modules expand materially;
- an unapproved dependency is required;
- architecture, API, auth, security, data behavior, deployment, production
  configuration, schema, migration, or production-data scope changes;
- artifact hashes no longer describe the work;
- approval expires.

## Local command safety

Before running any repository-controlled command:

1. Read the script definition.
2. Inspect hooks, lifecycle actions, plugins, and generated commands.
3. Confirm the command is inside the approved scope.
4. Record the sanitized command and result.
5. Stop if secrets or destructive actions are detected.
