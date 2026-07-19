# G2 Execution Skill Library

## Purpose

Deterministic offline skill cards for G2_EXECUTION gate operations. These cards provide Context7-compatible guidance for execution planning, repository interaction, and approval envelope generation.

## Source mode

`OFFLINE_PINNED` — used when Context7 is unavailable, forbidden, timeout, or incomplete.

## Compatible gates

- G2_EXECUTION

## Contents

- `skills/g2-execution-plan.md` — Transactional execution sequence blueprint
- `skills/g2-repository-interaction.md` — Allowed/prohibited action constraint layer
- `skills/g2-approval-envelope.md` — G2 approval envelope generation

## Authority

These cards do not grant merge, deployment, release, production configuration, credential, migration, or production-data authority.