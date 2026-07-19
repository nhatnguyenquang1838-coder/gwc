# GWC G2 Skill
## Purpose

This skill establishes the execution contract for transitioning from a validated G1 intent to low-level, transactional repository mutations required to achieve the target G3 Draft PR state. It is the active gatekeeper between high-level design/intent (G1) and implementation artifact creation (G3).

## Authority Boundary

G2 is the phase where `libs/gwc-g2-execution-library` artifacts are used to manage the isolated working tree. It maintains a strictly limited set of authorized actions against the base repository SHA:

**Allowed Actions:**
- Add/Modify File within approved ranges.
- Commit a single, logical change representing the G1 fix.
- Create/Bind an isolated working branch from a known, valid base SHA.
- Push the finalized, guarded branch reference.
- Apply React/Vite engineering standards (Component structure, State management, Performance optimization, and Testing) as defined in the G2 skill library.

**Hard Exclusions (Failure Conditions):**
Any attempt to execute actions outside the bounds of `G1_APPROVAL_HASH` or attempting unauthorized commits (e.g., squashing, rewriting shared history) must be blocked by `g2-repository-interaction.md` and result in a failure code before touching the remote repository.

## Skill Source Resolution (Context7/Offline)

Use Context7 first for blueprinting and transaction mapping. Offline execution relies on the canonical library structure:

```text
/obra/superpowers
```

**Resolution Order:**
1. Query Context7 for optimal transaction sequences and potential conflicts based on the G1 intent hash.
2. Fallback to `libs/g2-skill-library/` artifacts if Context7 is unavailable, empty, or incompatible.
3. Verify all offline files against `libs/g2-skill-library/manifest.yaml`.
4. If neither source is valid, stop with `G2_SKILL_SOURCE_BLOCKED`.

## Artifacts Used

The G2 execution is supported by the following artifacts in `libs/g2-skill-library/`:
- `g2-execution-plan.md` (The sequence blueprint)
- `g2-repository-interaction.md` (The action constraint layer)
- `g2-approval-envelope.md` (The transition artifact)
- `g2-react-vite-component-structure.md` (React/Vite component standards)
- `g2-react-vite-state-management.md` (React/Vite state patterns)
- `g2-react-vite-performance.md` (React/Vite performance & compiler rules)
- `g2-react-vite-testing.md` (React/Vite testing & act() standards)

## Run Identity and Workspace Mode
Every G2 session must declare a stable `run_id` before executing transactional steps:

- **Modes:** `chat-only`, `canonical`, or `session-scoped`.
- **Workspace Root:** Must follow the canonical paths detailed in `libs/g2-skill-library/README.md` for proper artifact persistence and version control integration.

**Action:** The G2 artifacts are the operational culmination of G1's approval and the precursors to G3's review.
