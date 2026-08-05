# SCRUM-191 — Requirements (Task Me plan)

Task: [MAT-F2-N08] `gate_authority.g2-execution-envelope-render` (M2 → M5)
Parent: SCRUM-167
Repository: nhatnguyenquang1838-coder/gwc
Protected base: 54fcc4c5395d0b3dabfe0564d5b3f8ad8daa3337
Selected option: OPT-1
Risk class: R2

## Functional requirements

1. Render a closed, bounded G2 execution envelope deterministically from approved F1 scope
   artifacts and F2 authority decisions. Identical inputs must always render an identical envelope.
2. The rendered envelope is a closed set: read scope, write scope, authorized actions, excluded
   actions, and evidence bindings are enumerated exhaustively; no implicit or wildcard authority.
3. Bind exactly to the F1 scope artifacts (intake scope, acceptance criteria, scope hash) and to the
   F2 authority decision outputs (authority-boundary decision, approval validation from SCRUM-186).
4. Envelope lifecycle states are exactly `DRAFT`, `AWAITING_APPROVAL`, and `ACTIVE`. A rendered
   envelope is never `ACTIVE` before a validated approval is bound.
5. Later gates (`G3_PR`, `G4_MERGE`, `G5_DEPLOY`, `G6_PRODUCTION`) are always listed as excluded.
6. Checkpoint/replay: the renderer emits a replay digest so an envelope can be re-rendered and
   compared byte-for-byte after a crash or resume.
7. The renderer is pure — it performs no connector call, no repository write, and no execution.

## Non-functional requirements

- Pure Python standard library plus the repository's existing `jsonschema` usage; no new dependencies.
- Fail closed: any missing, invalid, drifted, or unapproved binding yields a refusal result rather
  than a permissive envelope.
- Deterministic ordering and stable serialization for all collections.

## Acceptance criteria mapping

- AC-1 → closed envelope schema (`schemas/g2-execution-envelope.schema.json`)
- AC-2 → exact F1/F2 binding fidelity
- AC-3 → inactive-before-approval lifecycle
- AC-4 → later-gate exclusions and no execution authority
- AC-5 → checkpoint/replay determinism
- AC-6 → focused M5 tests pass
