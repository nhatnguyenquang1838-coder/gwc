# SCRUM-269 Rev3 Architecture Specification

**Status**: RESEARCH_CONTINUE (4/4 NEEDS_CLARIFICATION → RESEARCH_CONTINUE)
**Snapshot**: 773baa601492dabf6ad8e835b62e48a68b0c1b55
**Protected Base**: origin/main = 6d46fe701ac2cfe3653099f42d48ae27990d7bde
**Schema Version**: 2.0
**Dual-Read Constraint**: v1 records MUST remain valid under v2 schema (NON-REWRITING)

---

## L1: Core Infrastructure Specifications

### L1.1 State Machines

#### Ledger State Machine
```
States: [INIT, WRITING, FSYNC_PENDING, COMMITTED, QUARANTINED, ROLLED_BACK]
Transitions:
  INIT → WRITING                    : record() invoked
  WRITING → FSYNC_PENDING           : bytes written, fsync() issued
  FSYNC_PENDING → COMMITTED         : fsync() returns success
  FSYNC_PENDING → QUARANTINED       : fsync() fails / I/O error / digest mismatch
  COMMITTED → ROLLED_BACK           : rollback triggered (new anchor)
  QUARANTINED → ROLLED_BACK         : manual recovery / compaction
```

#### Node Execution State Machine (from node_evidence_ledger.py RECORD_SEQUENCE)
```
Sequence: node-start(1) → node-decision(2) → node-result(3) → node-readback(4) → checkpoint(5) → next-route-decision(6)
State enum: PENDING → RECORDING → VALIDATED → COMMITTED → READBACK_VERIFIED → CHECKPOINTED → ROUTED
```

### L1.2 Recovery-Ordering Tables

| Failure Mode | Detection Point | Recovery Action | Ordering Constraint |
|-------------|----------------|-----------------|---------------------|
| Kill -9 (SIGKILL) | Missing `event_digest` in runtime-events.jsonl | Replay from last COMMITTED sequence | Strict: sequence must be monotonic |
| Bitflip (silent corruption) | `state_digest` mismatch on readback | Quarantine record, replay from prior COMMITTED | Isolate: single record quarantine |
| Clock Skew | `occurred_at` non-monotonic vs wall clock | Reject if drift > 5s; accept with warning ≤5s | Wall-clock monotonicity within tolerance |
| Network Partition | Missing witness signatures | Hold in QUARANTINED until T/N witnesses respond | Quorum: witness_threshold (default 3) |

### L1.3 FS-Assumption Contracts

| Assumption | Guarantee | Violation Handling |
|-----------|-----------|-------------------|
| `write()` + `fsync()` = durability | Data survives power loss after fsync returns | On fsync failure → QUARANTINED, alert |
| `rename()` atomicity | No partial file states visible | Use `.tmp` → `rename()` pattern for all writes |
| Directory fsync | Parent directory entries durable | `fsync(dir_fd)` after new file creation |
| Append-only JSONL | No in-place mutation of events | `O_APPEND` flag; reject seeks on event log |

### L1.4 Digest-Profile Definitions

| Profile | Algorithm | Input Canonicalization | Output Format |
|---------|-----------|------------------------|---------------|
| `state_digest` | SHA-256 | `canonical_json(payload)` | `sha256:<64 hex>` |
| `decision_digest` | SHA-256 | `canonical_json({artifact_type, payload})` | `sha256:<64 hex>` |
| `record_digest` | SHA-256 | `canonical_json(full_record)` | `sha256:<64 hex>` |
| `event_digest` | SHA-256 | `canonical_json(event)` | `sha256:<64 hex>` |
| `digest_chain.prev_hash` | SHA-256 | `canonical_json(prev_event_bytes)` | `sha256:<64 hex>` |
| `root_merkle` | SHA-256 (Merkle) | Leaf = `record_digest` per sequence | `sha256:<64 hex>` |

### L1.5 Adversarial Test Thresholds (10 Golden Vectors)

| Vector ID | Scenario | Expected Result | Threshold |
|-----------|----------|-----------------|-----------|
| GV-01 | Kill-9 at sequence 3 (node-result) | Replay from sequence 2 COMMITTED | 100% replay fidelity |
| GV-02 | Single bitflip in `payload` at rest | Detect on readback, quarantine | 100% detection rate |
| GV-03 | Clock skew +5s (forward) | Accept with warning | ≤5s drift tolerated |
| GV-04 | Clock skew -10s (backward) | Reject, QUARANTINED | >5s backward = FAIL |
| GV-05 | Partition: 2/3 witnesses timeout | Hold QUARANTINED, retry with backoff | T=3, N=3 default |
| GV-06 | Corrupted `prev_hash` in chain | Detect at sequence boundary | Chain break = FAIL |
| GV-07 | Duplicate `idempotency_key` diff payload | `EvidenceConflict` raised | 100% conflict detection |
| GV-08 | Missing `fsync` (power loss sim) | Record in QUARANTINED | Durability guarantee |
| GV-09 | Root key rotation mid-run | Trust window overlap validates both | 30-day overlap |
| GV-10 | Schema v1 record in v2 validator | PASS (dual-read compat) | Zero v1 regressions |

---

## L2: Cryptographic & Authorization Specifications

### L2.1 DSSE Schema + Predicates

```json
{
  "payloadType": "application/vnd.gwc.node-evidence.v2+json",
  "payload": "<base64(canonical_json(record))>",
  "signatures": [
    {
      "keyid": "gwc-root-1",
      "sig": "<base64(ed25519_sign(private_key, payload))>"
    }
  ],
  "predicates": [
    {
      "type": "https://gwc.local/predicates/sequence-monotonic",
      "predicate": {"expected_sequence": 3, "actual_sequence": 3}
    },
    {
      "type": "https://gwc.local/predicates/idempotency-unique",
      "predicate": {"idempotency_key": "task-123-run-456-node-789"}
    },
    {
      "type": "https://gwc.local/predicates/digest-chain-valid",
      "predicate": {"prev_hash": "sha256:...", "chain_id": "gwc-main", "sequence": 3}
    }
  ]
}
```

### L2.2 Authorization Mapping

| Artifact Type | Required Key Role | Witness Threshold |
|--------------|-------------------|-------------------|
| `node-start` | `node_executor` | 0 (self-signed) |
| `node-decision` | `node_executor` + `gate_authority` | 1 |
| `node-result` | `node_executor` | 0 |
| `node-readback` | `validator` | 1 |
| `checkpoint` | `checkpoint_authority` | 2 |
| `next-route-decision` | `gate_authority` | 2 |

### L2.3 Rollback Semantics (New Anchor)

```python
def rollback_to_anchor(ledger: NodeEvidenceLedger, anchor_sequence: int, reason: str) -> RollbackRecord:
    """
    Creates a new anchor record that invalidates all sequences > anchor_sequence.
    Does NOT mutate existing records (append-only invariant).
    """
    rollback_record = {
        "schema_version": "2.0",
        "artifact_type": "rollback-anchor",
        "anchor_sequence": anchor_sequence,
        "reason": reason,
        "invalidated_sequences": list(range(anchor_sequence + 1, current_max_sequence + 1)),
        "rolled_back_at": utc_now(),
        "rollback_digest": digest_payload({"anchor_sequence": anchor_sequence, "reason": reason}),
        "digest_chain": {
            "prev_hash": get_event_digest_at_sequence(anchor_sequence),
            "chain_id": "gwc-main",
            "sequence": anchor_sequence + 1  # rollback is next sequence
        }
    }
    # Signed by root key, witnessed by quorum
    return sign_and_witness(rollback_record, threshold=WITNESS_THRESHOLD)
```

### L2.4 Root Rotation Procedure

1. **Pre-rotation**: New root key (`gwc-root-2`) added to `ledger_trusted_bootstrap.json` with `status: "pending"`, `valid_from` = now + 30 days overlap
2. **Overlap Period** (30 days): Both `gwc-root-1` (active) and `gwc-root-2` (pending) accepted for verification
3. **Cutover**: At `valid_from` of `gwc-root-2`, status → `active`; `gwc-root-1` → `retired`
4. **Post-rotation**: `gwc-root-1` remains valid for verifying historical records until `valid_until`

### L2.5 Key Rotation (key_id + Trust Window)

```json
{
  "key_id": "gwc-root-1",
  "public_key": "-----BEGIN PUBLIC KEY-----\n...",
  "valid_from": "2026-08-01T00:00:00Z",
  "valid_until": "2027-08-01T00:00:00Z",
  "status": "active"
}
```

**Trust Window Rules**:
- Overlap: `trust_window_overlap_days` = 30 (configurable)
- Verification accepts any key where `valid_from ≤ record.occurred_at ≤ valid_until`
- Key lookup by `key_id` in signature → bootstrap config
- Expired keys rejected for NEW records; accepted for HISTORICAL verification

### L2.6 Witness Threshold T/N

- Default: `witness_threshold` = 3, `witness_set` = 3 (T=3, N=3 = unanimous)
- Configurable via `ledger_trusted_bootstrap.json`
- Witness signatures collected async; record moves COMMITTED only after threshold met
- Witness set rotation follows same trust-window procedure as root keys

---

## L3: Runtime & Operational Specifications

### L3.1 State Enum (Complete)

```python
class LedgerState(Enum):
    INIT = "init"
    WRITING = "writing"
    FSYNC_PENDING = "fsync_pending"
    COMMITTED = "committed"
    QUARANTINED = "quarantined"
    ROLLED_BACK = "rolled_back"

class RecordState(Enum):
    PENDING = "pending"
    RECORDED = "recorded"
    VALIDATED = "validated"
    COMMITTED = "committed"
    READBACK_VERIFIED = "readback_verified"
    CHECKPOINTED = "checkpointed"
    ROUTED = "routed"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"  # by rollback-anchor
```

### L3.2 Fsync Ordering (Write → Fsync → Ack)

```python
def durable_write(path: Path, content: bytes) -> None:
    # 1. Write to temp file
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_bytes(content)
    
    # 2. fsync file
    with tmp_path.open("r") as f:
        os.fsync(f.fileno())
    
    # 3. fsync parent directory (ensures directory entry durable)
    dir_fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    
    # 4. Atomic rename
    tmp_path.rename(path)
    
    # 5. Ack: return only after all above succeed
```

### L3.3 Quarantine Path

```
.gwc/tasks/{task_id}/node-runtime/{run_id}/
├── {node_id}/
│   ├── node-start.json
│   ├── node-decision.json
│   ├── node-result.json
│   ├── node-readback.json
│   ├── checkpoint.json
│   └── next-route-decision.json
├── runtime-events.jsonl          # append-only event log
└── quarantine/
    ├── {sequence}-{event_digest[:8]}.jsonl   # isolated corrupted records
    └── quarantine-index.json                 # metadata: reason, detected_at, recovery_action
```

### L3.4 Lease TTL

| Lease Type | TTL | Renewal | Expiry Action |
|-----------|-----|---------|---------------|
| Node execution lease | 30 min | Every 10 min (heartbeat) | QUARANTINE node, mark RUNNING→STALLED |
| Checkpoint lease | 24 hr | On each checkpoint write | EVICT checkpoint, require re-execution |
| Witness signature lease | 5 min | N/A (one-shot) | Retry with next witness |
| Root key validity | 365 days | Rotation procedure | Key expires, rotation mandatory |

### L3.5 SLO Numbers

| Metric | Target | Measurement |
|--------|--------|-------------|
| Record write latency (p99) | < 50 ms | `record()` call → COMMITTED |
| Readback verification (p99) | < 100 ms | `readback()` call → VALIDATED |
| Chain replay (1000 records) | < 2 s | Full `ledger_replay_verifier.py` run |
| Witness collection (T=3) | < 5 s | Async parallel collection |
| Quarantine recovery | < 30 s | Manual + automated |

### L3.6 Retention T

| Artifact | Retention Period | Disposition |
|----------|------------------|-------------|
| Runtime events (jsonl) | 90 days | Compress → cold storage |
| Node evidence (json) | 365 days | Archive |
| Rollback anchors | Permanent | Immutable |
| Root key bootstrap | Permanent | Immutable |
| Quarantine records | 30 days | Auto-purge if resolved |

### L3.7 10 Golden Test Vectors (Pinned)

See L1.5 table. Each vector has:
- Fixed input fixture (ledger file + bootstrap config)
- Expected output: PASS/FAIL + reason code per boundary
- Deterministic: same input → same output (no timestamps, no randomness)

---

## Cross-Lens Constraints

### Dual-Read v1/v2 NON-REWRITING Constraint

| Requirement | Implementation |
|-------------|----------------|
| v1 records validate under v2 schema | `additionalProperties: false` but v1 fields all present in v2 |
| No migration/rewrite of existing v1 files | v2 validator accepts `schema_version: "1.0"` |
| New v2 fields optional for v1 records | `digest_chain` field: required for v2, optional for v1 |
| `schema_version` const updated to `"2.0"` for new records | v1 records keep `"1.0"`; validator handles both |

### Schema Version "2.0"

- All NEW records written with `"schema_version": "2.0"`
- v2 schema `$id`: `https://gwc.local/schemas/node-architect/node-runtime-evidence.schema.json`
- v2 schema includes `digest_chain` object (see L3.8)

### L3.8 digest_chain Field (v2 Addition)

```json
"digest_chain": {
  "type": "object",
  "required": ["prev_hash", "chain_id", "sequence"],
  "properties": {
    "prev_hash": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "chain_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9._-]*$"},
    "sequence": {"type": "integer", "minimum": 1}
  },
  "additionalProperties": false
}
```

**Semantics**:
- `prev_hash`: SHA-256 of previous event's canonical JSON bytes (genesis = `sha256:00...00`)
- `chain_id`: Logical chain identifier (e.g., `gwc-main`, `gwc-preprod-{run_id}`)
- `sequence`: Monotonic sequence number within chain (matches `sequence` field)

**Backward Compatibility**:
- v1 records: `digest_chain` absent → validator computes implicitly from `event_digest` chain
- v2 records: `digest_chain` present → validator uses explicit values
- Both validate successfully under v2 schema

---

## File References (Grounding)

| Artifact | Source File | Purpose |
|----------|-------------|---------|
| v1 Ledger | `tools/node_architect/node_evidence_ledger.py` | Record sequence, digest logic, idempotency, event log |
| v1 Schema | `schemas/node-architect/node-runtime-evidence.schema.json` | v1 field definitions, required fields, constraints |
| v1 Event Schema | `schemas/node-architect/runtime-event.schema.json` | Event types, actor model, gate mapping |
| Evidence Ledger Schema | `schemas/node-architect/evidence-ledger.schema.json` | Node-level evidence envelope |

---

## Deliverable Checklist

- [x] L1: State machines, recovery-ordering, FS-assumptions, digest-profiles, adversarial thresholds
- [x] L2: DSSE schema + predicates, authz mapping, rollback semantics, root rotation, key rotation, witness T/N
- [x] L3: State enum, fsync ordering, quarantine path, lease TTL, SLO numbers, retention T, 10 golden vectors
- [x] Cross-lens: Dual-read v1/v2 non-rewriting, schema_version "2.0", digest_chain field