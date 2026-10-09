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

    existing_progress=repo.read(EXECUTOR).events
    if len(existing_progress)==1:
        prior=existing_progress[0].envelope.to_dict()
        prev_receipt=prior["payload"].get("progress_receipt",{})
        if (prior["message_type"]!="execution_progress"
            or prior["payload"].get("status")!="RUNNING"
            or prev_receipt.get("source_sha")!=ep["expected_head_sha"]
            or prev_receipt.get("q0_suite_rc")!=0
            or prev_receipt.get("candidate_sha") is None):
            raise RuntimeError("PREVIOUS_EXECUTOR_PROGRESS_NOT_VERIFIED")
        for ancestor in (ep["expected_head_sha"],prev_receipt["candidate_sha"]):
            if subprocess.run(["git","merge-base","--is-ancestor",ancestor,head],
                cwd=ROOT).returncode:
                raise RuntimeError("EXECUTOR_WORKTREE_ORIGIN_NOT_ADDITIVE")
        regression=ROOT/"tests/test_scrum781_q0_historical_replay.py"
        test_content='''"""Historical C91/E52 semantic replay is not the DWO login end-to-end certification."""
from tools.node_architect.universal_run_epoch import (
    resolve_runtime_epoch,replay_c91_incident,
)

def test_scrum781_fresh_boot_is_universal_v2_not_legacy():
    epoch=resolve_runtime_epoch(
        task_id="SCRUM-781",
        branch="fix/SCRUM-781-q0-fresh-20261010-r1",
    )
    assert epoch["runtime_epoch"]=="UNIVERSAL_V2_DEVELOPMENT"
    assert epoch["legacy_fallback"] is False

def test_c91_missing_legacy_artifacts_does_not_stop_native_controller():
    result=replay_c91_incident(
        runtime_epoch="UNIVERSAL_V2_DEVELOPMENT",
        legacy_g01_package_present=False,
        universal_native_state_valid=True,
    )
    assert result["needs_exact_hitl"] is False
    assert result["advance_beyond_old_failure"] is True
    assert result["first_state_beyond_failure"]=="UR.G1_TYPED_CONTROLLER_NEXT"
'''
        if regression.exists() and regression.read_text()!=test_content:
            raise RuntimeError("HISTORICAL_REPLAY_REGRESSION_CONFLICT")
        if not regression.exists():regression.write_text(test_content)
        import importlib
        module=importlib.import_module("tools.node_architect.universal_run_epoch")
        # Execute a real C91/E52 control-plane replay; do not mislabel it
        # as a replay of the complete DWO-LOGIN-AUTH-R1 fixture.
        scenario=module.replay_c91_incident(
            runtime_epoch="UNIVERSAL_V2_DEVELOPMENT",
            legacy_g01_package_present=False,
            universal_native_state_valid=True,
        )
        if (scenario["outcome"]!="UNIVERSAL_CONTINUES"
            or not scenario["advance_beyond_old_failure"]):
            raise RuntimeError("HISTORICAL_C91_REPLAY_FAILED")
        focused=run(sys.executable,"-m","pytest","-q",
            "tests/test_scrum781_q0_historical_replay.py",
            "tests/test_universal_run_epoch_v2.py")
        suites=run(sys.executable,"-m","pytest","-q",*TESTS)
        if focused.returncode or suites.returncode:
            raise RuntimeError("HISTORICAL_REPLAY_REGRESSION_FAILED")
        run("git","add",str(regression.relative_to(ROOT)),check=True)
        if run("git","diff","--cached","--quiet").returncode:
            raise RuntimeError("EXPECTED_NEW_REPLAY_REGRESSION_NOT_ADDED")
        run("git","config","user.name","github-actions[bot]",check=True)
        run("git","config","user.email","41898282+github-actions[bot]@users.noreply.github.com",check=True)
        run("git","commit","-m","test(q0): replay historical C91 controller deadlock under Universal V2",check=True)
        run("git","push","origin",f"HEAD:refs/heads/{BRANCH}",check=True)
        advanced=run("git","rev-parse","HEAD",check=True).stdout.strip()
        evidence={
            "schema_id":"gwc.scrum781.q0-semantic-replay-progress/v1",
            "run_id":RUN,
            "loaded_source_sha":head,
            "candidate_sha":advanced,
            "runtime_process_id":str(os.getpid()),
            "runtime_session_id":os.environ.get("GITHUB_RUN_ID"),
            "loaded_module_sha256":digest_file(Path(module.__file__)),
            "loaded_instruction_sha256":digest_file(ROOT/"AGENTS.md"),
            "historical_scenario":"C91/E52_missing_legacy_G0_G1",
            "historical_replay_result":scenario,
            "focused_suite_exit":focused.returncode,
            "q0_suite_exit":suites.returncode,
            "replay_fixture_limit":"C91/E52 semantic projection only; complete original DWO-LOGIN-AUTH-R1 replay still OPEN",
            "status":"IN_PROGRESS",
            "remaining":["DWO_ORIGINAL_INCIDENT_EXACT_FIXTURE","DWO_ORIGINAL_INCIDENT_REPLAY","Q0_FULL_LIVE_QUALIFICATION","GWC_L3_CERTIFICATION","DRAFT_PR"],
        }
        evidence["receipt_digest"]=canonical_digest(evidence)
        reply=payload.copy()
        reply.update({
            "message_id":"scrum781-q0-executor-progress-r2-phase2",
            "seq":2,
            "direction":"executor_to_controller",
            "message_type":"execution_progress",
            "producer":{"namespace":"executor","actor_id":ACTOR,"role":"executor"},
            "recipient":{"capability":"taskcontroller.controller","agent_instance":"controller"},
            "payload":{"status":"RUNNING","report_type":"mission_status",
                "typed_next":"CONTINUE_Q0_ORIGINAL_DWO_INCIDENT_REPLAY",
                "semantic_replay_evidence":evidence,"plan_mode":"EXECUTE"},
            "provenance":{"origin":"executor","parent_message_id":payload["message_id"],
                "child_id":None,"lens":"historical-control-plane-replay",
                "agent_instance":ACTOR,"status":"RUNNING",
                "source_refs":[f"github://{REPO}/commit/{advanced}"],
                "evidence_refs":[f"github://{REPO}/issues/{ISSUE}"],
                "result_digest":None},
            "idempotency_key":canonical_digest({"run":RUN,"phase":2,"receipt":evidence["receipt_digest"]})
        })
        reply["digest"]=canonical_digest(reply)
        observed=repo.write(EXECUTOR,repo.read(EXECUTOR).last_event_seq,V2MailboxEnvelope.from_dict(reply))
        repo.exact_readback(observed)
        folder=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"scrum781-q0-engineering"
        folder.mkdir(parents=True,exist_ok=True)
        (folder/"historical-c91-replay.json").write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\\n")
        print(json.dumps({"status":"EXECUTOR_HISTORICAL_REPLAY_AND_PROGRESS2_DONE",
            "commit":advanced,"event_id":observed.event_id,
            "receipt":evidence["receipt_digest"],"original_dwo_replay":"OPEN"},sort_keys=True))
        return 0
    if len(existing_progress)>1:
        print(json.dumps({"status":"EXECUTOR_PROGRESS_ALREADY_EMITTED",
            "run_id":RUN,"executor_progress_events":len(existing_progress)}))
        return 0

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
