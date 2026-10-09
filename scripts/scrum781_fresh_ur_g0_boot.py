#!/usr/bin/env python3
"""SCRUM-781 fresh UR.G0 boot: use native GWC V2 source, never old mailbox state.

This boot is Controller-side/read-only with respect to protected remote effects.
It materializes immutable local evidence for the brand-new run. It does not
claim UNDERSTANDING_RECEIPT, mark UR.G0 completed, or grant Executor authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

import jsonschema

from tools.node_architect.universal_run_controller import UniversalController
from tools.node_architect.universal_run_kernel import initial_run_state, seal_immutable_record
from tools.node_architect.universal_run_topology import (
    create_node_allocation,
    create_run_manifest_revision,
)
from tools.node_architect.universal_runtime_profile import load_universal_v2_default_profile
from tools.node_architect.q0_qualification import q0_qualification_profile

RUN = "scrum781-q0-fresh-20261010-r1"
NODE = "q0.qualification-campaign"
BRANCH = "fix/SCRUM-781-q0-fresh-20261010-r1"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "414002f92d48083e7133236346b26e3a2a047e33"
ISSUE = 595
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ROOT = Path(__file__).resolve().parents[1]


def _digest(value: dict) -> str:
    b = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(b).hexdigest()


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _schema_validate(record: dict, name: str) -> None:
    path = ROOT / "schemas/node-architect/universal-run" / name
    jsonschema.validate(record, json.loads(path.read_text(encoding="utf-8")))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)

    observed_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
    ).strip()
    actual_branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True,
    ).strip()
    if not SHA40.fullmatch(observed_sha) or observed_sha != args.expected_head:
        raise RuntimeError("SOURCE_HEAD_DRIFT: no boot evidence can be issued")
    if actual_branch != BRANCH:
        raise RuntimeError(f"SOURCE_BRANCH_DRIFT: {actual_branch!r}")

    profile = load_universal_v2_default_profile()
    q0 = q0_qualification_profile()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    actor = {"profile": "taskcontroller-controller", "mode": "fresh_ur_g0_boot"}
    root_id = f"RM-{RUN}-r1"
    allocation_id = f"{RUN}:{NODE}:r1"
    allocation_record_id = f"NA-{RUN}-r1"
    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    manifest = create_run_manifest_revision(
        record_id=root_id, run_id=RUN, revision=1, run_kind="ROOT",
        created_at=now, created_by=actor,
        source_refs=[f"github://{REPO}/issues/{ISSUE}", BRANCH, observed_sha],
    )
    allocation = create_node_allocation(
        record_id=allocation_record_id, run_id=RUN,
        node_allocation_id=allocation_id, kind="WORK",
        requirement="REQUIRED", created_at=now, created_by=actor,
        source_refs=[NODE],
    )
    _schema_validate(manifest, "run-manifest-revision.schema.json")
    _schema_validate(allocation, "node-allocation.schema.json")

    plan_body = {
        "schema_id": "gwc.universal-run.runtime-plan.v2",
        "schema_version": 2,
        "run_id": RUN,
        "revision": 1,
        "target_contract_ref": f"github://{REPO}/issues/{ISSUE}",
        "node_allocations": [allocation_id],
        "runtime_epoch": profile["runtime_epoch"],
        "runtime_profile_ref": "core/node-architect/universal-runtime-default-profile.json",
        "runtime_default_profile_digest": profile["profile_digest"],
        "qualification_profile_ref": "core/node-architect/q0-live-qualification-profile.json",
        "qualification_profile_digest": q0["profile_digest"],
        "previous_digest": None,
        "source_binding": {
            "repository": REPO,
            "branch": BRANCH,
            "pre_head_sha": observed_sha,
        },
    }
    plan = {**plan_body, "digest": _digest(plan_body)}
    allocation_ref = f"native://{RUN}/node-allocation.json#record_id={allocation_record_id}"
    cursor_ref = f"{RUN}:UR.G0:seq1"

    state_body = {
        "schema_id": "gwc.universal-run.run-state.v2",
        "schema_version": 2,
        "run_id": RUN,
        "sequence": 1,
        "predecessor_sequence": 0,
        "active_gate": "UR.G0",
        "runtime_epoch": profile["runtime_epoch"],
        "execution_refs": {
            "branch": BRANCH,
            "node_allocation_id": allocation_id,
            "node_allocation_ref": allocation_ref,
            "base_sha": BASE,
            "candidate_sha": observed_sha,
            "qualification_profile_digest": q0["profile_digest"],
            "runtime_plan_digest": plan["digest"],
            "cursor_ref": cursor_ref,
        },
        "gate_evidence": {},
        "typed_next": "Q0_UNDERSTAND",
        "next_owner": "CONTROLLER",
        "evidence_gap": ["UNDERSTANDING_RECEIPT"],
        "consumed_receipts": [],
    }
    state = {**state_body, "state_digest": _digest(state_body)}

    native = UniversalController.from_manifest(
        profile=profile,
        manifest={"runtime_plan": plan, "run_state": state, "node_allocation": allocation},
    )
    assignment = native.assign_current_action()
    if (assignment["run_id"] != RUN or assignment["gate"] != "UR.G0"
            or assignment["action"] != "q0_understand"
            or assignment["actor"] != "CONTROLLER"
            or assignment["effect_authority"] != "NONE"):
        raise RuntimeError("NATIVE_UR_G0_ASSIGNMENT_INVALID")

    initial = initial_run_state(profile["lifecycle_profile"])
    logical_body = {
        "record_id": f"RS-{RUN}-seq1",
        "schema_id": "gwc.universal-run.run-state-record.v2",
        "schema_version": 2,
        "run_id": RUN,
        "created_at": now,
        "created_by": actor,
        "lifecycle_profile": profile["lifecycle_profile"],
        "provenance": {
            "predecessor_refs": [],
            "source_refs": [f"github://{REPO}/issues/{ISSUE}", observed_sha],
        },
        "run_manifest_ref": f"native://{RUN}/run-manifest.json#record_id={root_id}",
        "run_manifest_digest": manifest["content_digest"]["value"],
        "state_revision": 1,
        "predecessor_state_ref": None,
        "predecessor_state_digest": None,
        "sequence": 1,
        "active_gate": "UR.G0",
        "gate_states": initial["gate_states"],
        "terminal_state": initial["terminal_state"],
        "execution_refs": {
            "runtime_plan_ref": f"native://{RUN}/runtime-plan.json",
            "runtime_plan_digest": plan["digest"],
            "cursor_ref": cursor_ref,
        },
        "future_contract_refs": [],
    }
    logical_state = seal_immutable_record(logical_body)
    _schema_validate(logical_state, "run-state-record.schema.json")

    objects = {
        "run-manifest.json": manifest,
        "node-allocation.json": allocation,
        "runtime-plan.json": plan,
        "controller-run-state.json": state,
        "logical-run-state.json": logical_state,
        "controller-assignment.json": assignment,
    }
    for fname, value in objects.items():
        _write(output / fname, value)

    receipt_body = {
        "schema_id": "dw.scrum781.fresh-ur-g0-boot-evidence/v1",
        "run_id": RUN,
        "stage": "UR.G0",
        "native_action": assignment["action"],
        "source_repository": REPO,
        "source_branch": BRANCH,
        "source_sha": observed_sha,
        "taskcontroller_boot_issue": ISSUE,
        "controller_actor": "CONTROLLER",
        "effect_authority": "NONE",
        "status": "UR_G0_NATIVE_ASSIGNMENT_VERIFIED",
        "understanding_receipt_issued": False,
        "taskcontroller_mailbox_event_created": False,
        "executor_wakeup_allowed": False,
        "artifacts": {f: _digest(v) for f, v in objects.items()},
        "timestamp": now,
    }
    receipt = {**receipt_body, "receipt_digest": _digest(receipt_body)}
    _write(output / "fresh-boot-evidence.json", receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
