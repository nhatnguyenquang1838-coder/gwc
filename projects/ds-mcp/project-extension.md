---
extension_id: ds-mcp-conventions
version: '1.0'
authoritative: false
extends_profile: ds-mcp
core_policy: CODING-PROJECT-GOVERNANCE@1.0
core_sha256: 04cd33bbaff66f44917199e6bbb8355a1e956edb9c474e6c8e664ed8d0ed41c1
mode: tighten_only
source_note: DS MCP API, workflow, connector, data, and Admin UI invariants.
---

# DS MCP Project Extension

> This extension adds DS MCP-specific constraints and cannot weaken the generic core.

## Architecture boundaries

- Reuse existing schemas, repositories, route policies, State Engine, audit event model, error contracts, and Admin UI components.
- Generic CRUD MUST NOT mutate workflow state, current task, leases, claims, or transitions outside validated State Engine operations.
- Consistency-critical multi-table operations MUST use a database transaction or transactional Supabase RPC.
- Bulk operations MUST declare atomic versus partial-success semantics and be bounded, duplicate-safe, idempotent where retried, and auditable.
- Destructive actions default to non-force. `force` requires dependency preview, explicit confirmation, audit evidence, and the applicable production-data gate.

## API and security

- Register every new sensitive route and HTTP method in the existing route-policy abstraction.
- Enforce bearer/authentication, role, ownership, and resource relationship server-side.
- Apply critical-write rate limits to state-changing or destructive endpoints.
- Preserve request IDs and structured error details without exposing secrets.
- Document new public REST/MCP operations, payloads, status codes, partial-success semantics, and retry behavior.

## Repository and connector

- GitHub operations use the `DW` connector declared by the profile.
- REST base context is `https://ds-mcp-server-one.vercel.app/`; this is context only and does not authorize network calls or deployment.
- Never push directly to `main`; use a dedicated branch/worktree.
- After every PR push, apply the core `+2 minute` CI monitoring and bounded repair loop.

## Validation focus

Applicable tests must cover:

- Workflow ownership, current-task consistency, transition legality, claim ordering, lease protection, and active-workflow mutation.
- Transaction rollback and partial-failure prevention.
- Forced and non-forced destructive behavior.
- Auth, authorization denial, route policy, rate limiting, request IDs, and secret redaction.
- Admin UI loading, disabled CTA, confirmation, filtering, hidden selection, and failure output.
