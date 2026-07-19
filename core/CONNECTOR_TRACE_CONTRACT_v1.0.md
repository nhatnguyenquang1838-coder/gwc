# Connector Trace Contract v1.0

## Status

- Contract ID: `connector-trace-contract`
- Version: `1.0`
- Lifecycle: `active`
- Scope: repository and external-service connector operations

## Purpose

Provide deterministic evidence showing where a connector operation succeeded or failed across the agent, platform runtime, connector backend, policy layer, and upstream provider.

This contract is additive. It does not grant repository write, merge, deployment, production configuration, credential, secret, migration, or production-data authority.

## Required response envelope

Every connector backend operation should return a structured envelope when the invocation reaches that backend.

```yaml
ok: true|false
trace:
  trace_id: <stable correlation id>
  operation: <tool operation name>
  stage: completed|schema_validation|platform_runtime|connector_transport|connector_input_validation|connector_policy|upstream_api|response_serialization|unknown
  connector_received: true|false
  policy_checked: true|false
  upstream_provider: github|null
  upstream_attempted: true|false
  provider_request_id: <provider request id|null>
  http_status: <integer|null>
error:
  code: <stable machine code|null>
  message: <sanitized human-readable message|null>
  retryable: true|false|null
```

## Stage semantics

| Stage | Meaning |
|---|---|
| `schema_validation` | Tool arguments failed before connector invocation. |
| `platform_runtime` | Platform safety/runtime rejected or failed before connector backend execution. |
| `connector_transport` | Invocation was dispatched but connector transport did not complete. |
| `connector_input_validation` | Connector backend rejected malformed or unsupported input. |
| `connector_policy` | Connector policy or authorization rejected the operation before upstream API execution. |
| `upstream_api` | Upstream provider was called and returned an error or rejection. |
| `response_serialization` | Operation completed but response could not be serialized or returned. |
| `completed` | Operation completed successfully. |
| `unknown` | The implementation cannot determine the boundary; this must not be reported as a more specific stage. |

## Attribution rules

1. `connector_received: false` means the backend cannot claim responsibility for a connector policy or upstream failure.
2. `upstream_attempted: true` requires an upstream provider name and should include the provider request ID and HTTP status when available.
3. A GitHub-originated rejection should preserve `X-GitHub-Request-Id` as `provider_request_id` when available.
4. Sanitized error messages must not expose credentials, tokens, authorization headers, cookies, private connection strings, or secret payload fields.
5. Retry recommendations must be based on a stable error code or response category, not speculation.
6. An agent must not state that a named safety layer blocked an operation unless the trace envelope or platform error identifies that boundary.

## Propagation

Connector implementations should propagate W3C Trace Context across service boundaries when supported. The backend-generated `trace_id` remains mandatory in the user-visible structured envelope even when distributed tracing infrastructure is unavailable.

## Compatibility

The trace envelope is additive to existing operation-specific response fields. Existing consumers may ignore `trace` and `error`; new consumers should prefer these fields over parsing free-form error text.

## Bootstrap gap

The GWC repository defines this contract and its conformance tests. Runtime implementation must occur in the repository that owns the DW1 connector backend. Until that source is available and deployed, GWC may validate only the declared contract and agent behavior, not backend runtime conformance.
