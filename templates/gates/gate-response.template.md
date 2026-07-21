# Gate Response

## Status

```text
<GATE>: <STATUS> — <evidence or blocker>
```

## Gate Response Trace

The following labels are mandatory and must be emitted exactly as shown. UTC timestamps use ISO 8601 with a trailing `Z`.

| Field | Value |
|---|---|
| Skills called | `<non-empty, unique skill/tool identifiers>` |
| Started at UTC | `<YYYY-MM-DDTHH:MM:SSZ>` |
| Ended at UTC | `<YYYY-MM-DDTHH:MM:SSZ>` |

Machine-readable equivalent:

```yaml
schema_version: "1.0"
artifact_type: gate-response-trace
gate: G2_EXECUTION
Skills called:
  - DWC GitHub
Started at UTC: "2026-07-21T02:00:00Z"
Ended at UTC: "2026-07-21T02:10:00Z"
```

Validation rules:

- `Skills called` is non-empty, contains unique non-blank values, and records only skills or tools actually used.
- `Started at UTC` and `Ended at UTC` are valid UTC timestamps ending in `Z`.
- `Ended at UTC` is equal to or later than `Started at UTC`.
