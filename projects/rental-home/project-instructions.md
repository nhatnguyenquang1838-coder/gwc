
# Rental Home Project Instructions

## Core rule

`AGENTS.md` in the protected base is the project-specific source of truth.
Do not add extra process unless required by `AGENTS.md`, the canonical core
policy, this extension, or the user.

## Language

Use English for repository artifacts unless the task requires Vietnamese.
Keep technical terms such as spec, workflow, PR, validation, RLS, Supabase,
Figma, and Mermaid unchanged.

## Session and branch rule

- One unique session directory per task.
- One isolated worktree/folder per branch.
- Do not reuse a worktree for another branch.
- Keep proposal, logs, screenshots, diagrams, and reports inside the session
  directory.

## Required task context

Before implementation, identify:

- repository;
- base branch and full base SHA;
- dedicated working branch;
- task/spec identifier;
- required frontend, backend, UI, database, or testing skills;
- location of requirements, design, tasks, conventions, and acceptance criteria;
- affected data entities, RLS policies, APIs, screens, and workflows;
- validation commands discovered from the protected base.

## Delivery

Use Draft Pull Requests for reviewed delivery. Do not merge or deploy without
separate authority. Record:

- changed files;
- behavior;
- tests;
- validation;
- screenshots or visual evidence when UI changes;
- migration and configuration status;
- residual risks.
