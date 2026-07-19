# Supabase Snapshot Exporter — Specification v1

## Task

**NTM-7**: Create Supabase snapshot exporter
**Phase**: Build
**Priority**: P0
**Risk**: High
**Workstream**: Migration

## Objective

Design and specify the Supabase snapshot exporter that reads canonical source rows from Supabase and produces deterministic, reconciliation-ready output files. The exporter must be repeatable, read-only, and produce output that the idempotent Notion importer (NTM-8) can consume.

## Output Format

Each export produces a JSON Lines (`.jsonl`) file per entity type, plus a batch manifest.

### Batch Manifest

```json
{
  "batch_id": "019f5515-c618-7790-b702-1ae6d73fd2b8",
  "source_system": "supabase",
  "exported_at": "2026-07-17T18:00:00.000Z",
  "source_sha": "8929784c01b7207080639886e4efec86f14249e4",
  "entities": [
    {
      "type": "agents",
      "file": "snapshot_019f5515_agents.jsonl",
      "row_count": 12,
      "sha256": "a1b2c3d4..."
    }
  ],
  "total_rows": 1234,
  "manifest_sha256": "e5f6a7b8..."
}
```

### Entity File (JSON Lines)

Each line is one source row with standardized envelope fields:

```json
{
  "_meta": {
    "source_table": "agentops_agents",
    "source_id": "agent_001",
    "exported_at": "2026-07-17T18:00:00.000Z",
    "batch_id": "019f5515-c618-7790-b702-1ae6d73fd2b8",
    "row_hash": "sha256-256:abc123..."
  },
  "id": "agent_001",
  "name": "DWC",
  "agent_type": "system",
  "enabled": true,
  "created_at": "2026-07-01T00:00:00.000Z",
  "updated_at": "2026-07-15T12:00:00.000Z"
}
```

The `_meta.row_hash` is computed as `SHA256(JSON.stringify(sorted_fields))` over all source fields excluding `_meta`.

## Source Queries

### 1. Agents (`agentops_agents`)

```sql
SELECT *
FROM public.agentops_agents
ORDER BY created_at ASC, id ASC;
```

### 2. Workflow Instances (`workflows`)

```sql
SELECT *
FROM public.workflows
ORDER BY created_at ASC, id ASC;
```

### 3. Tasks (`agentops_tasks`)

```sql
SELECT *
FROM public.agentops_tasks
ORDER BY created_at ASC, id ASC;
```

### 4. Runtime Tasks (`tasks`)

```sql
SELECT *
FROM public.tasks
ORDER BY created_at ASC, id ASC;
```

### 5. Task Events (`agentops_task_events`)

```sql
SELECT *
FROM public.agentops_task_events
ORDER BY created_at ASC, id ASC;
```

### 6. Runtime Task Events (`task_events`)

```sql
SELECT *
FROM public.task_events
ORDER BY created_at ASC, id ASC;
```

### 7. Agent Runs (`agentops_agent_runs`)

```sql
SELECT *
FROM public.agentops_agent_runs
ORDER BY created_at ASC, id ASC;
```

### 8. Approvals (`agentops_approvals`)

```sql
SELECT *
FROM public.agentops_approvals
ORDER BY created_at ASC, id ASC;
```

### 9. Task Links (`agentops_task_links`)

```sql
SELECT *
FROM public.agentops_task_links
ORDER BY created_at ASC, id ASC;
```

### 10. Audit Logs (`agentops_audit_logs`)

```sql
SELECT *
FROM public.agentops_audit_logs
ORDER BY timestamp ASC, id ASC;
```

### 11. Task Leases (`task_leases`)

```sql
SELECT *
FROM public.task_leases
ORDER BY leased_at ASC, id ASC;
```

## Export Algorithm

```
1. CONNECT to Supabase with read-only credentials
2. GENERATE batch_id = uuid_v7()
3. FOR EACH entity_type in dependency order:
   a. EXECUTE the corresponding SQL query
   b. FOR EACH row:
      - COMPUTE row_hash = SHA256(canonical_json(row))
      - WRITE JSON line with _meta envelope
   c. COMPUTE file_sha256 = SHA256(entire .jsonl file)
   d. RECORD in manifest
4. COMPUTE manifest_sha256 = SHA256(manifest JSON)
5. WRITE manifest file
6. OUTPUT: { manifest, files: [entity_type.jsonl, ...] }
```

## Safety Constraints

### Read-Only Guarantees

```yaml
safety:
  - connection: read-only transaction
  - statement: SELECT only
  - mutation: FORBIDDEN (INSERT/UPDATE/DELETE blocked at connection level)
  - side_effects: NONE
  - idempotent: YES (same source snapshot → same output)
```

### Row Hash Computation

```typescript
function computeRowHash(row: Record<string, any>): string {
  // 1. Remove _meta field
  // 2. Sort keys alphabetically
  // 3. Serialize to canonical JSON (no whitespace, sorted keys)
  // 4. Compute SHA-256
  const canonical = JSON.stringify(row, Object.keys(row).sort());
  return "sha256-256:" + crypto.createHash("sha256").update(canonical).digest("hex");
}
```

### Determinism Requirements

```yaml
determinism:
  - ORDER BY: (created_at ASC, id ASC) for all queries
  - TIMESTAMP: ISO-8601 UTC in all output
  - NULL handling: omit null fields from JSON output
  - FLOAT precision: fixed 6 decimal places where applicable
  - UUID format: lowercase with dashes
```

## Output Directory Structure

```
snapshots/
├── 2026-07-17/
│   ├── 019f5515-c618-7790-b702-1ae6d73fd2b8/
│   │   ├── manifest.json
│   │   ├── agents.jsonl
│   │   ├── workflows.jsonl
│   │   ├── agentops_tasks.jsonl
│   │   ├── tasks.jsonl
│   │   ├── agentops_task_events.jsonl
│   │   ├── task_events.jsonl
│   │   ├── agentops_agent_runs.jsonl
│   │   ├── agentops_approvals.jsonl
│   │   ├── agentops_task_links.jsonl
│   │   ├── agentops_audit_logs.jsonl
│   │   └── task_leases.jsonl
│   └── latest -> 019f5515-c618-7790-b702-1ae6d73fd2b8/
└── latest -> 2026-07-17/
```

## Reconciliation Support

The exporter output is designed to be consumed by the migration reconciliation doctor (NTM-9):

```yaml
reconciliation_fields:
  row_count: "manifest.entities[type].row_count"
  row_hash: "_meta.row_hash per line"
  file_hash: "manifest.entities[type].sha256"
  manifest_hash: "manifest.manifest_sha256"
```

The doctor can compare:
- Source row count vs Notion page count per entity type
- Source row hash vs Notion page hash (stored in Payload Hash)
- Source timestamps vs Notion timestamps

## Error Handling

```yaml
errors:
  connection_failure:
    action: retry (max 3, exponential backoff 1s/2s/4s)
    log: "Connection failed: {error}"
  query_failure:
    action: fail batch for that entity type
    log: "Query failed for {entity_type}: {error}"
    partial_output: preserve previously exported entities
  row_serialization_failure:
    action: skip row, log warning
    log: "Row serialization failed for {entity_type} id={id}: {error}"
  file_write_failure:
    action: fail batch
    log: "File write failed for {entity_type}: {error}"
```

## Acceptance Criteria Verification

1. **Exporter is repeatable** — running twice against the same source snapshot produces identical output (verified by SHA-256 comparison)
2. **Exporter is read-only** — no INSERT/UPDATE/DELETE statements executed (verified by connection configuration)
3. **Exporter is deterministic** — same ORDER BY, same timestamp format, same null handling (verified by output inspection)
4. **Output is reconciliation-ready** — manifest contains row counts and file hashes; each row has `_meta.row_hash` (verified by manifest structure)
5. **Batch isolation** — each export creates a new batch directory with unique batch ID (verified by directory listing)

## Dependencies

- **NTM-1**: Inventory and de-duplicate Supabase task models ✅ Done
- **NTM-3**: Design canonical Notion workflow schema ✅ Done
- **NTM-8**: Create idempotent Notion importer ✅ Done (this exporter feeds the importer)

## Rescue Scope

This specification is a design deliverable only. No Supabase connection, data export, or repository change is performed in this session.