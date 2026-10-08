from __future__ import annotations

import copy
import hashlib
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
from taskcontroller.interaction.continuation import (
    CONTINUATION_MANIFEST_KIND,
    ControllerContinuation,
    WAIT_EXECUTOR_EVENT_ACTION,
    recover_continuation,
)
from taskcontroller.interaction.github_continuation_store import GitHubContinuationStore
from taskcontroller.interaction.github_mailbox_v2 import GitHubMailboxRepository
from taskcontroller.interaction.github_rest_transport import GitHubRestIssueCommentTransport
from taskcontroller.interaction.mailbox_v2 import canonical_digest
from taskcontroller.runtime.high_integrity_session import (
    materialize_controller_transition,
    recover_high_integrity_session,
    validate_materialization_request,
)

REPO="nhatnguyenquang1838-coder/gwc"
ISSUE=575
RUN_ID="scrum781-q0-20260920T074727Z"
CTRL_MBX=f"github://{REPO}/issues/{ISSUE}#scrum781-controller-v2-e9"
EXEC_MBX=f"github://{REPO}/issues/{ISSUE}#scrum781-executor-v2-e5"
EXECUTOR="20260923_175734_bea63d"
TC_SHA="75404cfeb57f6742b60f9136aeeefd41c66b5eef"
MAIN_SHA="414002f92d48083e7133236346b26e3a2a047e33"
HEAD_REF="fix/SCRUM-781-q0-canonical"
HEAD_SHA="f6fd4121e492b61e8e0781614cd4b627d99ad979"
PREVIOUS_EVENT_COMMENT=6058084320
APPROVAL_COMMENT=6057838708
APPROVAL_ID="g2_scrum-781_c64c274d9125d76e"
APPROVAL_DIGEST="sha256:fd29642c379b82489fd985c000ce8eb743cb670bc298fdf7097da6f4fdae3b10"
SCOPE_HASH="sha256:4e98635e0fe78961fe96b0194eebdbcdca9a90f1ff55cec186dc17f69936681f"
EXPIRES_AT="2026-10-08T14:24:04Z"

token=os.environ["GITHUB_TOKEN"]

def gh(path:str):
    req=urllib.request.Request(
        "https://api.github.com"+path,
        headers={
            "Authorization":f"Bearer {token}",
            "Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
            "User-Agent":"scrum781-event-driven-redispatch",
        },
    )
    with urllib.request.urlopen(req,timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

owner,repo=REPO.split("/",1)
main=gh(f"/repos/{owner}/{repo}/git/ref/heads/main")["object"]["sha"]
head=gh(f"/repos/{owner}/{repo}/git/ref/heads/{urllib.parse.quote(HEAD_REF,safe='')}")["object"]["sha"]
if main!=MAIN_SHA or head!=HEAD_SHA:
    raise SystemExit(f"BINDING_DRIFT main={main} head={head}")

approval_body=gh(f"/repos/{owner}/{repo}/issues/comments/{APPROVAL_COMMENT}")["body"]
for expected in (APPROVAL_ID,APPROVAL_DIGEST,SCOPE_HASH,MAIN_SHA,HEAD_SHA,EXPIRES_AT):
    if expected not in approval_body:
        raise SystemExit(f"APPROVAL_READBACK_INVALID missing={expected}")

now=datetime.now(timezone.utc).replace(microsecond=0)
expiry=datetime.fromisoformat(EXPIRES_AT.replace("Z","+00:00"))
if not now<expiry:
    raise SystemExit(f"APPROVAL_EXPIRED now={now.isoformat()} expiry={EXPIRES_AT}")
now_text=now.isoformat().replace("+00:00","Z")

transport=GitHubRestIssueCommentTransport(token)
repository=GitHubMailboxRepository(transport)
store=GitHubContinuationStore(transport,repository=REPO,issue_number=ISSUE)
previous=recover_continuation(store,RUN_ID)
if previous is None:
    raise SystemExit("CONTINUATION_MISSING")
expected_state={
    "controller_epoch":9,
    "controller_seq":2,
    "phase":"WAIT_EXECUTOR",
    "next_action":"POLL_EXECUTOR",
    "controller_mailbox_ref":CTRL_MBX,
    "executor_mailbox_ref":EXEC_MBX,
    "executor_actor":EXECUTOR,
    "expected_executor_seq":2,
    "last_seen_executor_seq":1,
    "exact_head_sha":HEAD_SHA,
}
for key,expected in expected_state.items():
    actual=getattr(previous,key)
    if actual!=expected:
        raise SystemExit(f"CONTINUATION_DRIFT {key}={actual!r} expected={expected!r}")

previous_record=json.loads(gh(f"/repos/{owner}/{repo}/issues/comments/{PREVIOUS_EVENT_COMMENT}")["body"])
old=previous_record["payload"]["envelope"]
if old["seq"]!=2 or old["payload"].get("approval",{}).get("approval_request_id")!=APPROVAL_ID:
    raise SystemExit("PREVIOUS_EXECUTE_EVENT_BINDING_INVALID")
if old["payload"].get("execution_authority_active") is not True:
    raise SystemExit("PREVIOUS_EXECUTE_EVENT_NOT_AUTHORIZED")

checkpoint=ControllerContinuation(
    run_id=RUN_ID,
    controller_epoch=9,
    phase="WAIT_EXECUTOR",
    status="ACTIVE",
    next_action=WAIT_EXECUTOR_EVENT_ACTION,
    controller_mailbox_ref=CTRL_MBX,
    controller_seq=3,
    executor_actor=EXECUTOR,
    executor_mailbox_ref=EXEC_MBX,
    expected_executor_seq=2,
    last_seen_executor_seq=1,
    wakeup_binding="mailbox-event",
    exact_head_sha=HEAD_SHA,
    updated_at=now_text,
    human_root_ref=f"github://{REPO}/issues/{ISSUE}",
)

source_specs=[
    ("dw-superapps","nhatnguyenquang1838-coder/DW-SuperApps",TC_SHA,"controllers/taskcontroller.yaml"),
    ("dw-superapps","nhatnguyenquang1838-coder/DW-SuperApps",TC_SHA,"taskcontroller/controlplane/orchestration_policy.py"),
    ("dw-superapps","nhatnguyenquang1838-coder/DW-SuperApps",TC_SHA,"taskcontroller/runtime/high_integrity_session.py"),
    ("dw-superapps","nhatnguyenquang1838-coder/DW-SuperApps",TC_SHA,"taskcontroller/interaction/continuation.py"),
    ("dw-superapps","nhatnguyenquang1838-coder/DW-SuperApps",TC_SHA,"taskcontroller/interaction/github_mailbox_v2.py"),
    ("canonical-gwc",REPO,HEAD_SHA,"AGENTS.md"),
]
sources=[]
for root,source_repo,commit_sha,rel in source_specs:
    raw=(Path(root)/rel).read_bytes()
    sources.append({
        "repository":source_repo,
        "commit_sha":commit_sha,
        "path":rel,
        "blob_digest":"sha256:"+hashlib.sha256(raw).hexdigest(),
    })
sources.sort(key=lambda x:(x["repository"],x["commit_sha"],x["path"],x["blob_digest"]))
source_digest=canonical_digest({
    "manifest_version":"dw-source-manifest-json/v1",
    "runtime_ref":f"nhatnguyenquang1838-coder/DW-SuperApps@{TC_SHA}",
    "sources":sources,
})

logical=old["logical_contract"]
scope=copy.deepcopy(logical["scope"])
boundary_digest=canonical_digest({
    "run_id":RUN_ID,
    "gate":"G2_EXECUTION",
    "mode":"EXECUTE",
    "delivery":"AWAIT_EXECUTOR_EVENT",
    "scope_hash":SCOPE_HASH,
    "scope":scope,
    "approval_request_id":APPROVAL_ID,
    "base_sha":MAIN_SHA,
    "head_sha":HEAD_SHA,
    "runtime_sha":TC_SHA,
})
contract_id="scrum781-q0-v2-e9-t1-t7-execute-event"
contract_digest=canonical_digest({
    "contract_id":contract_id,
    "plan_version":logical["plan_version"],
    "boundary_digest":boundary_digest,
    "source_digest":source_digest,
    "approval_digest":APPROVAL_DIGEST,
    "execution_plan_ref":old["payload"]["execution_plan_ref"],
    "work_packages":old["payload"]["work_packages"],
    "delivery":"AWAIT_EXECUTOR_EVENT",
})

payload=copy.deepcopy(old["payload"])
for key in (
    "objective","acceptance_criteria","source_refs","evidence_refs",
    "environment_requirements","authority_constraints","contract_id",
    "source_manifest_ref","standards_profile_ref","recipient_capability",
    "agent_instance","checkpoint_id","execution_id",
):
    payload.pop(key,None)
payload.update({
    "controller_contract_mode":"EXECUTE",
    "execution_authority_active":True,
    "authority_source":"USER_EXPLICIT_CURRENT_TURN",
    "approval_ref":f"user://SCRUM-781/{APPROVAL_ID}",
    "approval_digest":APPROVAL_DIGEST,
    "disposition":"EXECUTE_RELEASED_T1_T7_EVENT_DRIVEN",
    "typed_next":"EXECUTE_T1_T7_CONTINUOUSLY_TO_UR_G3_VERIFICATION",
    "taskcontroller_runtime_ref":f"nhatnguyenquang1838-coder/DW-SuperApps@{TC_SHA}",
    "executor_wakeup_allowed":False,
    "executor_notification_mode":"mailbox-event",
    "periodic_polling_allowed":False,
    "supersedes_controller_event_ref":f"github://{REPO}/issues/{ISSUE}#issuecomment-{PREVIOUS_EVENT_COMMENT}",
})

request=BoundedMailboxRequest(
    message_id="scrum781-q0-v2-e9-t1-t7-execute-event-3",
    run_id=RUN_ID,
    node_id=old["node_id"],
    seq=3,
    correlation_id=RUN_ID,
    contract_id=contract_id,
    plan_version=logical["plan_version"],
    contract_digest=contract_digest,
    boundary_digest=boundary_digest,
    source_digest=source_digest,
    source_manifest_ref="scrum781-q0-v2-e9-t1t7-event-source-v1",
    objective=logical["objective"],
    scope=scope,
    acceptance_criteria=tuple(logical["acceptance_criteria"]),
    source_refs=tuple(sources),
    evidence_refs=(
        f"github://nhatnguyenquang1838-coder/DW-SuperApps/commit/{TC_SHA}",
        f"github://{REPO}/commit/{HEAD_SHA}",
        f"github://{REPO}/issues/{ISSUE}#issuecomment-{APPROVAL_COMMENT}",
        f"github://{REPO}/issues/{ISSUE}#issuecomment-{PREVIOUS_EVENT_COMMENT}",
        "user://current-turn/no-poll",
    ),
    standards_profile=copy.deepcopy(old["standards_profile"]),
    standards_profile_ref=logical["standards_profile_ref"],
    recipient_capability="taskcontroller.executor",
    agent_instance=EXECUTOR,
    attempt_id="scrum781-q0-v2-e9-t1-t7-attempt-event-2",
    attempt_number=5,
    lease_generation=6,
    fencing_token="scrum781-q0-v2-e9-t1-t7-fence-6",
    lease_expires_at=EXPIRES_AT,
    idempotency_key="scrum781-q0-v2-e9-t1-t7-execute-event-3",
    producer_namespace="controller",
    producer_actor_id="chatgpt-controller",
    authority_constraints={},
    payload=payload,
)

validated=validate_materialization_request(request)
contracting=validate_execution_contracting(payload=validated.payload,scope=validated.scope)
if contracting.mode!="EXECUTE" or not contracting.real_work_required:
    raise SystemExit("EXECUTION_CONTRACT_PREFLIGHT_FAILED")
preflight=compile_bounded_mailbox_request(replace(validated,checkpoint_id=checkpoint.checkpoint_id))
if preflight.seq!=3:
    raise SystemExit("PREFLIGHT_SEQ_INVALID")
if preflight.to_dict()["payload"].get("periodic_polling_allowed") is not False:
    raise SystemExit("PREFLIGHT_POLLING_NOT_DISABLED")

ledger=AuditFacade("/tmp/scrum781-e9-event-redispatch.sqlite3")
try:
    receipt=materialize_controller_transition(
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

recovered=recover_high_integrity_session(
    continuation_store=store,
    repository=repository,
    run_id=RUN_ID,
    observed_at=now_text,
)
final=recovered.checkpoint
if (final.controller_epoch,final.controller_seq,final.phase,final.next_action)!=(9,3,"WAIT_EXECUTOR",WAIT_EXECUTOR_EVENT_ACTION):
    raise SystemExit(f"EVENT_REDISPATCH_READBACK_INVALID {final.to_dict()}")
if final.wakeup_binding!="mailbox-event":
    raise SystemExit("EVENT_REDISPATCH_WAKEUP_BINDING_INVALID")
if final.expected_executor_seq!=2 or final.last_seen_executor_seq!=1:
    raise SystemExit("EVENT_REDISPATCH_EXECUTOR_SEQ_INVALID")

latest=store.latest_receipt(RUN_ID,CONTINUATION_MANIFEST_KIND)
if latest is None:
    raise SystemExit("EVENT_REDISPATCH_CONTINUATION_RECEIPT_MISSING")

print(json.dumps({
    "status":"SCRUM781_EVENT_DRIVEN_EXECUTE_DISPATCHED",
    "runtime_sha":TC_SHA,
    "controller_seq":3,
    "next_action":WAIT_EXECUTOR_EVENT_ACTION,
    "periodic_polling":False,
    "materialized":receipt.to_dict(),
    "final_checkpoint":final.to_dict(),
    "latest_continuation_receipt":latest.to_dict(),
},sort_keys=True))
