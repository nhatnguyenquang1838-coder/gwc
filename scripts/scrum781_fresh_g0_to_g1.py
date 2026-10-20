#!/usr/bin/env python3
"""Advance fresh SCRUM-781 native GWC UR.G0 to UR.G1 without Executor admission.

G0 is Controller-owned. This script checks already materialized source-bound
G0 artifacts, produces a real understanding receipt and advances the native
Universal V2 lifecycle. Does not append TaskController mailbox, create a
WAIT_EXECUTOR checkpoint, require a Hermes session or grant effects.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from tools.node_architect.q0_qualification import advance_qualification_gate, complete_q0_gate
from tools.node_architect.universal_run_controller import UniversalController
from tools.node_architect.universal_runtime_profile import load_universal_v2_default_profile

RUN = "scrum781-q0-fresh-20261010-r1"
REPO = "nhatnguyenquang1838-coder/gwc"
BRANCH = "fix/SCRUM-781-q0-fresh-20261010-r1"
SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _digest(doc: dict) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("ARTIFACT_SHAPE_INVALID")
    return value


def _write(path: Path, value: dict) -> None:
    if path.exists():
        raise ValueError("IMMUTABLE_ARTIFACT_ALREADY_EXISTS")
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if _read(path) != value:
        raise RuntimeError("ARTIFACT_EXACT_READBACK_FAILED")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)

    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=SOURCE_ROOT, text=True,
    ).strip()
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=SOURCE_ROOT, text=True,
    ).strip()
    if source_sha != args.expected_head or branch != BRANCH:
        raise RuntimeError("SOURCE_BINDING_DRIFT")

    directory = args.artifact_dir
    boot = _read(directory / "fresh-boot-evidence.json")
    plan = _read(directory / "runtime-plan.json")
    state = _read(directory / "controller-run-state.json")
    allocation = _read(directory / "node-allocation.json")
    assignment = _read(directory / "controller-assignment.json")

    if (boot.get("run_id") != RUN
            or boot.get("source_sha") != source_sha
            or boot.get("status") != "UR_G0_NATIVE_ASSIGNMENT_VERIFIED"
            or boot.get("authority_granted") is True
            or boot.get("understanding_receipt_issued") is not False
            or boot.get("taskcontroller_mailbox_event_created") is not False
            or boot.get("receipt_digest") != _digest({k: v for k, v in boot.items() if k != "receipt_digest"})):
        raise RuntimeError("G0_BOOT_RECEIPT_INVALID")
    if (plan["run_id"] != RUN
            or plan["source_binding"]["branch"] != BRANCH
            or plan["source_binding"]["pre_head_sha"] != source_sha
            or state["run_id"] != RUN
            or state["active_gate"] != "UR.G0"
            or state["sequence"] != 1
            or assignment["gate"] != "UR.G0"
            or assignment["action"] != "q0_understand"
            or assignment["actor"] != "CONTROLLER"
            or assignment["effect_authority"] != "NONE"):
        raise RuntimeError("G0_NATIVE_ASSIGNMENT_BINDING_INVALID")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    understanding_body = {
        "schema_id": "dw.scrum781.understanding-receipt/v1",
        "run_id": RUN,
        "task_id": "SCRUM-781",
        "parent": "SCRUM-780",
        "gate": "UR.G0",
        "owner": "CONTROLLER",
        "source_repository": REPO,
        "source_branch": BRANCH,
        "source_sha": source_sha,
        "runtime_plan_digest": plan["digest"],
        "q0_node": "q0.qualification-campaign",
        "objective": (
            "Qualify and repair GWC Universal V2 against original DWO login "
            "runtime failure before SCRUM-782 Login R00 execution."
        ),
        "source_refs": [
            "https://nhatnguyenquang1838.atlassian.net/browse/SCRUM-781",
            "https://github.com/nhatnguyenquang1838-coder/gwc/issues/595",
            "core/node-architect/q0-live-qualification-profile.json",
            "core/runbooks/Q0_LIVE_QUALIFICATION_RUNBOOK_v1.0.md",
        ],
        "input_evidence": {
            "g0_boot_receipt_digest": boot["receipt_digest"],
            "g0_assignment_digest": assignment["assignment_digest"],
            "node_allocation_digest": allocation["content_digest"]["value"],
        },
        "constraints": {
            "new_run_only": True,
            "historical_e9_e5_continuation_reuse": False,
            "legacy_gwc_v1_fallback": False,
            "independent_executor_admission_for_g0": False,
            "taskcontroller_mailbox_dispatch_for_g0": False,
            "protected_executor_effects_allowed": False,
        },
        "deliverable": "Create the fresh UR.G1 planning DAG and engineering acceptance criteria.",
        "status": "UNDERSTOOD",
        "created_at": now,
    }
    understanding = {**understanding_body, "receipt_digest": _digest(understanding_body)}
    verified = complete_q0_gate(
        gate="UR.G0", evidence={"UNDERSTANDING_RECEIPT": understanding},
        run_id=RUN, runtime_plan_digest=plan["digest"], candidate_sha=source_sha,
    )
    transition = advance_qualification_gate(
        current_gate="UR.G0", current_state="ACTIVE",
        evidence={"UNDERSTANDING_RECEIPT": understanding},
        sequence=1, run_id=RUN, runtime_plan_digest=plan["digest"],
        candidate_sha=source_sha,
    )
    if (verified["gate_state"] != "PASSED"
            or transition["next_gate"] != "UR.G1"
            or transition["next_state"] != "ACTIVE"):
        raise RuntimeError("G0_TO_G1_TRANSITION_INVALID")

    new_state_body = {k: v for k, v in state.items() if k != "state_digest"}
    refs = dict(new_state_body["execution_refs"])
    refs["cursor_ref"] = f"{RUN}:UR.G1:seq2"
    new_state_body.update({
        "sequence": 2, "predecessor_sequence": 1,
        "active_gate": "UR.G1",
        "execution_refs": refs,
        "gate_evidence": {"UNDERSTANDING_RECEIPT": understanding},
        "typed_next": "Q0_PLAN_DECOMPOSE",
        "next_owner": "CONTROLLER",
        "evidence_gap": ["PLAN_RECEIPT"],
    })
    new_state = {**new_state_body, "state_digest": _digest(new_state_body)}
    controller = UniversalController.from_manifest(
        profile=load_universal_v2_default_profile(),
        manifest={"runtime_plan": plan, "run_state": new_state, "node_allocation": allocation},
    )
    next_assignment = controller.assign_current_action()
    if (next_assignment["actor"] != "CONTROLLER"
            or next_assignment["action"] != "q0_plan_decompose"
            or next_assignment["gate"] != "UR.G1"
            or next_assignment["effect_authority"] != "NONE"):
        raise RuntimeError("G1_CONTROLLER_ACTION_INVALID")
    objects = {
        "g0-understanding-receipt.json": understanding,
        "g0-to-g1-transition.json": transition,
        "g1-controller-run-state.json": new_state,
        "g1-controller-assignment.json": next_assignment,
    }
    for fname, item in objects.items():
        _write(directory / fname, item)

    body = {
        "schema_id": "dw.scrum781.fresh-g0-to-g1-result/v1",
        "run_id": RUN,
        "source_sha": source_sha,
        "previous_gate": "UR.G0",
        "current_gate": "UR.G1",
        "current_action": "q0_plan_decompose",
        "actor": "CONTROLLER",
        "status": "G0_PASSED_G1_CONTROLLER_ASSIGNED",
        "understanding_receipt_digest": understanding["receipt_digest"],
        "taskcontroller_mailbox_dispatched": False,
        "executor_admission_required_for_transition": False,
        "authority_granted": False,
        "artifacts": {name: _digest(item) for name, item in objects.items()},
    }
    result = {**body, "receipt_digest": _digest(body)}
    _write(directory / "fresh-g0-to-g1-result.json", result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
