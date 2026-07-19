# Connector Trace Contract v1.0

## Status

- Document ID: `connector-trace-contract`
- Version: `1.0`
- Lifecycle: `active`
- Scope: connector operations that call external providers

## Purpose

Provide observable evidence showing where a connector operation succeeded or failed without exposing credentials, tokens, authorization headers, or sensitive payload values.

## Boundary model

```text
platform schema/runtime
→ connector transport
→ DW1 input validation
→ DW1 policy
→ provider adapter
→ GitHub API
→ response serialization
```

DW1 can attest only to stages reached after the DW1 backend receives the call. When no DW1 response exists, the caller must classify the failure as platform or connector transport evidence, not as a DW1 or GitHub rejection.

## Additive response envelope

Existing operation data remains compatible. Implementations should add:

```yaml
ok: true|false
trace:
  trace_id: 32 lowercase hexadecimal characters
  operation: github_create_branch
  failure_stage: null|platform_schema_validation|platform_runtime|connector_transport|dw1_input_validation|dw1_policy|github_api|response_serialization|unknown
  connector_received: true|false
  policy_checked: true|false
  upstream_attempted: true|false
  upstream_provider: github|null
  provider_request_id: string|null
  github_request_id: string|null
  http_status: integer|null
  started_at: ISO-8601 UTC
  completed_at: ISO-8601 UTC
  duration_ms: non-negative integer
error:
  code: stable machine-readable code
  message: sanitized human-readable message
  retryable: true|false
  details: object|null
data: object|null
```

## Required invariants

1. `ok: true` requires `failure_stage: null` and `error: null`.
2. A DW1 policy rejection requires `failure_stage: dw1_policy`, `policy_checked: true`, and `upstream_attempted: false`.
3. A GitHub rejection requires `failure_stage: github_api`, `upstream_attempted: true`, and records HTTP status plus `X-GitHub-Request-Id` when GitHub supplies them.
4. A provider call that succeeds records `upstream_attempted: true` and the provider request identifier when available.
5. Error codes are stable; error messages may evolve but must remain sanitized.
6. Trace identifiers may propagate using W3C Trace Context. If no valid parent context exists, DW1 generates a trace identifier.
7. Raw authorization headers, access tokens, cookies, credentials, secrets, private connection strings, and full sensitive payloads must never appear in trace fields or error details.
8. Response serialization failure is recorded only when the backend can still emit a safe fallback envelope; otherwise runtime logs retain the trace ID.

## Failure-stage ownership

| Stage | Owning boundary | Provider reached |
|---|---|---|
| `platform_schema_validation` | Chat/tool schema layer | No |
| `platform_runtime` | Chat/platform runtime | No |
| `connector_transport` | Connector transport | No or unknown |
| `dw1_input_validation` | DW1 request validator | No |
| `dw1_policy` | DW1 policy guard | No |
| `github_api` | GitHub API/adapter | Yes |
| `response_serialization` | DW1 response encoder | Possibly |
| `unknown` | Unclassified; requires investigation | Unknown |

## Example: DW1 policy rejection

```json
{
  "ok": false,
  "trace": {
    "trace_id": "0123456789abcdef0123456789abcdef",
    "operation": "github_create_branch",
    "failure_stage": "dw1_policy",
    "connector_received": true,
    "policy_checked": true,
    "upstream_attempted": false,
    "upstream_provider": null,
    "provider_request_id": null,
    "github_request_id": null,
    "http_status": null,
    "started_at": "2026-07-19T11:20:00Z",
    "completed_at": "2026-07-19T11:20:00Z",
    "duration_ms": 3
  },
  "error": {
    "code": "BRANCH_PREFIX_NOT_ALLOWED",
    "message": "Branch must use an allowed prefix",
    "retryable": false,
    "details": {"allowed_prefixes": ["feat/", "fix/", "chore/", "docs/", "test/", "refactor/", "hotfix/"]}
  },
  "data": null
}
```

## Adoption boundary

This repository defines the governance and validation contract. The DW1 backend repository must implement the response envelope at its request validator, policy guard, GitHub adapter, and top-level exception boundary. Contract publication alone is not backend implementation evidence.
