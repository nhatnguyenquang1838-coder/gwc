from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import urllib.parse
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.controlplane.execution_contracting import validate_execution_contracting
from taskcontroller.controlplane.request_compiler import BoundedMailboxRequest, compile_bounded_mailbox_request
from taskcontroller.interaction.continuation import CONTINUATION_MANIFEST_KIND, ControllerContinuation, recover_continuation
from taskcontroller.interaction.github_continuation_store import GitHubContinuationStore
from taskcontroller.interaction.github_mailbox_v2 import GitHubMailboxRepository
from taskcontroller.interaction.github_rest_transport import GitHubRestIssueCommentTransport
from taskcontroller.interaction.mailbox_v2 import canonical_digest
from taskcontroller.runtime.high_integrity_session import (
    materialize_controller_transition,
    recover_high_integrity_session,
    validate_materialization_request,
)

REPO = "nhatnguyenquang1838-coder/gwc"
ISSUE = 575
RUN_ID = "scrum781-q0-20260920T074727Z"
CTRL_MBX = f"github://{REPO}/issues/{ISSUE}#scrum781-controller-v2-e9"
EXEC_MBX = f"github://{REPO}/issues/{ISSUE}#scrum781-executor-v2-e5"
EXECUTOR = "20260923_175734_bea63d"
TC_SHA = "8663779c62ca00340c257af92e66e2b616e9154a"
MAIN_SHA = "414002f92d48083e7133236346b26e3a2a047e33"
HEAD_REF = "fix/SCRUM-781-q0-canonical"
HEAD_SHA = "f6fd4121e492b61e8e0781614cd4b627d99ad979"
E8_COMMENT = 6044604052
APPROVAL_COMMENT = 6057838708
APPROVAL_ID = "g2_scrum-781_c64c274d9125d76e"
APPROVAL_DIGEST = "sha256:fd29642c379b82489fd985c000ce8eb743cb670bc298fdf7097da6f4fdae3b10"
APPROVAL_SHA = "59712a23e343dd336f50f76078b22e5995a61bb6de1851cef9ae217927c5027a"
SCOPE_HASH = "sha256:4e98635e0fe78961fe96b0194eebdbcdca9a90f1ff55cec186dc17f69936681f"
USER_COMMAND = "APPROVE G2 g2_scrum-781_c64c274d9125d76e 4e98635e0fe78961 2026-10-08T14:24:04Z"
ISSUED_AT = "2026-10-08T10:24:04Z"
EXPIRES_AT = "2026-10-08T14:24:04Z"

token = os.environ["GITHUB_TOKEN"]

def gh(path: str):
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "scrum781-controller-dispatch",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

owner, repo = REPO.split("/", 1)
main = gh(f"/repos/{owner}/{repo}/git/ref/heads/main")["object"]["sha"]
head = gh(f"/repos/{owner}/{repo}/git/ref/heads/{urllib.parse.quote(HEAD_REF, safe='')}")["object"]["sha"]
if main != MAIN_SHA or head != HEAD_SHA:
    raise SystemExit(f"AUTHORITY_BINDING_DRIFT main={main} head={head}")

approval_body = gh(f"/repos/{owner}/{repo}/issues/comments/{APPROVAL_COMMENT}")["body"]
for expected in (APPROVAL_ID, APPROVAL_DIGEST, APPROVAL_SHA, SCOPE_HASH, MAIN_SHA, HEAD_SHA, USER_COMMAND):
    if expected not in approval_body:
        raise SystemExit(f"APPROVAL_REQUEST_READBACK_INVALID missing={expected}")

spec = importlib.util.spec_from_file_location(
    "approval_token_generation",
    Path("canonical-gwc/tools/node_architect/approval_token_generation.py"),
)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
approval_request = module.generate_approval_request(
    task_id="SCRUM-781",
    repository=REPO,
    gate="G2_EXECUTION",
    action="modify_approved_files",
    scope_identity={
        "scope_hash": SCOPE_HASH,
        "base_sha": MAIN_SHA,
        "head_sha": HEAD_SHA,
        "branch": HEAD_REF,
        "pr_number": None,
        "environment": None,
    },
    authority_boundary_decision={"decision": "REQUIRE_APPROVAL", "requested_action": "modify_approved_files"},
    actor_target={"type": "user", "id": "USER", "display_name": "Human Approver"},
    issued_at=ISSUED_AT,
    expires_at=EXPIRES_AT,
)
if approval_request["approval_request_id"] != APPROVAL_ID:
    raise SystemExit("APPROVAL_ID_MISMATCH")
if approval_request["request_digest"] != APPROVAL_DIGEST:
    raise SystemExit("APPROVAL_DIGEST_MISMATCH")
if approval_request["approval_command"] != USER_COMMAND:
    raise SystemExit("APPROVAL_COMMAND_MISMATCH")

now = datetime.now(timezone.utc).replace(microsecond=0)
issued = datetime.fromisoformat(ISSUED_AT.replace("Z", "+00:00"))
expiry = datetime.fromisoformat(EXPIRES_AT.replace("Z", "+00:00"))
if not (issued <= now < expiry):
    raise SystemExit(f"APPROVAL_EXPIRED now={now.isoformat()} expiry={EXPIRES_AT}")
now_text = now.isoformat().replace("+00:00", "Z")

transport = GitHubRestIssueCommentTransport(token)
repository = GitHubMailboxRepository(transport)
store = GitHubContinuationStore(transport, repository=REPO, issue_number=ISSUE)
previous = recover_continuation(store, RUN_ID)
if previous is None:
    raise SystemExit("CONTINUATION_MISSING")
expected_state = {
    "controller_epoch": 9,
    "controller_seq": 1,
    "phase": "WAIT_CONTROLLER",
    "next_action": "RESOLVE_EXECUTION_AUTHORITY",
    "controller_mailbox_ref": CTRL_MBX,
    "executor_mailbox_ref": EXEC_MBX,
    "executor_actor": EXECUTOR,
    "expected_executor_seq": 2,
    "last_seen_executor_seq": 1,
    "exact_head_sha": HEAD_SHA,
}
for key, expected in expected_state.items():
    actual = getattr(previous, key)
    if actual != expected:
        raise SystemExit(f"CONTINUATION_DRIFT {key}={actual!r} expected={expected!r}")

e8 = json.loads(gh(f"/repos/{owner}/{repo}/issues/comments/{E8_COMMENT}")["body"])["payload"]["envelope"]
old_contract = e8["logical_contract"]
old_payload = e8["payload"]

checkpoint = ControllerContinuation(
    run_id=RUN_ID,
    controller_epoch=9,
    phase="WAIT_EXECUTOR",
    status="ACTIVE",
    next_action="POLL_EXECUTOR",
    controller_mailbox_ref=CTRL_MBX,
    controller_seq=2,
    executor_actor=EXECUTOR,
    executor_mailbox_ref=EXEC_MBX,
    expected_executor_seq=2,
    last_seen_executor_seq=1,
    wakeup_binding="mailbox-v2-only",
    exact_head_sha=HEAD_SHA,
    updated_at=now_text,
    human_root_ref=f"github://{REPO}/issues/{ISSUE}",
)

source_specs = [
    ("dw-superapps", "nhatnguyenquang1838-coder/DW-SuperApps", TC_SHA, "controllers/taskcontroller.yaml"),
    ("dw-superapps", "nhatnguyenquang1838-coder/DW-SuperApps", TC_SHA, "taskcontroller/controlplane/orchestration_policy.py"),
    ("dw-superapps", "nhatnguyenquang1838-coder/DW-SuperApps", TC_SHA, "taskcontroller/runtime/high_integrity_session.py"),
    ("dw-superapps", "nhatnguyenquang1838-coder/DW-SuperApps", TC_SHA, "taskcontroller/interaction/github_mailbox_v2.py"),
    ("canonical-gwc", REPO, HEAD_SHA, "AGENTS.md"),
]
sources = []
for root, source_repo, commit_sha, rel in source_specs:
    raw = (Path(root) / rel).read_bytes()
    sources.append({
        "repository": source_repo,
        "commit_sha": commit_sha,
        "path": rel,
        "blob_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
    })
sources.sort(key=lambda x: (x["repository"], x["commit_sha"], x["path"], x["blob_digest"]))
source_digest = canonical_digest({
    "manifest_version": "dw-source-manifest-json/v1",
    "runtime_ref": f"nhatnguyenquang1838-coder/DW-SuperApps@{TC_SHA}",
    "sources": sources,
})

scope = copy.deepcopy(old_contract["scope"])
boundary_digest = canonical_digest({
    "run_id": RUN_ID,
    "gate": "G2_EXECUTION",
    "mode": "EXECUTE",
    "scope_hash": SCOPE_HASH,
    "scope": scope,
    "approval_request_id": APPROVAL_ID,
    "base_sha": MAIN_SHA,
    "head_sha": HEAD_SHA,
    "runtime_sha": TC_SHA,
})
contract_id = "scrum781-q0-v2-e9-t1-t7-execute"
contract_digest = canonical_digest({
    "contract_id": contract_id,
    "plan_version": old_contract["plan_version"],
    "boundary_digest": boundary_digest,
    "source_digest": source_digest,
    "approval_digest": APPROVAL_DIGEST,
    "execution_plan_ref": old_payload["execution_plan_ref"],
    "work_packages": old_payload["work_packages"],
})

approval = copy.deepcopy(old_payload["approval"])
approval.pop("protocol", None)
approval.update({
    "approval_request_id": APPROVAL_ID,
    "approval_request_digest": APPROVAL_DIGEST,
    "approval_request_sha256": APPROVAL_SHA,
    "approved_scope_hash": SCOPE_HASH,
    "scope_hash_short": "4e98635e0fe78961",
    "base_sha": MAIN_SHA,
    "head_sha": HEAD_SHA,
    "issued_at": ISSUED_AT,
    "expires_at": EXPIRES_AT,
    "release_text": USER_COMMAND,
    "approval_command": USER_COMMAND,
    "consumed": True,
    "request_comment_ref": f"github://{REPO}/issues/{ISSUE}#issuecomment-{APPROVAL_COMMENT}",
})

payload = {
    "controller_contract_mode": "EXECUTE",
    "execution_authority_active": True,
    "authority_source": "USER_EXPLICIT_CURRENT_TURN",
    "execution_plan_ref": old_payload["execution_plan_ref"],
    "approval_ref": f"user://SCRUM-781/{APPROVAL_ID}",
    "approval_digest": APPROVAL_DIGEST,
    "approval": approval,
    "disposition": "EXECUTE_RELEASED_T1_T7_FROM_E9_FRESH_AUTHORITY",
    "typed_next": "EXECUTE_T1_T7_CONTINUOUSLY_TO_UR_G3_VERIFICATION",
    "taskcontroller_runtime_ref": f"nhatnguyenquang1838-coder/DW-SuperApps@{TC_SHA}",
    "work_packages": copy.deepcopy(old_payload["work_packages"]),
    "continue_until": copy.deepcopy(old_payload["continue_until"]),
    "stop_conditions": copy.deepcopy(old_payload["stop_conditions"]),
    "non_stop_conditions": copy.deepcopy(old_payload["non_stop_conditions"]),
    "still_denied": copy.deepcopy(old_payload["still_denied"]),
    "integration_ceiling": old_payload["integration_ceiling"],
    "excluded_paths": copy.deepcopy(old_payload["excluded_paths"]),
    "exact_base": {"repository": REPO, "ref": HEAD_REF, "sha": HEAD_SHA},
    "preserved_state": copy.deepcopy(old_payload["preserved_state"]),
    "reconciliation_evidence": {
        "source_binding": "EXACT_REMOTE_REFS",
        "main_base": MAIN_SHA,
        "branch": HEAD_REF,
        "remote_head": HEAD_SHA,
        "worktree_clean": "EXECUTOR_MUST_VERIFY",
    },
    "completion_report": {
        **{
            key: value
            for key, value in copy.deepcopy(old_payload["completion_report"]).items()
            if key != "mailbox_ref"
        },
        "mailbox_target_ref": EXEC_MBX,
    },
    "executor_wakeup_allowed": True,
}

request = BoundedMailboxRequest(
    message_id="scrum781-q0-v2-e9-t1-t7-execute-2",
    run_id=RUN_ID,
    node_id="SCRUM-781-Q0-UR-G2-EXECUTE",
    seq=2,
    correlation_id=RUN_ID,
    contract_id=contract_id,
    plan_version=old_contract["plan_version"],
    contract_digest=contract_digest,
    boundary_digest=boundary_digest,
    source_digest=source_digest,
    source_manifest_ref="scrum781-q0-v2-e9-t1t7-source-v1",
    objective=old_contract["objective"],
    scope=scope,
    acceptance_criteria=tuple(old_contract["acceptance_criteria"]),
    source_refs=tuple(sources),
    evidence_refs=(
        f"github://nhatnguyenquang1838-coder/DW-SuperApps/commit/{TC_SHA}",
        f"github://{REPO}/commit/{HEAD_SHA}",
        f"github://{REPO}/issues/{ISSUE}#issuecomment-{APPROVAL_COMMENT}",
        f"github://{REPO}/issues/{ISSUE}#issuecomment-6057366880",
        f"github://{REPO}/issues/{ISSUE}#issuecomment-6057373722",
        "user://current-turn/APPROVE-G2",
    ),
    standards_profile=copy.deepcopy(e8["standards_profile"]),
    standards_profile_ref=old_contract["standards_profile_ref"],
    recipient_capability="taskcontroller.executor",
    agent_instance=EXECUTOR,
    attempt_id="scrum781-q0-v2-e9-t1-t7-attempt-1",
    attempt_number=4,
    lease_generation=5,
    fencing_token="scrum781-q0-v2-e9-t1-t7-fence-5",
    lease_expires_at=EXPIRES_AT,
    idempotency_key="scrum781-q0-v2-e9-t1-t7-execute-2",
    producer_namespace="controller",
    producer_actor_id="chatgpt-controller",
    authority_constraints={},
    payload=payload,
)

validated = validate_materialization_request(request)
receipt = validate_execution_contracting(payload=validated.payload, scope=validated.scope)
if receipt.mode != "EXECUTE" or not receipt.real_work_required:
    raise SystemExit("EXECUTION_CONTRACT_PREFLIGHT_FAILED")
preflight = compile_bounded_mailbox_request(replace(validated, checkpoint_id=checkpoint.checkpoint_id))
if preflight.seq != 2 or not preflight.to_dict()["payload"]["execution_authority_active"]:
    raise SystemExit("EXECUTION_PREFLIGHT_INVALID")

ledger = AuditFacade("/tmp/scrum781-e9-g2-execute.sqlite3")
try:
    materialized = materialize_controller_transition(
        continuation_store=store,
        repository=repository,
        ledger=ledger,
        checkpoint=checkpoint,
        request=request,
        state_version=0,
        prepared_at=now_text,
        committed_at=now_text,
    )
finally:
    ledger.close()

recovered = recover_high_integrity_session(
    continuation_store=store,
    repository=repository,
    run_id=RUN_ID,
    observed_at=now_text,
)
final = recovered.checkpoint
if (final.controller_epoch, final.controller_seq, final.phase, final.next_action) != (9, 2, "WAIT_EXECUTOR", "POLL_EXECUTOR"):
    raise SystemExit(f"EXECUTE_READBACK_INVALID {final.to_dict()}")
if final.expected_executor_seq != 2 or final.last_seen_executor_seq != 1 or final.exact_head_sha != HEAD_SHA:
    raise SystemExit("EXECUTE_READBACK_BINDING_INVALID")

latest = store.latest_receipt(RUN_ID, CONTINUATION_MANIFEST_KIND)
if latest is None:
    raise SystemExit("CONTINUATION_RECEIPT_MISSING")

print(json.dumps({
    "status": "SCRUM781_G2_EXECUTE_DISPATCHED",
    "approval_request_id": APPROVAL_ID,
    "approval_consumed": True,
    "runtime_sha": TC_SHA,
    "materialized": materialized.to_dict(),
    "final_checkpoint": final.to_dict(),
    "latest_continuation_receipt": latest.to_dict(),
}, sort_keys=True))
