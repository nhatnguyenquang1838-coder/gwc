# SCRUM-269 Rev4 — Release Note (G6)

**Released**: 2026-08-26
**Merged commit**: e518f867 (fast-forward to main)
**PR**: #524 (G4 APPROVE: Nhat Nguyen Quang)
**Risk class**: R2

## What shipped
Evidence ledger hardening — 4 G1 fixes (Rev3→Rev4) + G1/G3 test coverage:

| Fix | File | Verification |
|---|---|---|
| Ed25519 DSSE verification | ledger_replay_verifier.py | real Ed25519 verify; forged sig → DSSE_SIGNATURE_INVALID |
| digest_chain payload cross-check | ledger_replay_verifier.py | payload_digest ≠ event_digest → DIGEST_CHAIN_MISMATCH |
| Root Merkle root comparison | ledger_replay_verifier.py | tampered leaf → ROOT_MERKLE_MISMATCH |
| File locking (fcntl) | (Rev3, in ledger) | concurrent-safe append |
| Quarantine routing (L3.3) | VerificationReport.quarantine | FAILs isolated w/ reason+detected_at |
| SLO timings (L3.5) | VerificationReport.timings | per-boundary latency (s) |
| Lease TTL (L3.4) | VerificationReport.lease_status | >30min stale → STALLED |

## Evidence
- G1+G3 test suite: **7/7 PASS**
- GV suite (10 golden vectors): **20/20 PASS** (clean); adversarial fixtures correctly fail
- Zero regression vs 20/20 baseline
- Dual-read v1/v2 compat: preserved (v2 fields optional for v1 records)

## Provenance
- Dedicated branch: auto/scrum-269-node-architect-rev4 (off f8e25602)
- G2 scope_hash: 2f51406b369d4ae19284b87d66ef5e24c487cd22275bd8177168ddbfeaa3c2bf
- Authority flags: all false (governance lane)
- 4-lens review: 4/4 APPROVE (L1/L2/L3 APPROVE, L4 IMPLEMENTABLE, G1 PASS)

## Out of scope (deferred)
- v2 as NEW schema file (evidence-ledger-v2.schema.json) — v1 untouched per L4 contract
- Quarantine auto-purge (L3.6 retention) — detection present, purge deferred
- SLO dashboard emission — timings captured, export deferred
