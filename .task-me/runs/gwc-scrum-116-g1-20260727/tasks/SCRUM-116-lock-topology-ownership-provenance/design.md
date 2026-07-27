# SCRUM-116 architecture handoff

## Architecture spine

Use a governed control-plane plus target-runtime ownership model. The package store and host adapters live in DW-SuperApps; GWC gate artifacts and governance contracts live in the GWC repository; each selected target owns generated `.gwc`, `.ua`, `.task-me`, and `.bmad` outputs. Projections read canonical state but never grant authority.

## Durable invariants

- AD-1: one artifact class has one canonical owner root.
- AD-2: provenance is exact-ref and exact-SHA based, never conversation based.
- AD-3: mutation requires owner, scope hash, current checkpoint revision and valid lease/fencing token.
- AD-4: projection failure cannot alter canonical state or gate outcome.
- AD-5: compatibility fallback is additive and preserves existing installations.

## Proposed contract surfaces

Topology matrix, source-of-truth matrix, ownership/denied-write matrix, provenance envelope schema, collision/fencing fixtures, compatibility matrix and downstream reference map. Exact filenames and symbols remain a G2 discovery item and must be read back before mutation.
