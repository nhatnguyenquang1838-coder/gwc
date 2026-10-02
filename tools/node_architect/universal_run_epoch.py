#!/usr/bin/env python3
"""Universal Runtime v2 — runtime epoch and control-plane cut-over.

This module is the branch-local normative runtime contract for the
Universal Runtime v2 development lane (SCRUM-781 Q0, branch
``fix/SCRUM-781-q0-canonical``).  It is PURE and transport-neutral: it
performs no repository, mailbox, authority, or external effect.  It provides
the deterministic epoch/router semantics that AGENTS.md, the runtime
entrypoint, the Controller liveness invariant, and the Q0 self-remediation
loop read at boot:

- ``runtime_epoch == UNIVERSAL_V2_DEVELOPMENT`` is normative for this lane.
- Legacy GWC G0/G1/G2 semantics, WAIT/HOLD control, legacy artifacts,
  legacy approval and legacy NEXT never own the Universal cursor and never
  block the Universal parent.
- Universal failure is ``GWC_RUNTIME_DEFECT`` -> Q0 self-remediation, never
  a fallback into the legacy runtime.
- ``EFFECT_HOLD != CONTROL_LOOP_STOP``: a prohibited effect holds that
  effect only; Controller-owned safe preparation/remediation continues.
- One Q0 run -> one development branch -> one canonical worktree -> additive
  immutable repair commits.

Hard safety boundaries are NOT granted here: protected main, merge,
auto-merge, deployment, production config/data, credentials/secrets,
migrations, destructive actions, force-push/history rewrite, and unrelated
product scope remain prohibited by the governing contracts.

Namespacing: Universal gates are ``UR.G0 .. UR.G6`` and are NOT aliases for
legacy ``G0 .. G6``.  A caller must always qualify the epoch when it combines
gate vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

RUNTIME_EPOCH_UNIVERSAL_V2 = "UNIVERSAL_V2_DEVELOPMENT"
RUNTIME_EPOCH_LEGACY = "LEGACY_GWC_V1"

# The only lifecycle vocabulary for this development lane.  These are NOT
# aliases of legacy G0..G6.
UNIVERSAL_GATES = (
    "UR.G0",  # UNDERSTAND
    "UR.G1",  # PLAN / DECOMPOSE
    "UR.G2",  # EXECUTE
    "UR.G3",  # VERIFY
    "UR.G4",  # INTEGRATE
    "UR.G5",  # VALIDATE_IN_TARGET
    "UR.G6",  # ACCEPT_AND_HANDOFF
)

# Q0 development lane identity.
Q0_TASK_ID = "SCRUM-781"
Q0_BRANCH_PREFIX = "fix/SCRUM-781-q0-"
Q0_CANONICAL_BRANCH = "fix/SCRUM-781-q0-canonical"
Q0_CANONICAL_WORKTREE = "q0/SCRUM-781-q0-universal-v2"

BLOCKER_CLASSES = (
    "SELF_REMEDIABLE",
    "MISSING_TECHNICAL_ARTIFACT",
    "MISSING_RUNTIME_COMPONENT",
    "VALIDATION_FAILURE",
    "LEGACY_POLICY_CONFLICT",
    "TRUE_HUMAN_DECISION",
    "HARD_AUTHORITY_BOUNDARY",
)


class UniversalV2EpochError(ValueError):
    """Deterministic fail-closed epoch/router error."""


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise UniversalV2EpochError(code if not detail else f"{code}: {detail}")


@dataclass(frozen=True)
class EpochDecision:
    """Immutable epoch-resolution decision (no authority attached)."""

    runtime_epoch: str
    normative: bool
    route: str
    legacy_runtime_entry_forbidden: bool
    legacy_fallback: bool
    lane_task_id: str = ""
    lane_branch: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_epoch": self.runtime_epoch,
            "normative": self.normative,
            "route": self.route,
            "legacy_runtime_entry_forbidden": self.legacy_runtime_entry_forbidden,
            "legacy_fallback": self.legacy_fallback,
            "lane_task_id": self.lane_task_id,
            "lane_branch": self.lane_branch,
        }


def resolve_runtime_epoch(
    *,
    task_id: str,
    branch: str,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve the normative runtime epoch for a boot request.

    Deterministic resolution for the Q0 development lane:

    - If ``context`` explicitly declares ``runtime_epoch ==
      UNIVERSAL_V2_DEVELOPMENT``, that is honored (explicit lane contract).
    - Otherwise the lane is resolved from task/branch identity: the
      SCRUM-781 Q0 development branch selects UNIVERSAL_V2_DEVELOPMENT.
    - Any un-resolvable combination fails closed with
      ``UNIVERSAL_V2_LANE_UNRESOLVED`` rather than guessing a runtime.
    """
    ctx = dict(context or {})
    explicit = str(ctx.get("runtime_epoch") or "")
    if explicit == RUNTIME_EPOCH_UNIVERSAL_V2:
        return EpochDecision(
            runtime_epoch=RUNTIME_EPOCH_UNIVERSAL_V2,
            normative=True,
            route="UNIVERSAL_V2",
            legacy_runtime_entry_forbidden=True,
            legacy_fallback=False,
            lane_task_id=task_id,
            lane_branch=branch,
        ).to_dict()

    is_q0_lane = (
        str(task_id) == Q0_TASK_ID and str(branch).startswith(Q0_BRANCH_PREFIX)
    )
    if not is_q0_lane:
        raise UniversalV2EpochError(
            "UNIVERSAL_V2_LANE_UNRESOLVED",
            f"task={task_id} branch={branch}",
        )
    return EpochDecision(
        runtime_epoch=RUNTIME_EPOCH_UNIVERSAL_V2,
        normative=True,
        route="UNIVERSAL_V2",
        legacy_runtime_entry_forbidden=True,
        legacy_fallback=False,
        lane_task_id=task_id,
        lane_branch=branch,
    ).to_dict()


def route_universal_request(
    *,
    runtime_epoch: str,
    requested_gate: str,
    requested_action: str,
) -> dict[str, Any]:
    """Route one gate/action request under the UNIVERSAL_V2 epoch.

    Legacy gates (G0..G6, unqualified) are FORBIDDEN as a Universal parent
    route.  Only the namespaced Universal gates UR.G0..UR.G6 are routable.
    """
    _require(
        runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2,
        "UNIVERSAL_V2_EPOCH_REQUIRED",
        str(runtime_epoch),
    )
    gate = str(requested_gate or "")
    action = str(requested_action or "")
    if gate in UNIVERSAL_GATES:
        return {
            "outcome": "UNIVERSAL_ROUTE_ALLOWED",
            "runtime_epoch": runtime_epoch,
            "gate": gate,
            "requested_action": action,
            "legacy_route": False,
        }
    if gate in {"G0", "G1", "G2", "G3", "G4", "G5", "G6"}:
        return {
            "outcome": "LEGACY_ROUTE_FORBIDDEN",
            "runtime_epoch": runtime_epoch,
            "gate": gate,
            "requested_action": action,
            "class": "LEGACY_POLICY_CONFLICT_WITH_UNIVERSAL_V2_DEVELOPMENT",
        }
    raise UniversalV2EpochError("UNIVERSAL_GATE_UNKNOWN", gate)


def classify_legacy_g01_absence(
    *,
    runtime_epoch: str,
    legacy_artifacts_present: bool,
    universal_native_state_valid: bool,
) -> dict[str, Any]:
    """Classify absence of legacy G0/G1 task artifacts.

    Under UNIVERSAL_V2 the legacy artifact set is a compatibility projection
    only: absence is a compatibility finding/defect and NEVER blocks the
    Universal parent run.
    """
    _require(
        runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2,
        "UNIVERSAL_V2_EPOCH_REQUIRED",
    )
    if universal_native_state_valid:
        classification = "LEGACY_COMPATIBILITY_FINDING"
    else:
        classification = "LEGACY_COMPATIBILITY_DEFECT"
    return {
        "classification": classification,
        "blocks_universal_parent": False,
        "legacy_artifacts_present": bool(legacy_artifacts_present),
        "universal_native_state_valid": bool(universal_native_state_valid),
        "action": "RECORD_FINDING_AND_CONTINUE_UNIVERSAL",
    }


def replay_c91_incident(
    *,
    runtime_epoch: str,
    legacy_g01_package_present: bool,
    universal_native_state_valid: bool,
) -> dict[str, Any]:
    """Replay the C91/E52 incident under the UNIVERSAL_V2 epoch.

    The former condition ``legacy G1 package absent`` must NOT produce
    ``NEEDS_EXACT_HITL``; the Universal parent continues with a typed
    Controller NEXT.
    """
    _require(
        runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2,
        "UNIVERSAL_V2_EPOCH_REQUIRED",
    )
    classification = classify_legacy_g01_absence(
        runtime_epoch=runtime_epoch,
        legacy_artifacts_present=legacy_g01_package_present,
        universal_native_state_valid=universal_native_state_valid,
    )["classification"]
    return {
        "outcome": "UNIVERSAL_CONTINUES",
        "runtime_epoch": runtime_epoch,
        "reason_codes": [
            "UNIVERSAL_V2_NORMATIVE",
            "LEGACY_G01_COMPATIBILITY_FINDING",
        ],
        "classification": classification,
        "first_state_beyond_failure": "UR.G1_TYPED_CONTROLLER_NEXT",
        "advance_beyond_old_failure": True,
        "controller_next": "CONTINUE_AUTONOMOUS_SELF_REMEDIATION",
        "needs_exact_hitl": False,
    }


def control_loop_verdict(
    *,
    runtime_epoch: str,
    blocker: str,
) -> dict[str, Any]:
    """Controller-liveness verdict for a blocker/WAIT token.

    ``WAIT``/``HOLD`` and legacy blocker vocabulary NEVER mean
    ``control_loop_continue = False`` under UNIVERSAL_V2.
    """
    _require(
        runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2,
        "UNIVERSAL_V2_EPOCH_REQUIRED",
    )
    token = str(blocker or "").upper()
    return {
        "runtime_epoch": runtime_epoch,
        "blocker": blocker,
        "control_loop_continue": True,
        "never_generic_stop": token in {"WAIT", "HOLD", "WAIT_CONTROLLER", "WAIT_HUMAN"},
        "effect_hold_only": token in {"HARD_AUTHORITY_BOUNDARY", "HOLD"},
    }


def classify_cursor_update(
    *,
    runtime_epoch: str,
    cursor_source: str,
    proposed_gate: str,
) -> dict[str, Any]:
    """Refuse legacy NEXT as a Universal cursor mover.

    Only a typed Universal Controller NEXT may advance the Universal cursor.
    """
    _require(
        runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2,
        "UNIVERSAL_V2_EPOCH_REQUIRED",
    )
    if str(cursor_source).startswith("LEGACY"):
        return {
            "cursor_moved": False,
            "reason_code": "LEGACY_NEXT_CANNOT_ADVANCE_UNIVERSAL_CURSOR",
            "proposed_gate": proposed_gate,
        }
    return {
        "cursor_moved": True,
        "reason_code": "UNIVERSAL_TYPED_NEXT",
        "proposed_gate": proposed_gate,
    }


def effect_hold_does_not_stop_control_loop(
    *,
    effect_hold: bool,
    control_loop_continue: bool,
) -> dict[str, Any]:
    """Enforce ``EFFECT_HOLD != CONTROL_LOOP_STOP``.

    A prohibited effect may be held while the Controller continues all safe
    Controller-owned work.
    """
    invariant = bool(control_loop_continue)
    return {
        "invariant": invariant,
        "effect_hold": bool(effect_hold),
        "control_loop_continue": bool(control_loop_continue),
        "stop_only_prohibited_effect": invariant,
    }


def classify_blocker(*, kind: str) -> dict[str, Any]:
    """Deterministic blocker classification and controller response."""
    key = str(kind).upper()
    if key not in BLOCKER_CLASSES:
        raise UniversalV2EpochError("BLOCKER_CLASS_UNKNOWN", key)
    if key == "SELF_REMEDIABLE":
        return {
            "class": key, "action": "CONTINUE_AUTONOMOUS",
            "requires_human": False, "legacy_fallback": False, "owner": "CONTROLLER",
        }
    if key == "MISSING_TECHNICAL_ARTIFACT":
        return {
            "class": key, "action": "SELF_REMEDIATE",
            "requires_human": False, "legacy_fallback": False, "owner": "CONTROLLER",
        }
    if key == "MISSING_RUNTIME_COMPONENT":
        return {
            "class": key, "action": "GWC_RUNTIME_DEFECT_SELF_REPAIR",
            "requires_human": False, "legacy_fallback": False, "owner": "CONTROLLER",
        }
    if key == "VALIDATION_FAILURE":
        return {
            "class": key, "action": "DIAGNOSE_FIX_RERUN",
            "requires_human": False, "legacy_fallback": False, "owner": "CONTROLLER",
        }
    if key == "LEGACY_POLICY_CONFLICT":
        return {
            "class": key, "action": "FIX_BRANCH_LOCAL_POLICY_ENTRY_POINT",
            "requires_human": False, "legacy_fallback": False, "owner": "CONTROLLER",
        }
    if key == "TRUE_HUMAN_DECISION":
        return {
            "class": key, "action": "REQUEST_HUMAN",
            "requires_human": True, "legacy_fallback": False, "owner": "HUMAN",
        }
    # HARD_AUTHORITY_BOUNDARY
    return {
        "class": key, "action": "HOLD_EFFECT_ONLY",
        "requires_human": True, "legacy_fallback": False, "owner": "HUMAN",
    }


def guard_executor_readonly_confirm(
    *,
    runtime_epoch: str,
    next_action: str,
    work_is_effect: bool,
) -> dict[str, Any]:
    """Forbid Controller->Executor read-only confirmation dispatch.

    Executor work requires an actual effect-bearing typed NEXT; read-only
    confirmation round-trips are Controller-owned.
    """
    _require(
        runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2,
        "UNIVERSAL_V2_EPOCH_REQUIRED",
    )
    if not work_is_effect:
        return {
            "permitted": False,
            "reason_code": "CONTROLLER_READONLY_PINGPONG_FORBIDDEN",
            "next_action": next_action,
        }
    return {
        "permitted": True,
        "reason_code": "EFFECT_BEARING_TYPED_NEXT",
        "next_action": next_action,
    }


def classify_wait_tick(
    *,
    runtime_epoch: str,
    fingerprint: str,
    controller_next: str,
) -> dict[str, Any]:
    """Repeated WAIT ticks are idempotent and generate no Executor traffic."""
    _require(
        runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2,
        "UNIVERSAL_V2_EPOCH_REQUIRED",
    )
    return {
        "runtime_epoch": runtime_epoch,
        "fingerprint": str(fingerprint),
        "controller_next": str(controller_next),
        "idempotent": True,
        "generated_executor_traffic": False,
        "control_loop_continue": True,
    }


def assess_q0_lineage(
    *,
    run_id: str,
    defect: str | None = None,
) -> dict[str, Any]:
    """Enforce ONE Q0 run -> ONE branch -> ONE canonical worktree.

    Defect identity is metadata on the same lineage; it never creates a new
    branch or worktree.
    """
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID")
    return {
        "run_id": run_id,
        "defect": defect or "",
        "branch": Q0_CANONICAL_BRANCH,
        "worktree": Q0_CANONICAL_WORKTREE,
        "single_lineage": True,
        "new_branch_prohibited": True,
        "new_worktree_prohibited": True,
    }


def assert_additive_commit(
    *,
    evidence_sha: str,
    new_sha: str,
) -> dict[str, Any]:
    """Corrections are additive immutable commits — never amend/force-push.

    Pure semantic guard: once a SHA is referenced as (replay/readback)
    evidence it is immutable; any correction must be a NEW commit on top.
    """
    _require(isinstance(evidence_sha, str) and len(evidence_sha) == 40, "SHA_INVALID")
    _require(isinstance(new_sha, str) and len(new_sha) == 40, "SHA_INVALID")
    _require(evidence_sha != new_sha, "CORRECTION_MUST_ADD_COMMIT")
    return {
        "additive": True,
        "correction_commit_allowed": True,
        "amend_forbidden": True,
        "rebase_forbidden": True,
        "force_push_forbidden": True,
        "evidence_sha": evidence_sha,
        "new_sha": new_sha,
    }


__all__ = [
    "BLOCKER_CLASSES",
    "Q0_CANONICAL_BRANCH",
    "Q0_CANONICAL_WORKTREE",
    "RUNTIME_EPOCH_LEGACY",
    "RUNTIME_EPOCH_UNIVERSAL_V2",
    "UNIVERSAL_GATES",
    "UniversalV2EpochError",
    "assert_additive_commit",
    "assess_q0_lineage",
    "classify_blocker",
    "classify_cursor_update",
    "classify_legacy_g01_absence",
    "classify_wait_tick",
    "control_loop_verdict",
    "effect_hold_does_not_stop_control_loop",
    "guard_executor_readonly_confirm",
    "replay_c91_incident",
    "resolve_runtime_epoch",
    "route_universal_request",
]
