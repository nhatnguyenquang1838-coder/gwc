#!/usr/bin/env python3
"""Controller-owned G1 planning and first real, read-only Q0 mailbox/v2 dispatch.

The GitHub Actions job is the explicitly bound one-shot read-only consumer; it
does not impersonate Hermes or grant a protected effect. Never reuse legacy E9.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.interaction.continuation import ControllerContinuation
from taskcontroller.interaction.github_continuation_store import GitHubContinuationStore
from taskcontroller.interaction.github_mailbox_v2 import GitHubMailboxRepository
from taskcontroller.interaction.github_rest_transport import GitHubRestIssueCommentTransport
from taskcontroller.interaction.executor_entrypoint import V2ExecutorValidationPolicy
from taskcontroller.interaction.wakeup import WakeupSignal
from taskcontroller.runtime.high_integrity_session import (
    materialize_controller_transition, bootstrap_executor_v2,
)
from taskcontroller.interaction.mailbox_v2 import canonical_digest

from tools.node_architect.universal_run_controller import UniversalController
from tools.node_architect.universal_runtime_profile import load_universal_v2_default_profile
from tools.node_architect.q0_qualification import q0_qualification_profile

ROOT = Path(__file__).resolve().parents[1]
RUN = "scrum781-q0-fresh-20261010-r1"
BRANCH = "fix/SCRUM-781-q0-fresh-20261010-r1"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
ISSUE = 595
CONTROLLER = f"github://{REPOSITORY}/issues/{ISSUE}#{RUN}-controller-v2"
EXECUTOR = f"github://{REPOSITORY}/issues/{ISSUE}#{RUN}-executor-v2"
ACTOR = "q0-actions-readonly"


def read(directory, name):
    return json.loads((directory / name).read_text(encoding="utf-8"))


def write_once(directory, name, payload):
    target = directory / name
    if target.exists():
        raise RuntimeError("IMMUTABLE_EVIDENCE_ALREADY_EXISTS: " + name)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if read(directory, name) != payload:
        raise RuntimeError("EVIDENCE_READBACK_FAILED: " + name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Only compile+verify native G1; no remote mailbox write")
    args = parser.parse_args()

    observed = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    current_branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    if observed != args.expected_head or current_branch != BRANCH:
        raise RuntimeError("Q0_SOURCE_OR_BRANCH_DRIFT")

    evidence = args.artifact_dir
    g0 = read(evidence, "fresh-g0-to-g1-result.json")
    state = read(evidence, "g1-controller-run-state.json")
    manifest = {
        "runtime_plan": read(evidence, "runtime-plan.json"),
        "run_state": state,
        "node_allocation": read(evidence, "node-allocation.json"),
    }
    profile = load_universal_v2_default_profile()
    q0 = q0_qualification_profile()
    if (g0["status"] != "G0_PASSED_G1_CONTROLLER_ASSIGNED"
        or g0["source_sha"] != observed
        or state["active_gate"] != "UR.G1"
        or state["next_owner"] != "CONTROLLER"):
        raise RuntimeError("G1_PREDECESSOR_NOT_VERIFIED")

    controller = UniversalController.from_manifest(profile=profile, manifest=manifest)
    assignment = controller.assign_current_action()
    if (assignment["gate"] != "UR.G1" or assignment["actor"] != "CONTROLLER"
        or assignment["action"] != "q0_plan_decompose"):
        raise RuntimeError("G1_NATIVE_ASSIGNMENT_INVALID")

    # This is a material plan, not a placeholder command or fabricated execution evidence.
    plan_body = {
        "schema_id": "gwc.scrum781.q0-plan-receipt/v1",
        "run_id": RUN,
        "gate": "UR.G1",
        "action": "q0_plan_decompose",
        "controller_assignment_digest": assignment["assignment_digest"],
        "source_sha": observed,
        "runtime_plan_digest": manifest["runtime_plan"]["digest"],
        "qualification_profile_digest": q0["profile_digest"],
        "mandatory_qualification_entries": q0["mandatory_qualification_entries"],
        "sequence": [
            {"id": "Q0-P1", "depends_on": [], "action": "Verify fresh GWC profile, native source SHA and canonical actor/gate ownership"},
            {"id": "Q0-P2", "depends_on": ["Q0-P1"], "action": "Exact-read a typed Controller mailbox/v2 request and validate the fresh continuation"},
            {"id": "Q0-P3", "depends_on": ["Q0-P2"], "action": "Perform read-only Q0 qualification checks; capture gaps without inventing incident replay"},
            {"id": "Q0-P4", "depends_on": ["Q0-P3"], "action": "Only with separate authority run branch-local TDD/fixes and original-incident replay"},
            {"id": "Q0-P5", "depends_on": ["Q0-P4"], "action": "Validate G2 through G5 in target; request human G6 acceptance with complete matrix"},
        ],
        "acceptance_criteria": [
            "GWC V2 native Controller/Executor modules and profile load against exact source SHA",
            "Read-only Q0 qualification evidence is exact-bound to this run and GitHub Actions consumer",
            "Fresh Controller mailbox event/cursor/continuation exact-readback; no legacy E9/E5 reuse",
            "No protected effects, source writes, merge/deploy or authority inference in the PLAN request",
            "Original-incident replay, load proof, and G6 certification remain OPEN until observed",
        ],
        "effect_authority_granted": False,
        "executor_admission_required_for_g1": False,
    }
    plan_receipt = {**plan_body, "receipt_digest": canonical_digest(plan_body)}
    decision = controller.complete_controller_owned_gate(
        evidence={"PLAN_RECEIPT": plan_receipt}, expected_sequence=2,
        completion_metadata={"source_sha": observed, "q0_profile_digest": q0["profile_digest"]},
    )
    if (decision["next_gate"] != "UR.G2" or not decision["gate_advanced"]
        or decision["authority_granted"] or decision["executed_effects"]):
        raise RuntimeError("G1_NATIVE_TRANSITION_INVALID")
    write_once(evidence, "g1-plan-receipt.json", plan_receipt)
    write_once(evidence, "g1-native-controller-decision.json", decision)
    # Under native Q0, this successor remains Controller-owned; the bounded
    # mailbox PLAN is an auxiliary real read-only verification, not UR.G2 effect authority.
    if decision["next_owner"] != "CONTROLLER":
        raise RuntimeError("Q0_G2_OWNER_CHANGED: re-resolve dispatch contract")

    issued = datetime.now(timezone.utc)
    now = issued.isoformat(timespec="seconds")
    expires = (issued + timedelta(hours=2)).isoformat(timespec="seconds")
    path = "scripts/scrum781_fresh_q0_mailbox.py"
    source_bytes = (ROOT / path).read_bytes()
    source = {
        "repository": REPOSITORY, "commit_sha": observed, "path": path,
        "blob_digest": "sha256:" + hashlib.sha256(source_bytes).hexdigest(),
    }
    scope = {
        "allowed_actions": ["read_repo", "read_exact_source"],
        "denied_actions": ["modify_approved_files", "merge", "deploy", "production_config_change"],
        "writable_targets": [], "source_roots": ["tools/node_architect", "core/node-architect"],
        "max_children": 0, "max_parallel": 1, "max_depth": 0,
    }
    contract = {
        "run_id": RUN, "gate": "UR.G2", "kind": "read_only_qualification_probe",
        "plan_digest": plan_receipt["receipt_digest"], "actor": ACTOR, "scope": scope,
        "source_sha": observed,
    }
    contract_digest = canonical_digest(contract)
    attempt = "q0-fresh-readonly-1"
    fence = canonical_digest({"run": RUN, "sha": observed, "attempt": attempt, "plan": contract_digest})
    checkpoint = ControllerContinuation(
        run_id=RUN, controller_epoch=1, phase="WAIT_EXECUTOR", status="ACTIVE",
        next_action="AWAIT_EXECUTOR_EVENT",
        controller_mailbox_ref=CONTROLLER, controller_seq=1, executor_actor=ACTOR,
        executor_mailbox_ref=EXECUTOR, expected_executor_seq=1, last_seen_executor_seq=0,
        wakeup_binding="github-actions-same-job-event", exact_head_sha=observed, updated_at=now,
    )
    payload = {
        "message_id": "scrum781-q0-readonly-probe-r1",
        "run_id": RUN, "node_id": "SCRUM-781", "seq": 1,
        "correlation_id": RUN + "-g1-g2-readonly-probe",
        "contract_id": RUN + "-q0-plan-probe", "plan_version": "q0-g1-r1",
        "contract_digest": contract_digest,
        "boundary_digest": canonical_digest(scope),
        "source_digest": canonical_digest({"sources": [source]}),
        "source_manifest_ref": f"github://{REPOSITORY}/blob/{observed}/{path}",
        "objective": "Execute bounded read-only Q0 source/profile/route qualification on the fresh run; return gaps to Controller. No edits or authority.",
        "scope": scope, "acceptance_criteria": plan_body["acceptance_criteria"][:3],
        "source_refs": [source],
        "standards_profile": {
            "profile_id": "gwc.universal-runtime-v2-q0", "version": "2", "digest": profile["profile_digest"],
        },
        "recipient_capability": "taskcontroller.executor",
        "agent_instance": ACTOR,
        "attempt_id": attempt, "attempt_number": 1, "lease_generation": 1,
        "fencing_token": fence, "lease_expires_at": expires,
        "idempotency_key": canonical_digest({"contract": contract_digest, "seq": 1}),
        "producer_namespace": "controller",
        "producer_actor_id": "chatgpt-controller",
        "evidence_refs": [f"github://{REPOSITORY}/issues/{ISSUE}", f"github://{REPOSITORY}/actions/runs/{os.environ.get('GITHUB_RUN_ID','local')}"],
        "authority_constraints": {"denied_actions": scope["denied_actions"], "writable_targets": []},
        "payload": {
            "controller_contract_mode": "PLAN", "execution_authority_active": False,
            "q0_universal_gate": "UR.G2", "q0_probe_only": True,
            "periodic_polling_allowed": False,
            "q0_plan_receipt_digest": plan_receipt["receipt_digest"],
        },
    }

    if args.dry_run:
        from taskcontroller.runtime.high_integrity_session import validate_materialization_request
        from taskcontroller.controlplane.request_compiler import compile_bounded_mailbox_request
        env = compile_bounded_mailbox_request(validate_materialization_request(payload))
        write_once(evidence, "q0-controller-command-preview.json", env.to_dict())
        print(json.dumps({"status": "DRY_RUN_VALID", "gate": "UR.G2", "plan_receipt": plan_receipt["receipt_digest"]}))
        return 0

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN_REQUIRED_ON_CANONICAL_CONTROLLER_RUNNER")

    transport = GitHubRestIssueCommentTransport(token)
    mailbox = GitHubMailboxRepository(transport)
    store = GitHubContinuationStore(transport, repository=REPOSITORY, issue_number=ISSUE)
    if mailbox.read(CONTROLLER).events or mailbox.read(EXECUTOR).events or store.load_manifest(RUN, "dw.taskcontroller.continuation/v1"):
        raise RuntimeError("FRESH_MAILBOX_ALREADY_ACTIVE: cannot reset/overwrite or create new attempt")

    ledger = AuditFacade(evidence / "taskcontroller-q0-dispatch.sqlite3")
    try:
        result = materialize_controller_transition(
            continuation_store=store, repository=mailbox, ledger=ledger,
            checkpoint=checkpoint, request=payload, state_version=1,
            prepared_at=now, committed_at=now, actor="chatgpt-controller",
        )
    finally:
        ledger.close()
    rec = result.to_dict()
    if (rec["run_id"] != RUN or rec["authority_granted"] is not False
            or rec["continuation"]["next_action"] != "AWAIT_EXECUTOR_EVENT"):
        raise RuntimeError("CONTROLLER_DISPATCH_RECEIPT_INVALID")
    write_once(evidence, "q0-controller-mailbox-materialization.json", rec)

    # This Action job IS the declared event adapter + read-only consumer. No
    # Hermes Desktop delivery or protected Q0 implementation is claimed.
    signal = WakeupSignal(
        run_id=RUN, sender="controller", recipient=ACTOR,
        mailbox_ref=CONTROLLER, seq=rec["continuation"]["controller_seq"], updated_at=now,
    )
    receipt = bootstrap_executor_v2(
        mailbox, signal, executor_actor=ACTOR,
        validation_policy=V2ExecutorValidationPolicy(
            capability_id="taskcontroller.executor", instance_id=ACTOR,
            attempt_id=attempt, lease_generation=1, fencing_token=fence,
            last_seen_event_seq=-1,
        ),
    )
    if receipt.envelope.to_dict()["payload"]["controller_contract_mode"] != "PLAN":
        raise RuntimeError("EXECUTOR_PLAN_CONSUMPTION_MISMATCH")
    write_once(evidence, "q0-readonly-executor-boot.json", {
        "run_id": RUN, "actor": ACTOR, "mailbox_event_id": receipt.event.event_id,
        "mailbox_event_digest": receipt.event.event_digest, "consumer_cursor": receipt.cursor.to_dict(),
        "effect_authority_granted": False,
        "mode": "PLAN", "status": "EXECUTOR_Q0_READONLY_COMMAND_CONSUMED",
    })
    print(json.dumps({
        "status": "FRESH_CONTROLLER_MAILBOX_PUBLISHED_AND_CONSUMED",
        "run_id": RUN, "event": rec["remote_evidence"]["event"],
        "cursor": rec["remote_evidence"]["cursor"],
        "continuation": rec["remote_evidence"]["continuation"],
        "plan_receipt": plan_receipt["receipt_digest"],
        "authority_granted": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
