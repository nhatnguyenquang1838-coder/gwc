# SCRUM-116 implementation design

Use a governed control-plane plus target-runtime ownership topology. Keep package code in `DW-SuperApps/.dw/powers`, thin host routing in DW-SuperApps host adapters, GWC gate artifacts in `.gwc/tasks/<task-id>/`, and selected target generated outputs in `.ua`, `.task-me` and `.bmad` roots.

The contract is machine-readable in `core/integration/dw-super-app-integration-contract.json`, schema-validated by `schemas/integration/dw-super-app-integration.schema.json`, and described in `core/integration/DW_SUPER_APP_INTEGRATION_TOPOLOGY_v1.0.md`. Existing SCRUM-105/SCRUM-108 checkpoint, CAS, lease and fencing contracts are reused.

The validator must enforce one owner/root per artifact class, non-authoritative projection roles, complete compatibility modes, exact downstream references, and positive plus fail-closed provenance examples.
