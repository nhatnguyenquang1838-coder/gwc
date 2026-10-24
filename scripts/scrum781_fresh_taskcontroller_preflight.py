#!/usr/bin/env python3
"""Verify new mailbox/v2 refs using canonical DW-SuperApps TaskController code.

Read-only: no event, cursor, continuation, lease, approval or notification writes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from taskcontroller.controlplane.controller_admission import (
    ControllerAdmissionInput,
    validate_controller_admission,
)
from taskcontroller.controlplane.execution_contracting import validate_execution_contracting
from taskcontroller.interaction.github_continuation_store import GitHubContinuationStore
from taskcontroller.interaction.github_mailbox_v2 import GitHubMailboxRepository
from taskcontroller.interaction.github_rest_transport import GitHubRestIssueCommentTransport

REPO = "nhatnguyenquang1838-coder/gwc"
ISSUE = 595
RUN = "scrum781-q0-fresh-20261010-r1"
CONTROL = f"github://{REPO}/issues/{ISSUE}#{RUN}-controller-v2"
EXECUTOR = f"github://{REPO}/issues/{ISSUE}#{RUN}-executor-v2"


def _digest(value: dict) -> str:
    b = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(b).hexdigest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--expected-gwc-head", required=True)
    p.add_argument("--taskcontroller-source-sha", required=True)
    a = p.parse_args(argv)
    evidence = json.loads(a.evidence.read_text())
    if (evidence.get("run_id") != RUN
            or evidence.get("source_sha") != a.expected_gwc_head
            or evidence.get("status") != "UR_G0_NATIVE_ASSIGNMENT_VERIFIED"
            or evidence.get("effect_authority") != "NONE"
            or evidence.get("taskcontroller_mailbox_event_created") is not False):
        raise RuntimeError("NATIVE_GWC_G0_READBACK_FAILED")
    observed = evidence.get("receipt_digest")
    if observed != _digest({k: v for k, v in evidence.items() if k != "receipt_digest"}):
        raise RuntimeError("NATIVE_GWC_G0_RECEIPT_DIGEST_INVALID")

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN_MISSING")
    transport = GitHubRestIssueCommentTransport(token)
    repo = GitHubMailboxRepository(transport)
    control = repo.read(CONTROL)
    executor = repo.read(EXECUTOR)
    store = GitHubContinuationStore(transport, repository=REPO, issue_number=ISSUE)
    manifest = store.load_manifest(RUN, "dw.taskcontroller.continuation/v1")
    if control.events or executor.events or manifest is not None:
        raise RuntimeError("FRESH_MAILBOX_NOT_EMPTY: another writer may own this run")

    admission = validate_controller_admission(
        ControllerAdmissionInput(requires_v2_semantics=True, protocol="dw.taskcontroller.mailbox/v2", mailbox_ref=CONTROL)
    )
    plan = validate_execution_contracting(
        payload={"controller_contract_mode": "PLAN", "execution_authority_active": False},
        scope={
            "allowed_actions": ["read_repo"], "denied_actions": ["modify_approved_files", "merge", "deploy"],
            "writable_targets": [],
        },
    )
    assert admission.authority_granted is False and plan.authority_granted is False
    receipt_body = {
        "schema_id": "dw.scrum781.taskcontroller-fresh-mailbox-preflight/v1",
        "run_id": RUN,
        "gwc_source_sha": a.expected_gwc_head,
        "taskcontroller_source_sha": a.taskcontroller_source_sha,
        "controller_mailbox_ref": CONTROL,
        "executor_mailbox_ref": EXECUTOR,
        "controller_last_event_seq": control.last_event_seq,
        "executor_last_event_seq": executor.last_event_seq,
        "continuation_present": False,
        "admission_mode": admission.mode,
        "contract_mode": plan.mode,
        "status": "FRESH_EMPTY_MAILBOX_VERIFIED",
        "native_stage": "UR.G0",
        "native_stage_assignment_verified": True,
        "taskcontroller_machine_transition_persisted": False,
        "executor_actor_bound": False,
        "transport_qualified": False,
        "authority_granted": False,
        "executor_wakeup_allowed": False,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    receipt = {**receipt_body, "receipt_digest": _digest(receipt_body)}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
