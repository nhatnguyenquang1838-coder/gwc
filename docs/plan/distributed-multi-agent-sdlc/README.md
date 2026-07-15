# Distributed Multi-Agent SDLC — Spec Package

## Purpose

This package defines:

1. **Pilot v1** — a bounded, measurable end-to-end pilot using DS MCP as the Hub and Rental Home as the first Spoke.
2. **Rental Home Adapter** — the project-specific integration needed to expose machine-readable validation evidence without changing production data, schema, auth, or RLS.
3. **End-State Full Scope** — the target multi-project control-plane architecture and phased roadmap.

The package is planning evidence only. It does not authorize repository writes, merge, deployment, production configuration, credentials, migrations, or production-data access.

## Proposed Repository Placement

```text
dw18031988/ds_mcp_server
└── .kiro/specs/
    ├── DS-OPS-08-multi-agent-pilot-v1/
    │   ├── requirements.md
    │   ├── design.md
    │   └── tasks.md
    └── DS-OPS-09-distributed-multi-agent-end-state/
        ├── requirements.md
        ├── design.md
        └── tasks.md

nhatnguyenquang1838-coder/rental_home
└── .kiro/specs/
    └── OPS-AGENT-01-multi-agent-pilot-adapter/
        ├── requirements.md
        ├── design.md
        └── tasks.md
```

## Ownership Model

| Scope | Repository owner |
|---|---|
| Control plane, workflow stages, claims, leases, evidence binding, scheduler and dashboard | `dw18031988/ds_mcp_server` |
| Project adapter, validation output, project workflow projection | `nhatnguyenquang1838-coder/rental_home` |
| Governance contract changes only when a concrete gap is proven | `nhatnguyenquang1838-coder/gwc` |

## Gate Boundary

```text
G0_CONTEXT
→ G1_ALIGNMENT
→ G2_EXECUTION
→ G3_PR
→ Human G4_MERGE
→ Human G5_DEPLOY
→ G6 only for separately authorized production operations
```

Pilot implementation must stop at validated Draft PRs unless separate gate authority is provided.

## Evidence Baseline

| Repository / source | Baseline |
|---|---|
| GWC main | `ae81b3d03dcbbd582eb34dae7911883e675b7c08` |
| DS MCP main | `db84dfb754656f1c119ebfdc0a053e592b1ebd18` |
| Rental Home main | `a3787e8706a53fcf78228d131ae4a134d1511634` |
| GWC lifecycle contract | `core/GATE_LIFECYCLE_CONTRACT_v1.0.md` |
| GWC E2E rule | `core/E2E_DRAFT_PR_DELIVERY_RULE.md` |
| DS MCP claim rule | `projects/ds-mcp/admin-task-claim-rule.md` |
| Rental Home spec format | `projects/rental-home/spec-driven-format.md` |

All base SHAs must be re-resolved during task-scoped G0 before implementation.
