#!/usr/bin/env python3
"""Execute Q0 WIP engineering from an actual v2 EXECUTE event, no legacy lease reuse.

First bounded engineering increment: run Q0 regression suite, add real
regression guard for accidental downgrade to PLAN, GREEN, commit/push in same
Q0 branch. Emit typed in-progress Executor mailbox event; never claim L3/G6.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from taskcontroller.interaction.github_mailbox_v2 import GitHubMailboxRepository
from taskcontroller.interaction.github_rest_transport import GitHubRestIssueCommentTransport
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest
from taskcontroller.interaction.wakeup import WakeupSignal
from taskcontroller.interaction.executor_entrypoint import V2ExecutorValidationPolicy
from taskcontroller.runtime.high_integrity_session import bootstrap_executor_v2

REPO="nhatnguyenquang1838-coder/gwc"
ISSUE=595
RUN="scrum781-q0-fresh-20261010-r1"
BRANCH="fix/SCRUM-781-q0-fresh-20261010-r1"
ACTOR="q0-actions-engineering"
CONTROL=f"github://{REPO}/issues/{ISSUE}#{RUN}-controller-v2"
EXECUTOR=f"github://{REPO}/issues/{ISSUE}#{RUN}-executor-v2"
ROOT=Path(__file__).resolve().parents[1]
REGRESSION=ROOT/"tests/test_scrum781_q0_execution_contract.py"
TESTS=[
"tests/test_q0_live_qualification_contract.py",
"tests/test_q0_universal_qualification.py",
"tests/test_universal_run_epoch_v2.py",
"tests/test_universal_v2_core_isolation.py",
"tests/test_universal_run_execution.py",
"tests/test_universal_run_authority_v1.py",
]

def run(*cmd,check=False):
    r=subprocess.run(cmd,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    print(r.stdout[-12000:])
    if check and r.returncode:
        raise RuntimeError("SUBPROCESS_FAILED:"+str(cmd[:4]))
    return r

def digest_file(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    token=os.environ.get("GITHUB_TOKEN")
    if not token:raise RuntimeError("MISSING_GITHUB_TOKEN")
    repo=GitHubMailboxRepository(GitHubRestIssueCommentTransport(token))
    snap=repo.read(CONTROL)
    if len(snap.events)!=3 or snap.last_event_seq!=2:
        raise RuntimeError("EXECUTE_MAILBOX_EVENT_NOT_NEWEST")
    event=snap.events[2]
    payload=event.envelope.to_dict()
    ep=payload["payload"]
    if (payload["seq"]!=3 or ep.get("controller_contract_mode")!="EXECUTE"
        or not ep.get("execution_authority_active")
        or ep.get("merge_deploy_production_allowed") is not False
        or ep.get("periodic_polling_allowed") is not False
        or payload["recipient"]["agent_instance"]!=ACTOR):
        raise RuntimeError("EXECUTE_EVENT_SCOPE_INVALID")

    head=run("git","rev-parse","HEAD",check=True).stdout.strip()
    branch=run("git","branch","--show-current",check=True).stdout.strip()
    if head!=ep["expected_head_sha"] or branch!=BRANCH:
        raise RuntimeError("GUARDED_EXECUTOR_SOURCE_HEAD_DRIFT")
    if "tests/**" not in payload["logical_contract"]["scope"]["writable_targets"]:
        raise RuntimeError("REGRESSION_TARGET_NOT_AUTHORIZED")
    signal=WakeupSignal(
        run_id=RUN,sender="controller",recipient=ACTOR,mailbox_ref=CONTROL,
        seq=3,updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    consumed=bootstrap_executor_v2(
        repo,signal,executor_actor=ACTOR,
        validation_policy=V2ExecutorValidationPolicy(
            capability_id="taskcontroller.executor",instance_id=ACTOR,
            attempt_id="scrum781-q0-execute-attempt3",lease_generation=3,
            fencing_token=payload["execution_identity"]["fencing_token"],
            last_seen_event_seq=1),
    )
    if consumed.event.event_id!=event.event_id:
        raise RuntimeError("EXECUTOR_EVENT_READBACK_DRIFT")
    # Focused regression: catch unexpected downgrade of the frozen Q0 plan.
    code='''"""SCRUM-781: executable Q0 contract cannot silently regress into read-only PLAN."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
def test_q0_execution_plan_stays_executable_and_scoped():
    d=json.loads((ROOT/"core/node-architect/scrum781-q0-fresh-execution-plan-r2.json").read_text())
    assert d["contract_mode"]=="EXECUTE"
    assert d["scope"]["writable_targets"]
    assert "modify_approved_files" in d["scope"]["allowed_actions"]
    assert "run_sandboxed_validation" in d["scope"]["allowed_actions"]
    assert "merge_approved_pr" in d["scope"]["denied_actions"]
    assert "deploy_approved_release" in d["scope"]["denied_actions"]
    assert len(d["work_packages"])>=5
    assert "ALL_ACCEPTANCE_CRITERIA_PASS" in d["continue_until"]

def test_q0_recursive_g1_has_atomic_leaves():
    d=json.loads((ROOT/"core/node-architect/scrum781-q0-fresh-execution-plan-r2.json").read_text())
    def visit(node):
        kids=node.get("children",[])
        if node.get("atomic"): assert not kids; return 1
        assert kids
        return sum(visit(k) for k in kids)
    assert visit(d["recursive_plan"])>=6
'''
    if REGRESSION.exists() and REGRESSION.read_text()!=code:
        raise RuntimeError("REGRESSION_TEST_ALREADY_EXISTS_WITH_DIFFERENT_CONTENT")
    if not REGRESSION.exists(): REGRESSION.write_text(code)
    focused=run(sys.executable,"-m","pytest","-q",str(REGRESSION.relative_to(ROOT)))
    suites=run(sys.executable,"-m","pytest","-q",*TESTS)
    if focused.returncode or suites.returncode:
        raise RuntimeError("Q0_TDD_FOCUSED_OR_BASELINE_FAILED_NEEDS_BRANCH_LOCAL_REPAIR")

    run("git","add",str(REGRESSION.relative_to(ROOT)),check=True)
    changed=run("git","diff","--cached","--quiet")
    if changed.returncode!=0:
        run("git","config","user.name","github-actions[bot]",check=True)
        run("git","config","user.email","41898282+github-actions[bot]@users.noreply.github.com",check=True)
        run("git","commit","-m","test(q0): protect executable continuous remediation contract from PLAN downgrade",check=True)
        # Never rewrite history and never modify a different branch.
        run("git","push","origin",f"HEAD:refs/heads/{BRANCH}",check=True)
    new_sha=run("git","rev-parse","HEAD",check=True).stdout.strip()
    receipt={
        "schema_id":"gwc.scrum781.q0-engineering-progress.v1",
        "run_id":RUN,"source_sha":head,"candidate_sha":new_sha,
        "generated_regression":str(REGRESSION.relative_to(ROOT)),
        "regression_sha256":digest_file(REGRESSION),
        "focused_rc":focused.returncode,"q0_suite_rc":suites.returncode,
        "work_packages_started":["P1","P2"],
        "complete":False,
        "remaining":["ORIGINAL_INCIDENT_REPRODUCTION","RED_REGRESSION","RUNTIME_FIX_RELOAD","ORIGINAL_INCIDENT_REPLAY","L3_CERTIFICATION","DRAFT_PR"],
        "status":"IN_PROGRESS","effect_ceiling":"branch_local_additive_write",
    }
    receipt["receipt_digest"]=canonical_digest(receipt)

    # Only a real Executor progress event, not a fabricated Q0 EXECUTION_RECEIPT.
    response=payload.copy()
    response.update({
        "message_id":"scrum781-q0-executor-progress-r2",
        "seq":1,
        "direction":"executor_to_controller",
        "message_type":"execution_progress",
        "producer":{"namespace":"executor","actor_id":ACTOR,"role":"executor"},
        "recipient":{"capability":"taskcontroller.controller","agent_instance":"controller"},
        "payload":{
            "status":"RUNNING","report_type":"mission_status",
            "typed_next":"CONTINUE_Q0_IMPLEMENTATION",
            "progress_receipt":receipt,
            "plan_mode":"EXECUTE",
        },
        "provenance":{
            "origin":"executor","parent_message_id":payload["message_id"],
            "child_id":None,"lens":"q0-tdd-execution",
            "agent_instance":ACTOR,"status":"RUNNING",
            "source_refs":[f"github://{REPO}/commit/{new_sha}"],
            "evidence_refs":[f"github://{REPO}/issues/{ISSUE}"],
            "result_digest":None,
        },
        "idempotency_key":canonical_digest({"run":RUN,"correlation_id":payload["correlation_id"],"seq":1,"new_sha":new_sha})
    })
    response["digest"]=canonical_digest(response)
    envelope=V2MailboxEnvelope.from_dict(response)
    remote=repo.write(EXECUTOR,repo.read(EXECUTOR).last_event_seq,envelope)
    snapshot=repo.exact_readback(remote)
    if len(snapshot.events)!=1:raise RuntimeError("EXECUTOR_PROGRESS_READBACK_INVALID")
    folder=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"scrum781-q0-engineering"
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"engineering-progress.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    (folder/"executor-progress-event.json").write_text(json.dumps(envelope.to_dict(),indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":"EXECUTOR_WP1_ACTUAL_WORK_AND_EVENT_COMPLETE",
        "run_id":RUN,"commit":new_sha,"source_sha":head,
        "event_id":remote.event_id,"progress_receipt":receipt["receipt_digest"],
        "remaining":receipt["remaining"],"auto_merge":False},sort_keys=True))
    return 0

if __name__=="__main__":sys.exit(main())
