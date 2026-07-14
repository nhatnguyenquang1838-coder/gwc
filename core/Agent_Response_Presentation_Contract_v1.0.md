# Agent Response Presentation Contract v1.0

## Status

- Contract ID: `agent-response-presentation-contract`
- Version: `1.0`
- Lifecycle: `active`
- Scope: agent responses and review artifacts produced under a GWC project package

## Purpose

Select the simplest response format that preserves accuracy, traceability, and
usability for the current task.

This contract is adaptive. It does not require a diagram, table, SVG, PNG,
YAML, or JSON when direct Markdown is clearer. A higher-priority project or
approval rule may still require specific review artifacts.

## Core principles

- Answer the user's actual question before adding process detail.
- Match presentation complexity to task complexity.
- Separate observed evidence, inference, decision, action, and limitation.
- Prefer compact structure over decorative formatting.
- Use visuals only when relationships, state, sequence, or architecture are
  materially easier to understand visually.
- Do not claim that an artifact exists unless it was produced and persisted.

## Format selection

Use this default selection matrix:

| Task shape | Preferred presentation |
|---|---|
| Simple factual or read-only answer | Direct Markdown paragraphs |
| Status across several items | Compact table plus conclusion |
| Multi-step task or implementation report | Flow-based sections in execution order |
| Comparison or decision | Comparison table, recommendation, and trade-offs |
| Workflow, lifecycle, or state transition | Mermaid diagram plus a concise text explanation |
| Architecture or cross-component change | Structured proposal plus Mermaid; add SVG/PNG only when required or materially useful |
| Machine-consumed result | Valid YAML or JSON matching the declared contract |
| Exact user action or command | One standalone fenced block per command |
| Error, limitation, or blocked operation | Current state, evidence, safe fallback, and next legal action |

When the task shape is unclear, default to concise Markdown and escalate only as
needed.

## Response flow for non-trivial work

Use sections that follow the work rather than an arbitrary template:

```text
Context
→ Evidence
→ Existing mechanism
→ Gap
→ Options or change
→ Validation
→ Impact and risk
→ Next legal action
```

Omit sections that add no value. Do not force a full governance report onto a
simple question.

## Tables

Use tables when the user must compare multiple items or dimensions.

Good uses:

- current versus proposed behavior;
- option trade-offs;
- PR, task, validation, or CI status;
- current mechanism, limitation, improvement, compatibility, and impact.

Avoid tables for long prose, nested reasoning, or a single fact.

## Mermaid

Use Mermaid for:

- workflow and lifecycle sequences;
- state transitions;
- dependency relationships;
- architecture boundaries;
- decision paths with meaningful branches.

Rules:

- Keep diagrams small enough to review without scrolling through unrelated
  detail.
- Provide a text explanation so the answer remains useful when Mermaid does not
  render.
- Do not use Mermaid as decoration for a linear fact that is clearer in one
  sentence.
- A diagram is evidence of presentation only; it does not grant execution or
  approval authority.

Fallback:

```text
Mermaid unavailable or unreadable
→ use a numbered text flow or compact relationship table
→ state that no rendered diagram was produced
```

## SVG and PNG

Generate SVG or PNG only when:

- the user requests a visual artifact;
- the active project or approval workflow explicitly requires it;
- a stable architecture or change-proposal artifact has review value beyond a
  Mermaid source diagram;
- the result must be consumed outside the current chat.

Do not generate SVG/PNG automatically for routine status, explanation, or
small workflow responses.

When SVG/PNG is required:

- preserve a reviewable source representation;
- validate layout and content where a validator exists;
- avoid clipped labels, crossing elements, and unreadable density;
- provide a truthful fallback when rendering or validation is unavailable.

Fallback:

```text
SVG/PNG unavailable
→ preserve the structured source and Mermaid/text equivalent
→ report the missing renderer or validation step
→ continue read-only review when the visual is not an authority prerequisite
```

If a higher-priority approval contract requires specific visual hashes or files,
missing visuals remain a blocker for that approval path.

## YAML and JSON

Use YAML or JSON only for machine-consumed contracts, task payloads, manifests,
configuration examples, or explicitly requested structured output.

Rules:

- Match the active schema when one exists.
- Do not mix comments into strict JSON.
- Distinguish examples from observed current values.
- Do not invent IDs, SHAs, timestamps, task states, approvals, or connector
  results.

## Commands and exact user actions

Place every exact command, activation phrase, approval token, or retry action in
a standalone fenced block.

Use one command per block when the user may copy and execute it independently.
Do not present placeholders as executable values without clearly marking them.

## Evidence and verification labels

For repository, task, PR, CI, or artifact work, make the verification level
visible when it affects trust:

```text
TOOL_VERIFIED
LOCAL_VERIFIED
USER_PROVIDED
INFERRED
UNVERIFIED_BY_TOOL
```

Do not add labels to every casual answer. Use them where the distinction changes
what the user may safely do next.

## Progress and completion reporting

For a running multi-step task, report progress at meaningful boundaries rather
than narrating every tool call.

A completion report should prioritize:

1. outcome;
2. changed behavior or decision;
3. evidence and validation;
4. unresolved risk or limitation;
5. next legal action.

Do not bury a failed check, missing artifact, pending CI run, or unperformed
operation below a success statement.

## Graceful presentation fallback

Presentation failure must not stop safe analysis unnecessarily.

| Preferred output unavailable | Fallback |
|---|---|
| Mermaid renderer | Text flow or table |
| SVG/PNG renderer | Mermaid/source plus explicit limitation |
| Interactive table | Markdown table |
| Structured artifact persistence | Inline YAML/JSON marked conversation-local |
| Repository or connector evidence | Planning-only response marked unverified |
| Full detail would overwhelm the user | Conclusion first, then bounded evidence |

Stop only when the missing presentation artifact is itself a required approval,
validation, or consumer contract.

## Compatibility and authority

This contract changes presentation, not authority.

It must not:

- bypass G0/G1 or project boot requirements;
- replace repository evidence with attractive formatting;
- convert a recommendation into a decision;
- convert CI success into merge or deployment permission;
- imply repository persistence from a chat-only response;
- weaken a stricter project-specific artifact or approval requirement.
