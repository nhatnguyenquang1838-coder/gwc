# G1 execution feasibility and HUMAN BYPASS

- Require G1 process readback and an end-to-end execution-feasibility route matrix before G1 PASS.
- Fail closed when a mandatory route step has an unknown or hard-blocked capability, lacks continuation, or cannot produce deterministic evidence.
- Add a one-time, step-bound HUMAN BYPASS record with expiry, append-only runtime events, exact readback, checkpoint-after evidence, drift invalidation, and idempotent resume.
- Preserve G2-G6 authority boundaries: HUMAN BYPASS cannot skip validation/CI or authorize protected-branch, merge, deploy, release, production, migration, credential, secret, destructive, or history-rewrite actions.
