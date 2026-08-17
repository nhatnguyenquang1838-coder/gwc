# Implementation plan

**Fresh implementation session required.** Use TDD and exact-base drift readback before modifying source.

## Step 1
Define a versioned capability registry that separates semantic capabilities (read-only verify, repo write, PR mutation, merge, release, production data/config, secret, migration/destructive) from gate labels while preserving existing G0-G6 compatibility.

Validation checkpoint: run the narrowest relevant RED/GREEN tests and inspect the complete diff before proceeding.

## Step 2
Define a transitive-effect graph schema with exact source action identity, deterministic/conditional edges, affected repository/environment, capability, authority requirement, evidence/readback identity and digest.

Validation checkpoint: run the narrowest relevant RED/GREEN tests and inspect the complete diff before proceeding.

## Step 3
Extend gate-action authority packet/schema with effect graph ref/digest and requested capability identity using backward-compatible optional fields where safe.

Validation checkpoint: run the narrowest relevant RED/GREEN tests and inspect the complete diff before proceeding.

## Step 4
Extend validation to compute deterministic reachable closure and fail closed when any child capability/repository is unauthorized; safe read-only children must remain non-escalating.

Validation checkpoint: run the narrowest relevant RED/GREEN tests and inspect the complete diff before proceeding.

## Step 5
Bind evidence consumption to repository + event/action + branch/PR + exact SHA + run/check + gate/node identity and reject wrong-node reuse.

Validation checkpoint: run the narrowest relevant RED/GREEN tests and inspect the complete diff before proceeding.

## Step 6
Add regression fixture for G4 merge -> push main -> export archive -> release-dist write/delete, plus multi-repo, safe child, drift and replay cases.

Validation checkpoint: run the narrowest relevant RED/GREEN tests and inspect the complete diff before proceeding.

## Step 7
Update lifecycle documentation/map only where required to make capability/effect semantics normative without renumbering existing gates.

Validation checkpoint: run the narrowest relevant RED/GREEN tests and inspect the complete diff before proceeding.

## Delivery boundary
Implementation commits belong to a fresh G2-authorized implementation branch/session, not this spec-only branch. G3/G4/G5/G6 remain separate authority boundaries.
