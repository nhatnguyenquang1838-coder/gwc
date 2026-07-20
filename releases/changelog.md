# Changelog

## 2026-07-20 — Canonical Kiro spec-driven delivery and ChatGPT task parity

### Added

- Canonical `core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md` for reusable requirements, design, and implementation-task planning under `.kiro/specs/<SPEC-ID>/`.
- Explicit ChatGPT/local-agent runtime parity: one AgentOps/DS Admin task, legal transitions through `agent_running`, and task-scoped `.gwc/tasks/<task-id>/g0`, `g1`, and `g2` evidence before G2.
- Canonical rule registration and distribution through the `gwc`, `ds-mcp`, and `rental-home` packages.

### Changed

- GWC package version `1.14.0`, DS MCP package version `1.2.0`, and Rental Home package version `1.1.0` include the canonical rule.
- Rental Home spec guidance is now an additive adapter that retains project naming, Mermaid dependency graphs, `src/app/dependencies.ts`, Supabase access, RLS/schema, and validation constraints without duplicating the shared template.
- ChatGPT and project-consumer instructions now require the existing `.gwc/tasks/<task-id>` mechanism instead of a parallel or conversation-only task artifact format.

### Compatibility

- Existing specs are not moved or rewritten automatically.
- Project-local rules may add stricter naming, architecture, security, data, and validation constraints but may not weaken canonical GWC gates.

### Safety

- Kiro specs, task creation, `agent_running`, and valid `.gwc` artifacts are traceability only.
- This change grants no protected-branch write, merge, auto-merge, deployment, release, production configuration, credential, migration, or production-data authority.

## 2026-07-19 — DW1 connector structured trace contract

### Added

- Additive connector trace contract defining deterministic failure-stage attribution across platform runtime, connector transport, connector validation/policy, and GitHub API boundaries.
- JSON Schema for trace IDs, operation names, stage values, upstream-attempt evidence, provider request IDs, HTTP status, and normalized retry metadata.
- Contract tests for successful GitHub calls, connector-policy rejection, required error envelopes, and non-speculative safety-layer attribution.

### Changed

- DWC instructions now require structured trace evidence before naming the blocking layer.
- DWC capabilities declare structured connector tracing as `contract_defined_runtime_bootstrap_gap`.

### Limitations

- The DW1 backend source is not present in this repository. Runtime instrumentation and deployment must occur in the connector implementation repository before these fields can be treated as live runtime evidence.

### Safety

- This additive contract grants no merge, deployment, release, production configuration, credential, secret, migration, or production-data authority.

## 2026-07-19 — G0/G1 Context7-first offline skill fallback

### Added

- Deterministic offline skill library for G0 and G1 under `libs/g0-g1-skill-library/`.
- Context7-first skill resolution for G0 (`skills/gwc-g0/SKILL.md`) and G1 (`skills/gwc-g1/SKILL.md`) with bundle-atomic fallback policy.
- Pinned offline manifest, SHA-256 verification, provenance notice, and G0/G1-compatible normalized skill cards:
  - `g0-context-loading`
  - `g1-intake-options-preflight`
  - `g1-decision-record`
  - `g0-g1-approval-envelope`
- Contract tests for Context7-first ordering, bundle-atomic fallback, offline file hashes, required skill composition, and exact evidence boundaries.
- GWC project package entries distributing the new G0/G1 skill library.

### Changed

- G0 and G1 skills now use exactly one source mode per run: `CONTEXT7_LIVE` or `OFFLINE_PINNED`; live and offline cards cannot be mixed.
- GWC project package version `1.14.0` distributes the G0/G1 skill library and updated skills.

### Safety

- Live and offline skill content is non-authoritative relative to protected-base GWC governance.
- Offline cards do not grant execution, merge, deployment, release, production configuration, credential, migration, or production-data authority.
- G0/G1 remain read-only and planning-only gates; G2 execution still requires a valid envelope and explicit approval.

## 2026-07-19 — G3 Context7-first offline skill fallback

### Added

- GWC-native `gwc-g3` skill for Draft PR assembly, exact-head read-only review, finding routing, review closure, and G4 approval preparation.
- Context7-first skill resolution for `/obra/superpowers` with deterministic offline fallback under `libs/g3-skill-library/`.
- Pinned offline manifest, SHA-256 verification, provenance notice, and G3-compatible normalized review cards.
- Contract tests for Context7-first ordering, bundle-atomic fallback, offline file hashes, exact-head evidence, and later-gate exclusions.

### Changed

- GWC package version `1.13.0` distributes the G3 skill and offline fallback library.
- G3 uses exactly one source mode per run: `CONTEXT7_LIVE` or `OFFLINE_PINNED`; live and offline cards cannot be mixed.

### Safety

- Live and offline skill content is non-authoritative relative to protected-base GWC governance.
- Offline cards do not grant merge, ready-for-review, branch cleanup, deployment, production configuration, credentials, migrations, or production-data authority.
- G3 remains Draft-PR-only; G4 merge still requires a separate exact human approval for the current PR head SHA.

## 2026-07-18 - Capability-aware ChatGPT agent harmonization

### Changed

- Root agent routing now applies the shared GWC boot to every agent and selects
  `local_agent` or `chat_connector_only` from verified capabilities rather than
  an agent-name or conversation-surface branch.
- ChatGPT instructions are now an additive overlay on `AGENTS.md`: they retain
  runtime banner, intake and file tracking, exact-SHA artifact recovery,
  proactive gate continuation, and exact approval commands without repeating
  the shared gate contract.
- Repository connectors now use the active profile's ordered fallback. Agents
  do not need to onboard every connector when a trusted local checkout or an
  earlier verified connector supplies the required evidence.
- GWC project package version `1.12.0` distributes the harmonized ChatGPT
  overlay. The `gwc` project is the only package consumer of this source.

### Rollout and rollback

- Roll out by building package `1.12.0`, reviewing the semantic package diff,
  and updating consumers only through their pinned-package workflow.
- Roll back by keeping consumers pinned to package `1.11.0`; do not hand-edit a
  generated rollout package.

### Safety

- This change does not alter core policy, gate schemas, lifecycle order, merge,
  deployment, production configuration, credentials, migrations, or production
  data authority.
- Connector fallback never substitutes for repository identity, task claim,
  gate artifacts, validator evidence, or an exact approval boundary.

## 2026-07-18 — ChatGPT artifact-driven gate continuation

### Added

- ChatGPT agents now read the protected-main G0/G1 operational runbook during mandatory context boot.
- A deterministic recovery sequence requires exact-SHA fetch of gate artifacts, schemas, templates, validators, and source evidence into an isolated task workspace before reporting a remediable validator gap as blocked.
- Gate exits now require proactive generation of the next canonical artifact and exact approval request through G2, G3, G4, G5, and G6.
- Focused tests enforce the runbook boot dependency, isolated artifact recovery, hard-stop boundaries, and package distribution entry.

### Changed

- GWC project package version `1.11.0` distributes the operational runbook and updated ChatGPT agent instructions.
- Missing local files, raw-download transport failures, stale generated artifacts, and remediable schema errors are recovery conditions rather than automatic workflow termination.

### Safety

- Artifact recovery does not grant authority. Protected-branch writes, merge, deployment, release, production configuration, credentials, migrations, production data, scope drift, expired approval, and connector hard denial remain stop conditions.
- Draft PR delivery remains separate from G4 merge authority.

## 2026-07-15 — Connector precedence update

### Changed

- GWC project profile now declares repository connector precedence as GitHub,
  then DWC, then DW1.
- GWC project instructions and DWC agent instructions now require the same
  connector order and forbid silently skipping a higher-priority connector.
- GWC project package version `1.9.0` records the connector precedence update.

### Safety

- This update changes connector-selection policy only.
- It does not grant merge, deployment, production configuration, credential,
  migration, or production-data authority.

## 2026-07-15 — G3 independent reviewer delivery contract

### Added

- G3 delivery-record schema and template formalize Draft PR identity, exact head SHA, scope hash, validation, CI, review lanes, acceptance criteria, findings, residual risks, exclusions, and final outcome.
- Deterministic `validate_g3_delivery.py` enforces reviewer separation, read-only review, exact-head freshness, severity policy, acceptance-criteria evidence, required CI, and G4/G5/G6 boundaries.
- Twelve focused tests cover valid delivery evidence, stale or mismatched heads, reviewer conflict, blocker and major findings, explicit risk acceptance, lane coverage, CI binding, unverified acceptance criteria, and valid `changes_required` evidence that routes open blockers back to G2.
- GWC project package version `1.8.0` distributes the G3 schema, template, and validator.

### Changed

- G3 now uses internal PR Assembly, Independent Review, and Review Closure stages without introducing another lifecycle gate.
- Blocking review findings return to G2 for separately authorized revision; every new PR head SHA invalidates earlier review evidence and requires re-review.
- Project and DWC instructions now require a read-only reviewer and exact-head delivery evidence before G3 can pass.

### Safety

- Reviewer PASS is evidence only and never grants G4 merge authority.
- This update does not authorize merge, deployment, release, production configuration, credentials, secrets, migrations, or production-data operations.

## 2026-07-15 — Operating runtime hardening

### Added

- Agent Operating Runtime Contract v1.0 centralizes SOURCE INSTRUCTION, Intake Card, Files READ/WRITE, context refresh, ChatGPT connector-only Git behavior, validation honesty, and agent-generated approval commands.
- Instruction Source Registry defines centrally managed source priority across protected-base GWC files, Google Drive native project docs, generated packages, and GPT Project instructions.
- Approval Request schema defines the agent-generated approval context and exact copy-paste command shape.
- Instruction Source Registry schema validates registry shape and source entries.
- Approval command tests ensure `ok`, `approve`, `continue`, and similar phrases remain acknowledgement-only, while exact generated approval commands are recognized.
- Registry tests validate source registry schema conformance, source ID uniqueness, and priority uniqueness.
- GWC project package version `1.7.0` distributes the operating runtime contract, approval schema, source registry, and registry schema.

### Changed

- ChatGPT Agent Instructions now require SOURCE INSTRUCTION, Intake Card, Files READ/WRITE, context refresh, and agent-generated approval commands before write-capable work.
- GWC project profile now reads the operating runtime contract and instruction source registry during protected-base boot.
- Plain acknowledgements such as `ok`, `approve`, `approved`, `continue`, `go`, `yes`, `làm đi`, and `fix ngay` are explicitly not gate authority.
- Humans do not invent approval tokens or scope hashes; agents generate the exact approval command and humans copy-paste it.

### Safety

- This update does not grant merge, deployment, production configuration, credential, migration, or production-data authority.
- Draft PR delivery remains separate from G4 merge authority.
- CI success remains evidence only and does not grant authority.

## 2026-07-15

### Added

- Gate Lifecycle Contract v1.0 defines G0 through G6 entry evidence, permitted
  actions, exit evidence, authority boundaries, action-to-gate mapping, and
  fail-closed behavior.
- ChatGPT Agent Instructions define `chat_connector_only` defaults, mandatory
  context boot, repository-evidence precedence, G0/G1 reporting, and write-stop
  behavior when validator evidence is unavailable.
- Project Consumer Agent Instructions define the minimum project-level
  `AGENTS.md` pattern for repositories that consume GWC through a pinned
  submodule or generated governance package.
- GWC project package version `1.6.0` distributes the gate lifecycle contract,
  ChatGPT agent instructions, and project consumer instructions.

### Changed

- `AGENTS.md`, coding-agent bootstrap, and DWC instructions now require explicit
  execution mode selection: `chat_connector_only`, `local_agent`, or `repo_ci`.
- G0/G1 completion can no longer be claimed from conversation reasoning alone;
  G1 `PASS` requires `tools/validate_g01.py` evidence or trusted external
  validator evidence.
- Chat connector agents remain read-only for repository-changing work when local
  validator evidence is unavailable, avoiding the branch-before-artifact
  deadlock.
- GWC validation now requires the new gate contract and ChatGPT/project-consumer
  instruction sources.
- Rental Home profile identity evidence was corrected to reference the actual
  `nhatnguyenquang1838-coder/rental_home` repository rather than the GWC source
  remote.

### Safety

- The update does not grant merge, deployment, production configuration,
  credential, migration, or production-data authority.
- CI success remains evidence only and does not grant authority.
- The previous Rental Home rollout hardening remains deferred until GWC gate
  enforcement is reviewed and merged.

## 2026-07-14

### Added

- Global Agent Behavior Semantic Contract v1.0 consolidates evidence precedence,
  understand-before-recommend flow, existing-before-new analysis, generated
  artifact ownership, bounded execution modes, and graceful fallback behavior.
- Global Agent Response Presentation Contract v1.0 selects direct Markdown,
  tables, Mermaid, SVG/PNG, YAML/JSON, or command blocks according to task
  complexity and consumer needs.
- Agent-readable GWC G0 skill wrapper for project activation, repository and
  protected-base verification, policy/source resolution, connector and task
  context checks, freshness handling, and a bounded handoff into G1.
- Agent-readable GWC G1 skill wrapper for intake, existing-mechanism inspection,
  brainstorming, preflight, explicit decision preparation, and G2 handoff
  preparation after G0 is ready.
- GWC project package version `1.4.0` distributes both skills as governed source
  instruction artifacts.

### Changed

- GWC project package version `1.5.0` distributes both global contracts and the
  GWC project profile loads them during protected-base boot.
- GWC project instructions now fail closed before mutation or authority
  escalation while allowing qualified read-only and planning fallbacks when
  task, connector, persistence, validation, or rendering evidence is missing.
- Presentation defaults are adaptive: simple responses are not forced to use
  Mermaid or SVG, while stricter project and approval artifact requirements
  remain in force.
- G1 now consumes a verified G0 handoff instead of owning a duplicate context
  reconstruction step.
- G1 skill expanded to version `0.3.0` with phase boundaries, artifact contract
  summaries, intake matrix, option selection rules, preflight outcomes, decision
  status rules, G2 handoff shape, and completion markers.
- G1 now requires run identity metadata for each session: `run_id`,
  `workspace_mode`, `workspace_root`, repository artifact write state,
  conflict policy, and verification mode.
- G1 chat-only mode is explicitly conversation-local and must not write
  `.gwc/g1/...`; concurrent artifact runs must use isolated workspaces or fail
  closed on unknown workspace ownership.
- The skills document that task and risk facts are runtime/preflight inputs but
  are not fields in the canonical G0 context snapshot schema version `1.0`.

### Safety

- The new contracts are additive and do not modify the canonical core policy,
  canonical SHA, G0/G1 schemas or tools, authority gates, workflows, secrets,
  production configuration, or production data.
- Planning and read-only fallbacks never grant branch, commit, push, PR, merge,
  deployment, release, or production authority.
- The G0 and G1 skills are instruction-only and do not add validators,
  executable tools, repository write authority, merge authority, deployment
  authority, production configuration, credentials, or production-data access.
- Anthropic and Superpowers skill patterns are used as reference material only;
  they cannot override GWC protected-base governance.

## 2026-07-13

### Added

- Versioned G01 decision input schema and deterministic options/decision capture
  tool with explicit-choice enforcement, scope hashing, and full workspace validation.
- Decision capture fixture and six focused tests covering PASS, blocked,
  non-explicit, rejected, duplicate-option, and CLI end-to-end behavior.
- Versioned G01 runtime input schema and deterministic generator for G0 context,
  G1 intake, and G1 preflight artifacts.
- Fail-closed runtime checks for repository identity, required sources, DS Admin
  task claim, intake completeness, and R2/R3 human direction.
- Runtime fixture, five focused unit tests, package assets, and usage documentation.
- Versioned G0 context and G1 intake, preflight, options, and decision schemas.
- Deterministic fail-closed G0/G1 validator, reusable YAML templates, fixtures,
  unit tests, and lifecycle documentation.
- Base drift evaluation policy, schema, evaluator, tests, and documentation for
  evaluating protected-base SHA changes after approval.

### Changed

- GWC project package version `1.3.0` includes G0/G1 lifecycle documentation,
  runtime and decision schemas, generator/capture tools, templates, fixtures,
  and validation tests.
