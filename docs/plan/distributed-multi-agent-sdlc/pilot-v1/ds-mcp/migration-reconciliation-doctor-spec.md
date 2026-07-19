# Migration Reconciliation Doctor — Specification v1

## Task

**NTM-9**: Build migration reconciliation doctor
**Phase**: Shadow
**Priority**: P0
**Risk**: High
**Workstream**: Validation

## Objective

Design and specify the migration reconciliation doctor that compares source Supabase data (exported by NTM-7) against Notion target data (imported by NTM-8) and produces PASS, BLOCKED, or CONFLICT with exact evidence. The doctor must never recommend cutover on unresolved P0 issues.

## Inputs

### Source Side (NTM-7 Snapshot)

```
snapshots/<date>/<batch_id>/
├── manifest.json              # row counts, file SHA-256 per entity
├── agents.jsonl               # _meta.row_hash per row
├── workflows.jsonl
├── agentops_tasks.jsonl
├── tasks.jsonl
├── agentops_task_events.jsonl
├── task_events.jsonl
├── agentops_agent_runs.jsonl
├── agentops_approvals.jsonl
├── agentops_task_links.jsonl
├── agentops_audit_logs.jsonl
└── task_leases.jsonl
```

### Target Side (NTM-8 Notion Databases)

Queried via Notion API:

```yaml
targets:
  - database: Agents
    query: "Source System == 'supabase'"
    fields: [Agent ID, Legacy Agent ID, Migration Status, Payload Hash]
  - database: Workflow Instances
    query: "Source System == 'supabase'"
    fields: [Workflow Instance ID, Legacy Workflow ID, Migration Status, Payload Hash]
  - database: Tasks
    query: "Source System == 'supabase'"
    fields: [Task ID, Legacy Supabase ID, State, State Version, Migration Status, Payload Hash]
  - database: Task Events
    query: "Source System == 'supabase'"
    fields: [Event ID, Legacy Event ID, Task, Event Type, Outcome, Migration Status, Payload Hash]
  - database: Task Runs
    query: "Source System == 'supabase'"
    fields: [Run ID, Legacy Run ID, Task, Agent, Run Status, Migration Status, Payload Hash]
  - database: Approvals
    query: "Source System == 'supabase'"
    fields: [Approval ID, Legacy Approval ID, Task, Decision, Migration Status, Payload Hash]
  - database: Task Links
    query: "Source System == 'supabase'"
    fields: [Link ID, Legacy Link ID, From Task, To Task, Link Type, Migration Status, Payload Hash]
  - database: Runtime Events Archive
    query: "Source System == 'supabase'"
    fields: [Runtime Event ID, Legacy Event ID, Task Run, Event Type, Migration Status, Payload Hash]
```

## Reconciliation Dimensions

### 1. Row Count

Compare source row count vs Notion page count per entity type.

```yaml
check: row_count
source: manifest.json → entities[type].row_count
target: Notion API → results.length
verdict:
  match: PASS
  mismatch: CONFLICT (report exact counts)
```

### 2. ID Coverage

Every legacy Supabase ID must exist in the corresponding Notion database.

```yaml
check: id_coverage
source: .jsonl → [row.id for each row]
target: Notion API → [page.properties["Legacy Supabase ID"] for each page]
verdict:
  all_found: PASS
  missing_ids: CONFLICT (list missing IDs)
  extra_ids: WARNING (list IDs in Notion but not in source)
```

### 3. Row Hash Integrity

Compare source row hash against Notion Payload Hash.

```yaml
check: row_hash
source: .jsonl → _meta.row_hash per row
target: Notion API → page.properties["Payload Hash"] per page
match_key: (source_system, legacy_supabase_id)
verdict:
  all_match: PASS
  mismatches: CONFLICT (list legacy_id, source_hash, target_hash)
  missing_hash: WARNING (page exists but no Payload Hash)
```

### 4. State Consistency

For Tasks, compare source state/status against Notion State.

```yaml
check: state_consistency
entity: Tasks
source: agentops_tasks.jsonl → row.state, tasks.jsonl → row.status
target: Notion API → page.properties["State"]
match_key: legacy_supabase_id
verdict:
  all_match: PASS
  mismatches: CONFLICT (list task_id, source_state, target_state)
```

### 5. Event Continuity

For Task Events, verify event sequence is preserved.

```yaml
check: event_continuity
entity: Task Events
source: agentops_task_events.jsonl → [row.id, row.event_type, row.created_at]
target: Notion API → [page.properties["Event ID"], page.properties["Event Type"], page.properties["Occurred At"]]
group_by: task_id
verdict:
  events_match: PASS
  missing_events: CONFLICT (list missing event IDs per task)
  extra_events: WARNING (list events in Notion not in source)
  order_mismatch: CONFLICT (list events with different sequence)
```

### 6. Unresolved Relation Check

Verify that all Notion relation fields point to existing pages.

```yaml
check: relation_integrity
target: Notion API → all relation fields across all databases
checks:
  - Task → Agent (resolved)
  - Task → Parent Task (resolved)
  - Task → Dependencies (resolved)
  - Task Event → Task (resolved)
  - Task Run → Task (resolved)
  - Task Run → Agent (resolved)
  - Task Run → Workflow Instance (resolved)
  - Approval → Task (resolved)
  - Task Link → From Task (resolved)
  - Task Link → To Task (resolved)
  - Runtime Event → Task Run (resolved)
verdict:
  all_resolved: PASS
  broken_relations: CONFLICT (list relation type, source page, missing target)
```

### 7. Migration Status Audit

Verify all imported pages have correct migration metadata.

```yaml
check: migration_status
target: Notion API → all pages with Source System == "supabase"
fields:
  - Migration Status == "imported"
  - Source System == "supabase"
  - Migration Batch ID is not null
verdict:
  all_correct: PASS
  anomalies: CONFLICT (list pages with unexpected migration status)
```

## Output Format

### Reconciliation Report

```json
{
  "report_id": "019f5515-c618-7790-b702-1ae6d73fd2b8",
  "batch_id": "019f5515-c618-7790-b702-1ae6d73fd2b8",
  "generated_at": "2026-07-17T18:00:00.000Z",
  "overall_verdict": "PASS | BLOCKED | CONFLICT",
  "dimensions": [
    {
      "name": "row_count",
      "verdict": "PASS",
      "details": {
        "agents": { "source": 12, "target": 12, "match": true },
        "workflows": { "source": 5, "target": 5, "match": true },
        "tasks": { "source": 150, "target": 148, "match": false }
      }
    },
    {
      "name": "id_coverage",
      "verdict": "CONFLICT",
      "details": {
        "missing_ids": {
          "tasks": ["task_151", "task_152"]
        },
        "extra_ids": {
          "tasks": []
        }
      }
    }
  ],
  "findings": [
    {
      "severity": "BLOCKER",
      "dimension": "id_coverage",
      "entity": "tasks",
      "message": "2 source tasks missing from Notion: task_151, task_152"
    },
    {
      "severity": "MAJOR",
      "dimension": "row_hash",
      "entity": "task_events",
      "message": "3 events have hash mismatch"
    }
  ],
  "cutover_recommendation": "DO_NOT_PROCEED",
  "manifest_sha256": "e5f6a7b8..."
}
```

### Verdict Rules

```yaml
overall_verdict:
  PASS:
    condition: All dimensions PASS, no BLOCKER findings
    cutover_recommendation: "PROCEED_WITH_CAUTION"
  BLOCKED:
    condition: One or more dimensions cannot be checked (API error, missing data)
    cutover_recommendation: "DO_NOT_PROCEED"
  CONFLICT:
    condition: One or more dimensions have mismatches
    cutover_recommendation:
      has_blocker: "DO_NOT_PROCEED"
      has_major_only: "INVESTIGATE_BEFORE_PROCEED"
      has_minor_only: "PROCEED_WITH_CAUTION"
```

### Finding Severity

```yaml
severity:
  BLOCKER:
    - Missing source data (cannot verify)
    - Notion API unreachable
    - Schema mismatch between source and target
    - Zero rows in source or target for critical entity
  MAJOR:
    - Row count mismatch > 1%
    - Missing IDs in target
    - Row hash mismatch
    - State inconsistency
    - Broken relations
  MINOR:
    - Row count mismatch <= 1%
    - Extra IDs in target (orphaned pages)
    - Missing Payload Hash on existing pages
    - Migration status anomalies
  INFO:
    - All checks passed
    - Performance metrics
    - Timing information
```

## Algorithm

```
1. LOAD source manifest.json
2. FOR EACH entity type:
   a. LOAD source .jsonl file
   b. QUERY Notion database for matching pages
   c. BUILD lookup map: legacy_id → Notion page
3. RUN dimension checks in order:
   a. Row count
   b. ID coverage
   c. Row hash integrity
   d. State consistency
   e. Event continuity
   f. Relation integrity
   g. Migration status audit
4. AGGREGATE findings by severity
5. DETERMINE overall verdict
6. GENERATE cutover recommendation
7. OUTPUT reconciliation report
```

## Error Handling

```yaml
errors:
  source_manifest_not_found:
    action: fail with BLOCKED
    message: "Source manifest not found at {path}"
  source_jsonl_corrupt:
    action: skip entity type, record BLOCKER
    message: "Source file {file} is corrupt: {error}"
  notion_api_error:
    action: retry (max 3, exponential backoff)
    message: "Notion API error for {database}: {error}"
    verdict: BLOCKED if all retries exhausted
  notion_query_timeout:
    action: retry with smaller page_size
    message: "Query timeout for {database}, retrying with page_size=50"
  partial_data:
    action: report what was checked, mark unchecked as BLOCKER
    message: "Partial data: {checked}/{total} entities verified"
```

## Acceptance Criteria Verification

1. **Doctor produces PASS, BLOCKED or CONFLICT with exact evidence** — verified by report output format
2. **No cutover recommendation on unresolved P0 issues** — verified by `cutover_recommendation: DO_NOT_PROCEED` when BLOCKER or unresolved MAJOR exists
3. **All 7 reconciliation dimensions are checked** — verified by dimension list
4. **Findings are classified by severity** — verified by BLOCKER/MAJOR/MINOR/INFO taxonomy
5. **Source and target evidence is captured** — verified by `details` field in each dimension result

## Dependencies

- **NTM-7**: Create Supabase snapshot exporter ✅ Done (provides source input)
- **NTM-8**: Create idempotent Notion importer ✅ Done (provides target input)
- **NTM-14**: Define reconciliation SLO and mismatch taxonomy (future — this spec defines the initial taxonomy)

## Rescue Scope

This specification is a design deliverable only. No reconciliation execution, Notion query, or repository change is performed in this session.