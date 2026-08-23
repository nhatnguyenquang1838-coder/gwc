# SCRUM-396 — Draft Amendments (research-level, for Human review)
# L1+L2+L3+L4 consolidated remediation → rewrite parent PROPOSAL/AC
# Sync targets: GWC schemas (node-runtime-evidence, workflow-run-observability, ci-observation)
#               + DW observation project (dw-observation fixtures: .run/.projection, observatory.ts)
# Boundary: research/tracking only. No code/PR/merge/deploy. No G2/G4.

## A. Canonical contract alignment (do NOT invent new vocabulary)

Existing contracts to REUSE (verbatim fields, no rename):
- `schemas/node-architect/node-runtime-evidence.schema.json` — `schema_version` const "1.0", `record_digest`, `idempotency_key`, Draft 2020-12.
- `schemas/workflow-run-observability.schema.json` — `decision_digest`, `observed_at`, `reason_code`, `classification`, `read_only_projection`.
- `schemas/ci-observation.schema.json` — `observation_digest`, `provider_payload_digest`, `classification`, `selected_runs`.
- `tools/node_architect/workflow_run_observability.py` — `canonical_json` + `digest_payload` (sha256: prefix) are the canonical digest primitives.
- DW observation: `projects/dw-observation/lib/observatory.ts` — normalized event `{sourceEventId, seq, occurredAt, eventType, source, actor, gate, nodeId, before, after, evidenceRefs, authorityRef, sourceDigest}`; UNKNOWN-not-invented rule.

New artifacts in SCRUM-396 scope (must cite the above, never shadow them):
- `DurableArtifactEnvelope` — binds `{artifact_kind, writer_schema_id, writer_schema_version, schema_digest, payload_digest, migration_lineage}`. Extends the existing evidence/observation digests; does NOT replace `record_digest`/`observation_digest`.
- `SchemaTrustManifest` — GWC-owned allowlist of writer_schema_id+version+profile. Verifier resolves through manifest only; artifact-recorded metadata is NOT an oracle.
- `MigrationOperationJournal` — durable states `DISCOVERED → TRUST_RESOLVED → COMPATIBILITY_CLASSIFIED → MIGRATION_PREPARED → OUTPUT_WRITTEN → OUTPUT_READBACK_VERIFIED → REPLAY_ELIGIBLE`; terminals `UNSUPPORTED | QUARANTINED | OUTCOME_UNKNOWN | FAILED`.

## B. Draft amended PROPOSAL

Introduce a provider-neutral durable-artifact compatibility layer bound to GWC's existing
evidence/observation contracts:
1. `DurableArtifactEnvelope` — writer schema identity + schema digest + payload digest + migration lineage, on top of existing `schema_version`/`record_digest`/`observation_digest`.
2. Compatibility resolver before checkpoint/evidence/observation interpretation: `EXACT | COMPATIBLE | MIGRATION_REQUIRED | UNSUPPORTED`; `UNKNOWN_SCHEMA_CANNOT_ENTER_REPLAY`.
3. `SchemaTrustManifest` (GWC-owned allowlist) — profile selection is policy-allowlisted, never artifact-authorized.
4. `MigrationOperationJournal` + copy-on-write migration (original immutable; derived lineage committed atomically with CAS/fsync/lease/fencing).
5. Deterministic error taxonomy + `OUTCOME_UNKNOWN` reconciliation + single retry owner + bounded backoff + poison→quarantine.
6. Cross-runtime conformance: golden vectors ≥2 independent implementations; semantic equivalence, not byte-equality on happy paths.
7. `CANONICALIZATION_NEVER_GRANTS_AUTHORITY` normative; digest PASS ≠ gate/actor/source authority.

## C. Draft amended ACCEPTANCE CRITERIA (map to 4 lanes)

### L1 Architecture
- AC1: `DurableArtifactEnvelope` schema (Draft 2020-12, `unevaluatedProperties:false`) với closed writer_schema_id/version + schema_digest + payload_digest + migration_lineage, tái dùng `schema_version` const pattern.
- AC2: Resolver state machine `EXACT/COMPATIBLE/MIGRATION_REQUIRED/UNSUPPORTED` trước replay; unique acyclic migration DAG (5 packages).
- AC3: Reader/registry generation pinned cho cả attempt; no hidden live reads downstream.
- AC4: Cross-artifact atomicity source/output/lineage/eligibility qua **SQLite transaction** (resolved D2-B).

### L2 Security & Trust
- AC5: `SchemaTrustManifest` GWC-owned; verifier resolves profile through allowlist only.
- AC6: Legacy path verification-only, scoped by artifact family/version/cutover; never valid for new writes.
- AC7: Tuple-bound single-use anti-replay: `{artifact_semantic_domain, schema/contract version, canonical profile/version, hash_algorithm}` integrity-bound.
- AC8: Role separation publisher/collector/compiler/executor/verifier; downgrade prevention; quarantine-first legacy.
- AC9: Negative vectors: profile substitution, unknown/deprecated profile, duplicate-key smuggling, cross-artifact digest replay, legacy-downgrade.

### L3 Reliability & Operability
- AC10: `MigrationOperationJournal` states + typed transitions incl. `OUTCOME_UNKNOWN`, quarantine, recovery ownership.
- AC11: Durable commit: file+dir fsync or transactional store; mandatory lease/fencing; reload/readback before success.
- AC12: Deterministic idempotency + reconcile-before-retry; one retry owner; bounded budgets/backoff/jitter; poison quarantine.
- AC13: Fail-closed but isolated degraded modes (registry/key/archive outage); unrelated compatible replay continues.
- AC14: Resource/admission/backpressure controls; staged migration draining; reference-aware retention.
- AC15: Fault-injection AC at every journal boundary; quantitative SLOs/alerts (migration latency, queue age/depth, reconciliation success, quarantine age/count, stale-worker rejection, cross-version routing errors).

### L4 Governance & Implementability
- AC16: Consumer inventory — every digest call site classified `SEMANTIC_PROFILED | RAW_BYTES | OUT_OF_SCOPE`; audit of `digest_payload`/`record_digest`/`observation_digest` call sites in `tools/node_architect/`.
- AC17: Compatibility matrix per artifact kind (exact/backward-compatible/migration-required/unsupported) incl. old-writer/new-reader, new-writer/old-reader, removed/renamed/default-semantic changes, mixed generations, interrupted migration, downgrade.
- AC18: Exact requirement→surface→test→evidence map before G1/G2; migration DAG 3–7 work packages; staged rollout/rollback (write-cutover, never rewrite historical evidence).
- AC19: Conformance matrix ≥2 independent implementations/reference verifiers for every normative/adversarial fixture; exact-head CI via repo validator subprocess pattern; unavailable CI → `CI_UNAVAILABLE_AT_CHECK`.
- AC20: Human G2 boundary — schema/migration touches security boundary + broad blast radius → Human G2 direction per project-extension, NOT automatic; `UNKNOWN_SCHEMA_CANNOT_ENTER_REPLAY` + `CANONICALIZATION_NEVER_GRANTS_AUTHORITY` remain normative.

## D. DW observation sync (explicit)
- Replay/schema events must remain consumable by `dw-observation` fixtures: any new envelope field must either be optional in the observation projection OR be added to `observatory.ts` normalization with `UNKNOWN` default. Do not break `run`/`projection` pair topology.
- New `MigrationOperationJournal` terminal states must map to existing anomaly/UNKNOWN rendering in `observatory.ts` (no invention of authority/gate state).
- Any new schema must follow `schema_version` const + `*_digest` convention so `dw-observation` can read it source-backed.

## E. Open decisions (NEED Nhat) — RESOLVED 2026-08-24
1. Envelope scope: **chỉ checkpoint/evidence/observation** (tight), mở rộng sau G3. ✅ Nhat
2. Storage backend: **SQLite/transactional ngay** (atomic commit, tránh partial-write lọt gate). ✅ Nhat — D2-B
3. Cross-runtime matrix: **Go (JCS lib)** là implementation thứ 2 (tái dùng GWC runtime Go node); Rust để sau làm validation target. ✅ Nhat — D3-A
4. SLO numbers: write p99<50ms, queue-age<5min, drift-detect<1min, full-reconcile<15min.
5. Manifest issuer: **DWC connector ký** + CI verify offline bằng pinned key + trust panel hiển thị issuer & validity window.
6. Migration DAG: **5 packages** (envelope schema, checkpoint_store ext→SQLite, golden-vector py+go, manifest-isser glue, reconcile journal).

## F. REVISION v2 — APPROVED 2026-08-24
- 4-lane re-review v2: SCRUM-562 (L1) / 563 (L2) / 564 (L3) / 565 (L4) — ALL 🟢 APPROVE → Done
- Aggregate: `FOUR_LENS_REVIEW_COMPLETE / APPROVE` (comment 12079)
- HUMAN RESEARCH APPROVAL posted (Nhat approved) — research-level complete
- Implementation bridge: **ELIGIBLE** (pending Human G2 approval)
- KHÔNG cấp G2/G4 — implementation cần G2 Human approval scope riêng
