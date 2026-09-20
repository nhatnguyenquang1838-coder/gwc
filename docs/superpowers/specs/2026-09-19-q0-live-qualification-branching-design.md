# Q0 Live Qualification Branching & Self-Fix Design

## Decision

Adopt Linear Chained Defect Branches + SHA-based Q0 Baseline for SCRUM-781 and future equivalent live runtime qualification lanes.

## Problem

Prior runtime fixes could be implemented and unit-tested without proof that the active runtime actually loaded the fixed identity. Long-lived sessions, imported modules, instruction bundles, compiled controller contracts, plans, route decisions, cursor state, and cached evidence may remain stale after Git HEAD changes. Protected `main` was also incorrectly treated as the immediate live-test oracle even when qualification was intentionally occurring on an unmerged fix lineage.

## Design

Keep four identities separate: protected base, accepted Q0 baseline, current candidate fix, and final certified Q0 SHA. For each independent runtime defect, branch from the latest accepted Q0 SHA into an isolated worktree. A candidate becomes the next baseline only after source GREEN, runtime load proof, original-incident replay, forward progress beyond the old failure, broader relevant regression, and exact readback.

The runtime activation lifecycle is independent of the controller/conversation lifecycle. A long-lived controller may continue, but each material fix receives a new/rebound runtime activation with explicit loaded-source identity and stale-state invalidation.

## Acceptance

The repository must contain a canonical branching contract, operational runbook, machine-readable fix receipt schema, contract tests, and instruction routing. The change must not modify runtime implementation behavior itself.
