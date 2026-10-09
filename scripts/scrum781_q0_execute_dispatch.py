#!/usr/bin/env python3
"""Native TaskController correction: replace read-only Q0 plan with authorized EXECUTE.

One Controller writer / run, append-only new continuation and v2 event. The
standing SCRUM-781 Q0 development policy permits branch-local TDD/fix/replay;
it does not authorize merge, deploy, production or G6 human acceptance.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.controlplane.execution_contracting import validate_execution_contracting
from taskcontroller.controlplane.request_compiler import compile_bounded_mailbox_request
from taskcontroller.interaction.continuation import ControllerContinuation, recover_continuation
from taskcontroller.interaction.github_continuation_store import GitHubContinuationStore
from taskcontroller.interaction.github_mailbox_v2 import GitHubMailboxRepository
from taskcontroller.interaction.github_rest_transport import GitHubRestIssueCommentTransport
from taskcontroller.interaction.mailbox_v2 import canonical_digest
from taskcontroller.runtime.high_integrity_session import materialize_controller_transition, validate_materialization_request

REPO = "nhatnguyenquang1838-coder/gwc"
ISSUE = 595
RUN = "scrum781-q0-fresh-20261010-r1"
BRANCH = "fix/SCRUM-781-q0-fresh-20261010-r1"
ACTOR = "q0-actions-engineering"
CONTROL = f"github://{REPO}/issues/{ISSUE}#{RUN}-controller-v2"
EXECUTOR = f"github://{REPO}/issues/{ISSUE}#{RUN}-executor-v2"
ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "core/node-architect/scrum781-q0-fresh-execution-plan-r2.json"

def fail(msg):
    raise RuntimeError(msg)

def exact_write(folder: Path, filename: str, data: dict) -> None:
    dest = folder / filename
    if dest.exists():
        if json.loads(dest.read_text()) != data:
            fail("IMMUTABLE_ARTIFACT_CONFLICT:" + filename)
        return
    dest.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    if json.loads(dest.read_text()) != data:
        fail("LOCAL_READBACK_INVALID:" + filename)

def main():
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    if branch != BRANCH or len(sha) != 40:
        fail("SOURCE_BRANCH_OR_SHA_DRIFT")
    plan = json.loads(PLAN_PATH.read_text())
    if (plan["run_id"] != RUN or plan["current_gate"] != "UR.G2"
        or plan["contract_mode"] != "EXECUTE" or plan["branch"] != BRANCH
        or plan["scope"]["max_children"] != 0):
        fail("FROZEN_Q0_EXECUTION_PLAN_INVALID")
    if len(plan["work_packages"]) < 5 or len(plan["continue_until"]) < 2:
        fail("PLAN_WORK_PACKAGES_OR_CONTINUATION_INVALID")

    # Match existing standing authority verbatim: no Controller self-grant.
    policy = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    policy_section = policy.split("## UNIVERSAL_V2_DEVELOPMENT override — SCRUM-781 Q0 development lane",1)[1].split("## Agent-specific routing",1)[0]
    normalized_policy = " ".join(policy_section.split())
    for required in (
        "Self-remediable Q0 defects", "same Q0", "no per-defect Human approval",
        "no merge/auto-merge", "no deployment", "no credentials/secrets",
    ):
        if required not in normalized_policy:
            fail("STANDING_Q0_AUTHORITY_POLICY_DRIFT:" + required)
    policy_digest = "sha256:" + hashlib.sha256(policy_section.encode()).hexdigest()
    plan_digest = "sha256:" + hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest()
    scope = plan["scope"]
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat(timespec="seconds")
    expires = (now + timedelta(hours=6)).isoformat(timespec="seconds")
    source_path = "core/node-architect/scrum781-q0-fresh-execution-plan-r2.json"
    source = {
        "repository": REPO, "commit_sha": sha, "path": source_path,
        "blob_digest": "sha256:" + hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest(),
    }
    command_payload = {
        "controller_contract_mode": "EXECUTE",
        "execution_authority_active": True,
        "execution_plan_ref": f"github://{REPO}/blob/{sha}/{source_path}",
        "approval_ref": f"github://{REPO}/blob/{sha}/AGENTS.md#UNIVERSAL_V2_DEVELOPMENT",
        "approval_digest": policy_digest,
        "standing_authority_basis": "Q0 autonomous branch-local TDD/repair, not new self-granted authority",
        "work_packages": plan["work_packages"],
        "continue_until": plan["continue_until"],
        "stop_conditions": plan["stop_conditions"],
        "branch": BRANCH, "expected_head_sha": sha,
        "worktree": "worktrees/gwc/SCRUM-781-q0-fresh-20261010-r1",
        "q0_runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
        "q0_gate": "UR.G2",
        "plan_digest": plan_digest,
        "previous_mailbox_event_ref": f"github://{REPO}/issues/{ISSUE}#issuecomment-6087891914",
        "supersedes_previous_readonly_probe": True,
        "periodic_polling_allowed": False,
        "tdd_repair_loop": "RED→FIX→GREEN→RELOAD→REPLAY→READBACK→BROADER_REGRESSION",
        "draft_pr_allowed": True,
        "merge_deploy_production_allowed": False,
    }

    receipt = validate_execution_contracting(payload=command_payload, scope=scope)
    if receipt.mode != "EXECUTE" or not receipt.real_work_required or receipt.authority_granted:
        fail("EXECUTE_CONTRACT_VALIDATION_NOT_SUFFICIENT")
    # Force policy/profile validation BEFORE any remote machine mutation.
    for action in ("merge_approved_pr","deploy_approved_release","force_push","credential_rotation","migration"):
        if action in scope["allowed_actions"]:
            fail("SEPARATE_AUTHORITY_EFFECT_UNSAFE")
    contract_identity = {"run":RUN,"sha":sha,"plan_digest":plan_digest,
                         "approval_digest":policy_digest,"scope":scope}
    contract_digest = canonical_digest(contract_identity)
    fence = canonical_digest({"run":RUN,"attempt":2,"contract":contract_digest})
    request = {
        "message_id":"scrum781-q0-execute-correction-r2",
        "run_id":RUN,"node_id":"SCRUM-781","seq":2,
        "correlation_id":RUN+"-q0-execute-r2",
        "contract_id":RUN+"-q0-execute","plan_version":"q0-g1-r2",
        "contract_digest":contract_digest,
        "boundary_digest":canonical_digest(scope),
        "source_digest":canonical_digest({"sources":[source]}),
        "source_manifest_ref":"gwc.scrum781.q0-execute-source-r2",
        "objective":"Execute full Q0 GWC runtime remediation/certification end-to-end on the same development branch. Continue through RED/GREEN, fixes, reload, replay, regressions, additive push, Draft PR.",
        "scope":scope,"acceptance_criteria":plan["acceptance_criteria"],
        "source_refs":[source],
        "standards_profile":{"profile_id":"gwc.q0-autonomous-development","version":"2","digest":policy_digest},
        "standards_profile_ref":"gwc.q0-autonomous-development/v2",
        "recipient_capability":"taskcontroller.executor",
        "agent_instance":ACTOR,
        "attempt_id":"scrum781-q0-execute-attempt2","attempt_number":2,"lease_generation":2,
        "fencing_token":fence,"lease_expires_at":expires,
        "idempotency_key":canonical_digest({"run":RUN,"seq":2,"contract_digest":contract_digest}),
        "producer_namespace":"controller","producer_actor_id":"chatgpt-controller",
        "evidence_refs":[f"github://{REPO}/issues/{ISSUE}","jira://SCRUM-781","jira://SCRUM-787","jira://SCRUM-796"],
        "authority_constraints":{"denied_actions":scope["denied_actions"],"writable_targets":scope["writable_targets"]},
        "payload":command_payload,
    }
    bound = validate_materialization_request(request)
    envelope = compile_bounded_mailbox_request(bound)
    if envelope.to_dict()["payload"]["controller_contract_mode"] != "EXECUTE":
        fail("EXECUTE_ENVELOPE_MODE_DRIFT")

    folder = Path(os.environ.get("RUNNER_TEMP","/tmp")) / "scrum781-q0-execute-r2"
    folder.mkdir(parents=True,exist_ok=True)
    exact_write(folder,"execution-plan.json",plan)
    exact_write(folder,"execute-controller-command-preview.json",envelope.to_dict())
    exact_write(folder,"execution-policy-binding.json",{
        "run_id":RUN,"repo":REPO,"source_sha":sha,"plan_digest":plan_digest,
        "standing_policy_digest":policy_digest,"contract_validation":receipt.to_dict(),
        "authority_basis_ref":command_payload["approval_ref"],
        "effect_ceiling":"branch-local-dev-and-draft-pr","separate_authority_required":plan["authority_basis"]["separate_authority_required"],
    })
    if os.environ.get("Q0_EXECUTE_DRY_RUN")=="1":
        print(json.dumps({"result":"EXECUTE_CONTRACT_DRY_RUN_PASS","contract":receipt.to_dict(),
                          "source_sha":sha,"plan_digest":plan_digest},sort_keys=True))
        return 0

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        fail("GITHUB_TOKEN_REQUIRED")
    transport = GitHubRestIssueCommentTransport(token)
    mailbox = GitHubMailboxRepository(transport)
    store = GitHubContinuationStore(transport,repository=REPO,issue_number=ISSUE)
    prev = recover_continuation(store,RUN)
    events = mailbox.read(CONTROL).events
    if (prev is None or prev.controller_seq != 1
        or prev.executor_actor != "q0-actions-readonly"
        or len(events)!=1 or events[0].logical_seq != 1
        or events[0].envelope.to_dict()["payload"].get("controller_contract_mode") != "PLAN"
        or mailbox.read(EXECUTOR).events):
        fail("PREDECESSOR_EVENT_DRIFT_OR_CONCURRENT_EXECUTION")
    checkpoint=ControllerContinuation(
        run_id=RUN,controller_epoch=2,phase="WAIT_EXECUTOR",status="ACTIVE",
        next_action="AWAIT_EXECUTOR_EVENT",controller_mailbox_ref=CONTROL,
        controller_seq=2,executor_actor=ACTOR,executor_mailbox_ref=EXECUTOR,
        expected_executor_seq=1,last_seen_executor_seq=0,
        wakeup_binding="github-actions-q0-engineering-consumer",
        exact_head_sha=sha,updated_at=timestamp,
    )
    ledger=AuditFacade(folder / "dispatch-ledger.sqlite3")
    try:
        result=materialize_controller_transition(
            continuation_store=store,repository=mailbox,ledger=ledger,
            checkpoint=checkpoint,request=request,state_version=2,
            prepared_at=timestamp,committed_at=timestamp,actor="chatgpt-controller",
        )
    finally:
        ledger.close()
    data=result.to_dict()
    exact_write(folder,"execute-mailbox-materialization.json",data)
    if (data["continuation"]["controller_seq"]!=2
        or data["authority_granted"] is not False
        or mailbox.read(CONTROL).last_event_seq!=1
        or data["envelope_digest"]!=envelope.digest()):
        fail("EXECUTE_EVENT_EXACT_READBACK_INVALID")
    print(json.dumps({"result":"EXECUTE_COMMAND_MATERIALIZED",
        "run_id":RUN,"source_sha":sha,
        "plan_digest":plan_digest,
        "contract_mode":"EXECUTE",
        "remote_evidence":data["remote_evidence"],
        "effective_scope":scope,
        "authority_grant_source":"standing-Q0-policy (validated); transport grants none",
        "executor_delivery":"not yet signaled",
    },sort_keys=True))
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({"error":str(exc),"details":getattr(exc,"errors",None)},default=str))
        raise
