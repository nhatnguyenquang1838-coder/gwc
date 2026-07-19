# Idempotent Notion Importer — Specification v1

## Task

**NTM-8**: Create idempotent Notion importer
**Phase**: Build
**Priority**: P0
**Risk**: High
**Workstream**: Migration

## Objective

Design and specify the idempotent Notion importer that reads canonical Supabase source rows and creates corresponding Notion database pages in dependency order, preserving legacy IDs, source hashes, and relation references. Re-running the same batch must not duplicate pages; unresolved relations must be quarantined and reported.

## Source Tables (Supabase)

| Source Table | Target Notion Database | Key Fields |
|---|---|---|
| `agentops_agents` | Agents | `id`, `name`, `agent_type`, `enabled` |
| `workflows` | Workflow Instances | `id`, `workflow_type`, `name`, `status` |
| `agentops_tasks` | Tasks | `id`, `title`, `task_type`, `state`, `priority` |
| `tasks` | Tasks (runtime) | `id`, `workflow_id`, `type`, `status` |
| `agentops_task_events` | Task Events | `id`, `task_id`, `event_type`, `from_state`, `to_state` |
| `task_events` | Task Events (runtime) | `id`, `workflow_id`, `task_id`, `event_type` |
| `agentops_agent_runs` | Task Runs | `id`, `task_id`, `agent_id`, `status` |
| `agentops_approvals` | Approvals | `id`, `task_id`, `approval_type`, `status` |
| `agentops_task_links` | Task Links | `id`, `from_task_id`, `to_task_id`, `link_type` |
| `agentops_audit_logs` | Runtime Events Archive | `id`, `action`, `source`, `task_id` |
| `task_leases` | (embedded in Tasks) | `task_id`, `agent_id`, `lease_token`, `status` |

## Import Dependency Order

```
1. Agents              (no dependencies)
2. Workflow Instances  (no dependencies)
3. Tasks               (depends on Agents, Workflow Instances)
4. Task Events         (depends on Tasks)
5. Task Runs           (depends on Tasks, Agents)
6. Approvals           (depends on Tasks)
7. Task Links          (depends on Tasks)
8. Runtime Events Archive (depends on Task Runs)
```

## Idempotency Strategy

### Uniqueness Constraints

Each target Notion database enforces:

```yaml
unique_constraints:
  - field: task_id
    scope: per-database
  - field: (source_system, legacy_supabase_id)
    scope: per-database
  - field: command_id
    scope: Task Events only
```

### Import Algorithm (per entity type)

```
1. QUERY: SELECT * FROM source_table ORDER BY created_at ASC
2. FOR EACH row:
   a. COMPUTE: legacy_id_hash = SHA256(source_system + ":" + row.id)
   b. CHECK: Notion database for page where
      "Source System" == source_system AND
      "Legacy Supabase ID" == row.id
   c. IF found → SKIP (idempotent — already imported)
   d. IF not found → CREATE Notion page with:
      - All mapped fields from source row
      - "Source System" = "supabase"
      - "Legacy Supabase ID" = row.id
      - "Migration Status" = "imported"
      - "Migration Batch ID" = current_batch_id
   e. RECORD: mapping { legacy_id → notion_page_id } for relation resolution
3. REPORT: { total, created, skipped, errors }
```

### Relation Resolution

When a source row references another entity (e.g., `task_id` in Task Events):

```
1. LOOKUP: mapping[source_system + ":" + referenced_legacy_id]
2. IF found → use the resolved Notion page ID as the relation value
3. IF not found → set relation to null, add to quarantine report
```

### Batch Execution

```yaml
batch:
  id: uuid_v7
  source_system: "supabase"
  started_at: ISO-8601
  entities: [entity_type, ...]
  idempotency_key: batch_id + entity_type
```

## Notion API Mapping

### Agents → Agents Database

| Source Field | Notion Property | Type |
|---|---|---|
| `id` | Agent ID | title (text) |
| `name` | Name | rich_text |
| `agent_type` | Status | select |
| `enabled` | Capabilities | rich_text |
| — | Runtime Provider | select (default: "supabase") |
| — | Last Seen Snapshot | date (from updated_at) |
| — | Legacy Agent ID | rich_text |
| — | Migration Status | select ("imported") |

### workflows → Workflow Instances Database

| Source Field | Notion Property | Type |
|---|---|---|
| `id` | Workflow Instance ID | title (text) |
| `workflow_type` | Workflow Definition ID | rich_text |
| — | Workflow Version | number (1) |
| `status` | State | select |
| — | State Version | number (1) |
| — | Root Task | relation (resolved) |
| `created_at` | Started At | date |
| `updated_at` | Completed At | date |
| — | Last Event ID | rich_text |
| — | Legacy Workflow ID | rich_text |
| — | Migration Status | select ("imported") |

### agentops_tasks + tasks → Tasks Database

| Source Field | Notion Property | Type |
|---|---|---|
| `id` | Task ID | title (text) |
| `title` | Title | rich_text |
| `state` / `status` | State | select |
| — | State Version | number (1) |
| — | Machine ID | rich_text |
| — | Machine Version | number (1) |
| `priority` | Priority | select |
| `risk` (if present) | Risk | select |
| `assigned_agent_id` | Owner | relation (resolved) |
| `assigned_agent_id` | Assigned Agent | relation (resolved) |
| `parent_task_id` | Parent Task | relation (resolved) |
| — | Dependencies | relation (resolved from Task Links) |
| `repo_owner` / `repo_name` | Repository | rich_text |
| `repo_branch` | Branch | rich_text |
| `pr_url` | PR URL | url |
| — | Blocker | rich_text |
| — | Blocked At | date |
| — | Requested Event | rich_text |
| — | Request ID | rich_text |
| — | Claim Token | rich_text |
| — | Claim Owner | rich_text |
| — | Lease Until | date |
| — | Lease Version | number (0) |
| — | Last Event ID | rich_text |
| — | Legacy Supabase ID | rich_text |
| — | Source System | select ("supabase") |
| — | Migration Status | select ("imported") |
| `created_at` | Created At | date |
| `updated_at` | Updated At | date |
| `completed_at` | Completed At | date |

### agentops_task_events + task_events → Task Events Database

| Source Field | Notion Property | Type |
|---|---|---|
| `id` | Event ID | title (text) |
| `idempotency_key` | Command ID | rich_text (unique) |
| `task_id` | Task | relation (resolved) |
| `event_type` | Event Type | select |
| `from_state` | From State | select |
| `to_state` | To State | select |
| — | Expected Version | number |
| — | Result Version | number |
| `actor` | Actor Type | select |
| `actor_id` | Actor ID | rich_text |
| — | Outcome | select ("Applied") |
| — | Payload Hash | rich_text |
| `created_at` | Occurred At | date |
| — | Legacy Event ID | rich_text |
| — | Source System | select ("supabase") |

### agentops_agent_runs → Task Runs Database

| Source Field | Notion Property | Type |
|---|---|---|
| `id` | Run ID | title (text) |
| `task_id` | Task | relation (resolved) |
| — | Workflow Instance | relation (resolved via task) |
| `agent_id` | Agent | relation (resolved) |
| `status` | Run Status | select |
| — | Attempt | number (1) |
| `created_at` | Started At | date |
| `completed_at` | Finished At | date |
| — | Input Hash | rich_text |
| — | Output Reference | rich_text |
| `error` | Error Summary | rich_text |
| — | Legacy Run ID | rich_text |
| — | Migration Status | select ("imported") |

### agentops_approvals → Approvals Database

| Source Field | Notion Property | Type |
|---|---|---|
| `id` | Approval ID | title (text) |
| `task_id` | Task | relation (resolved) |
| — | Gate | select |
| — | Scope Hash | rich_text |
| `requested_by` | Requested By | rich_text |
| `created_at` | Requested At | date |
| `status` | Decision | select |
| `approved_by` | Decided By | rich_text |
| `decided_at` | Decided At | date |
| — | Expires At | date |
| — | Evidence URL | url |
| — | Legacy Approval ID | rich_text |

### agentops_task_links → Task Links Database

| Source Field | Notion Property | Type |
|---|---|---|
| `id` | Link ID | title (text) |
| `from_task_id` | From Task | relation (resolved) |
| `to_task_id` | To Task | relation (resolved) |
| `link_type` | Link Type | select |
| — | Order | number (0) |
| — | Is Blocking | checkbox |
| — | Legacy Link ID | rich_text |
| — | Migration Status | select ("imported") |

### agentops_audit_logs → Runtime Events Archive

| Source Field | Notion Property | Type |
|---|---|---|
| `id` | Runtime Event ID | title (text) |
| — | Task Run | relation (resolved via run_id) |
| `action` | Event Type | select |
| — | Payload Hash | rich_text |
| `timestamp` | Occurred At | date |
| — | Sequence | number |
| — | Legacy Event ID | rich_text |

## Error Handling

### Conflict Resolution

```yaml
conflict_types:
  duplicate_legacy_id:
    action: skip
    log: "Page already exists for legacy_id={id}"
  unresolved_relation:
    action: create_with_null_relation
    log: "Unresolved relation: {field}={referenced_id}"
    quarantine: true
  api_error:
    action: retry (max 3, exponential backoff)
    log: "API error: {status} {message}"
    quarantine: true
  schema_mismatch:
    action: fail_batch
    log: "Schema mismatch: {detail}"
```

### Quarantine Report

After each batch, produce:

```yaml
quarantine:
  batch_id: uuid
  unresolved_relations:
    - entity_type: Task Events
      legacy_id: "evt_001"
      field: task_id
      referenced_id: "task_999"
      reason: "Referenced task not found in source or mapping"
  api_errors:
    - entity_type: Tasks
      legacy_id: "task_042"
      attempt: 2
      error: "Notion API rate limit"
      action: "quarantined after 3 retries"
```

## Acceptance Criteria Verification

1. **Re-running the same batch does not duplicate pages** — verified by checking `(source_system, legacy_supabase_id)` uniqueness constraint
2. **Unresolved relations are quarantined and reported** — verified by quarantine report output
3. **Import is dependency-ordered** — verified by execution sequence
4. **Legacy IDs are preserved** — verified by `Legacy Supabase ID` field in every Notion page
5. **Source hashes are preserved** — verified by `Payload Hash` field where applicable
6. **Relation references are resolved** — verified by relation lookup mapping

## Dependencies

- **NTM-1**: Inventory and de-duplicate Supabase task models ✅ Done
- **NTM-3**: Design canonical Notion workflow schema ✅ Done
- **NTM-7**: Create Supabase snapshot exporter (must exist before importer runs)

## Rescue Scope

This specification is a design deliverable only. No data import, Supabase read, or repository change is performed in this session.