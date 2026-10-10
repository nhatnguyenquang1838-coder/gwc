#!/usr/bin/env python3
"""Controller-owned stale-lease recovery for fresh SCRUM-781; never dispatch.

Uses current DW-SuperApps native recovery, not hand-authored state. Records
exact GitHub body hashes separately from semantic digests. Fail closed on
unexpected actor/run/cursor/head changes; #575 is not a state input.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

from taskcontroller.interaction.continuation import recover_continuation
from taskcontroller.interaction.github_continuation_store import GitHubContinuationStore
from taskcontroller.interaction.github_mailbox_v2 import GitHubMailboxRepository
from taskcontroller.interaction.github_rest_transport import GitHubRestIssueCommentTransport
from taskcontroller.runtime.high_integrity_session import recover_high_integrity_session

RUN="scrum781-q0-fresh-20261010-r1"
REPO="nhatnguyenquang1838-coder/gwc"
ISSUE=595
CONTROLLER=f"github://{REPO}/issues/{ISSUE}#{RUN}-controller-v2"
EXECUTOR=f"github://{REPO}/issues/{ISSUE}#{RUN}-executor-v2"
ROOT=Path(__file__).resolve().parents[1]
BRANCH="fix/SCRUM-781-q0-fresh-20261010-r1"
FOCAL_IDS=(6088465716,6088466150,6088599848,6088613896,6088614320)

def _sha(data: str) -> str:
    return "sha256:"+hashlib.sha256(data.encode("utf-8")).hexdigest()

def _format_comment(comment):
    obj=json.loads(comment.body)
    detail={"comment_id":int(comment.comment_id),
        "url":f"https://github.com/{REPO}/issues/{ISSUE}#issuecomment-{comment.comment_id}",
        "raw_body_sha256":_sha(comment.body),
        "record_digest":obj.get("digest"),
        "kind":obj.get("record_type") or obj.get("manifest_kind"),
    }
    if obj.get("record_type")=="event":
        detail.update({
            "logical_seq":obj["payload"]["logical_seq"],
            "event_id":obj["payload"]["event_id"],
            "envelope_digest":obj["payload"]["envelope_digest"],
            "message_type":obj["payload"]["envelope"]["message_type"],
            "direction":obj["payload"]["envelope"]["direction"],
        })
    elif obj.get("record_type")=="cursor":
        detail.update({
            "last_event_seq":obj["payload"]["last_event_seq"],
            "last_logical_seq":obj["payload"]["last_logical_seq"],
        })
    elif obj.get("manifest_kind")=="dw.taskcontroller.continuation/v1":
        detail.update({
            "record_seq":obj["record_seq"],
            "metadata":obj["manifest"]["metadata"],
        })
    return detail

def main():
    head=subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()
    branch=subprocess.check_output(["git","branch","--show-current"],text=True,cwd=ROOT).strip()
    if branch!=BRANCH:
        raise RuntimeError("ACTIVE_Q0_BRANCH_DRIFT")
    token=os.environ.get("GITHUB_TOKEN")
    if not token:raise RuntimeError("GITHUB_TOKEN_REQUIRED")

    transport=GitHubRestIssueCommentTransport(token)
    mailbox=GitHubMailboxRepository(transport)
    store=GitHubContinuationStore(transport,repository=REPO,issue_number=ISSUE)
    checkpoint=recover_continuation(store,RUN)
    ctr=mailbox.read(CONTROLLER)
    exe=mailbox.read(EXECUTOR)
    if (checkpoint is None or checkpoint.controller_seq!=3
        or checkpoint.executor_actor!="q0-actions-engineering"
        or checkpoint.executor_mailbox_ref!=EXECUTOR
        or checkpoint.controller_mailbox_ref!=CONTROLLER
        or checkpoint.expected_executor_seq!=3
        or checkpoint.last_seen_executor_seq!=2
        or len(ctr.events)!=3 or len(exe.events)!=2
        or ctr.events[-1].envelope.to_dict()["payload"]["controller_contract_mode"]!="EXECUTE"
        or exe.events[-1].envelope.to_dict()["message_type"]!="execution_progress"):
        raise RuntimeError("FRESH_Q0_MACHINE_BINDING_DRIFT")

    exp=ctr.events[-1].envelope.attempt["lease_expires_at"]
    now=datetime.now(timezone.utc).isoformat(timespec="seconds")
    if datetime.fromisoformat(exp.replace("Z","+00:00"))>=datetime.now(timezone.utc):
        raise RuntimeError("ATTEMPT_NOT_EXPIRED: cannot quarantine live execution")
    before=checkpoint.to_dict()
    if checkpoint.phase=="WAIT_EXECUTOR":
        result=recover_high_integrity_session(
            continuation_store=store,repository=mailbox,
            run_id=RUN,observed_at=now)
        after=result.checkpoint
        if (after.phase!="WAIT_CONTROLLER"
            or after.next_action!="RESOLVE_EXECUTION_AUTHORITY"
            or after.controller_seq!=3
            or after.last_seen_executor_seq!=2):
            raise RuntimeError("STALE_GUARD_DID_NOT_HOLD_EFFECTS")
    elif checkpoint.phase=="WAIT_CONTROLLER" and checkpoint.next_action=="RESOLVE_EXECUTION_AUTHORITY":
        after=checkpoint
    else:
        raise RuntimeError("UNEXPECTED_CONTROLLER_RECOVERY_PHASE")

    exact=recover_continuation(store,RUN)
    if exact!=after:
        raise RuntimeError("CONTINUATION_AFTER_RECOVERY_READBACK_MISMATCH")
    if (mailbox.read(CONTROLLER).events!=ctr.events
        or mailbox.read(EXECUTOR).events!=exe.events):
        raise RuntimeError("RECOVERY_MODIFIED_IMMUTABLE_MAILBOX_EVENTS")

    comments=transport.list_comments(REPO,ISSUE)
    by_id={int(c.comment_id):c for c in comments}
    focal={str(k):_format_comment(by_id[k]) for k in FOCAL_IDS}
    new_cont=store.latest_receipt(RUN,"dw.taskcontroller.continuation/v1")
    if new_cont is None:raise RuntimeError("RECOVERY_RECEIPT_MISSING")
    latest_id=int(new_cont.comment_id)
    if latest_id not in by_id:raise RuntimeError("RECOVERY_COMMENT_NOT_READABLE")
    actual_latest=_format_comment(by_id[latest_id])
    if actual_latest["metadata"]!=after.to_dict():
        raise RuntimeError("RECOVERY_COMMENT_METADATA_READBACK_MISMATCH")

    packet={
        "schema_id":"dw.scrum781.q0-controller-recovery-disposition/v1",
        "run_id":RUN,"canonical_issue":595,"historical_issue":575,
        "source_branch":BRANCH,"recovery_runner_source_sha":head,
        "bound_controller_event_source_sha":before["exact_head_sha"],
        "controller_mailbox_ref":CONTROLLER,"executor_mailbox_ref":EXECUTOR,
        "original_actor":before["executor_actor"],
        "old_attempt_expiry":exp,
        "controller_event_seq":after.controller_seq,
        "executor_last_consumed_seq":after.last_seen_executor_seq,
        "executor_next_expected_seq":after.expected_executor_seq,
        "old_continuation":before,"recovered_continuation":after.to_dict(),
        "recovered_continuation_ref":actual_latest,
        "focal_original_refs":focal,
        "status":"STALE_ATTEMPT_RECOVERED_EFFECTS_HELD",
        "next_owner":"CONTROLLER",
        "typed_next":"RESOLVE_EXECUTION_AUTHORITY",
        "blocker_class":"AUTHORITY_BOUNDARY",
        "blockers":[
            "Expired attempt 3 lease cannot be reused",
            "Fresh #595 recipient q0-actions-engineering != intended Hermes/DWA actor",
            "No fresh #595 canonical admission proof binding Hermes actor/session",
            "No qualified event-driven Hermes wakeup and callback binding to this GPT Controller thread",
        ],
        "release_trigger":"Exact DWA main-session actor claim + current source/worktree/lease & user pause proof + approved event adapter + current authority for branch-local WRITE. Then Controller issues new bounded EXECUTE successor with new lease/fence, current head and actor.",
        "executor_effects_permitted":False,
        "new_executor_command_created":False,
        "observed_at":now,
    }
    evidence_dir=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"scrum781-q0-controller-recovery"
    evidence_dir.mkdir(parents=True,exist_ok=True)
    file=evidence_dir/"controller-recovery-disposition.json"
    file.write_text(json.dumps(packet,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    assert json.loads(file.read_text())==packet
    print(json.dumps({
        "status":packet["status"],"typed_next":packet["typed_next"],
        "run_id":RUN,"comment_ref":actual_latest["url"],
        "comment_body_sha256":actual_latest["raw_body_sha256"],
        "record_digest":actual_latest["record_digest"],
        "record_seq":actual_latest["record_seq"],
        "actor":before["executor_actor"],
        "control_seq":after.controller_seq,"executor_seen":after.last_seen_executor_seq,
        "current_source_sha":head,
        "new_executor_command_created":False
    },sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
