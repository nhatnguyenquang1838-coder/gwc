# SCRUM-192 — Requirements

## Goal
Replay-safe `blocked_action_escalation` for the gate_authority node family (MAT-F2-N09).

## Functional requirements
- R1: Escalation is deterministic and replay-safe (same inputs → same decision + digest).
- R2: Enforce checkpoint-before-wait (no continuation before explicit checkpoint).
- R3: Remediation is minimal and exact (no scope creep beyond the blocked action).
- R4: No unauthorized continuation; blocked actions cannot be auto-promoted.
- R5: Closed schema validates the escalation envelope.

## Non-functional
- N1: No external/network calls (offline deterministic).
- N2: No execution authority granted.

## Dependencies
- SCRUM-184..191 (all merged to main).
