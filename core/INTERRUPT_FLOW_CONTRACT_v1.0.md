# Interrupt Flow Contract v1.0

## Purpose

This contract defines the shared interrupt mechanism used by GWC runtime nodes when a workflow cannot safely continue on the current linear path without first refreshing evidence, authority, or repository state.

The first mandatory interrupt type is `BASE_DRIFT`, where the protected base has moved after an approval was issued. The mechanism is generic so later interrupts such as authority expiry, working-head drift, capability loss, or external wait can reuse the same frame and resume contract.

## Core rule

```text
normal node running
→ interrupt detected
→ checkpoint before interrupt
→ suspend parent node
→ push interrupt frame
→ assess interrupt
→ handle through SAFE_CONTINUE / REVALIDATE / REAPPROVE / STOP
→ verify resume conditions
→ pop interrupt frame or reroute
→ resume parent, continue next, wait for authority, or stop
```

A successful evidence refresh is not a new authority grant. `SAFE_CONTINUE` and `REVALIDATE` may preserve the active envelope only when the scope, risk, authorized actions, repository, branch, and task identity remain unchanged. `REAPPROVE` and `STOP` invalidate the active route.

## Runtime invariants

| Invariant | Rule |
|---|---|
| `checkpoint_before_interrupt` | A node cannot be suspended unless the runtime first records a checkpoint containing node, phase, branch/head/base, scope hash, and side-effect state. |
| `parent_cursor_preserved` | The interrupt frame must record the parent node, node version, phase, and checkpoint id. |
| `single_active_interrupt_per_transition` | The same task/base transition cannot create duplicate active interrupt frames. Repeated observations must attach to the existing frame. |
| `no_blind_resume` | A parent node may resume only after branch, head, task, gate, scope, and authority are rechecked. |
| `no_duplicate_side_effect` | If the parent node already performed a side effect, deterministic readback must prove whether to continue next or reroute instead of repeating the action. |
| `resume_is_automatic_when_safe` | `SAFE_CONTINUE` and `REVALIDATE` with passing affected checks resume automatically without a human `continue` command. |
| `authority_change_requires_gate` | Scope, risk, authorized-action, production, merge, deploy, secret, credential, migration, or protected-branch drift requires the relevant gate authority. |
| `append_only_audit` | Interrupt detection, checkpointing, assessment, revalidation, reroute, stop, and resume are append-only events. |

## Interrupt lifecycle

```text
DETECTED
→ CHECKPOINTED
→ PARENT_SUSPENDED
→ ASSESSING
→ HANDLING
→ RESUME_VERIFY
→ RESUMED
```

Terminal alternatives:

```text
REROUTED
REAPPROVAL_REQUIRED
STOPPED
EXPIRED
```

## Resume modes

| Mode | Meaning |
|---|---|
| `RESUME_PARENT` | Return to the suspended parent node at the checkpointed phase. |
| `CONTINUE_NEXT` | Skip re-executing a completed parent side effect and continue to its next node after readback. |
| `REROUTE_REPAIR` | Route to a repair node still inside the active G2 scope. |
| `REROUTE_REAPPROVE` | Generate a refreshed approval package and wait at the authority boundary. |
| `STOP` | Record a terminal blocker and do not resume automatically. |

## Base-drift interrupt routing

| Base-drift decision | Authority effect | Evidence effect | Runtime action |
|---|---|---|---|
| `SAFE_CONTINUE` | Preserve active envelope | Append audit only | `RESUME_PARENT` or `CONTINUE_NEXT` |
| `REVALIDATE` | Preserve active envelope while blocking further writes | Refresh affected validation/integration evidence | Resume only after affected checks pass |
| `REAPPROVE` | Invalidate active envelope | Prior evidence becomes stale where bound to old scope/design | Generate new approval request |
| `STOP` | Invalidate active route | Preserve blocker evidence | Do not resume automatically |

## Required interrupt frame

Every interrupt frame must conform to `schemas/interrupt-frame.schema.json` and record:

- interrupt id, type, state, and timestamps;
- task, gate, repository, branch, base SHA, head SHA, and scope hash;
- parent node, node version, phase, checkpoint id, and side-effect state;
- assessment decision, reason codes, affected gates, affected evidence, and continuation target;
- audit event ids and resume verification result.

## Node interruptibility

Every runtime node that may execute under GWC must declare interruptibility metadata. A side-effect node must expose safe phases such as `PRE_ACTION` and `POST_ACTION_READBACK`; `SIDE_EFFECT_IN_FLIGHT` is never a safe interrupt phase.

Node metadata is validated through `schemas/node-interruptibility.schema.json`.

## Forbidden use

Interrupt flow must never be used to bypass:

- protected-branch write restrictions;
- G0/G1 validator requirements;
- exact G2/G3/G4/G5/G6 authority;
- required CI or exact-head review evidence;
- merge, deploy, release, runtime reload, production configuration, production data, credential, secret, migration, destructive operation, force-push, branch deletion, history rewrite, or PR base change restrictions.
