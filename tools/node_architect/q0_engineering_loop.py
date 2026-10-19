"""Native Q0 ENGINEERING_WORK preparation; not a TaskController adapter.

The guard returns host preflight evidence only. It grants neither effect authority
nor native C/E admission and never mutates/resumes a scheduler.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping


def assess_engineering_resume(*, expected: Mapping[str, str], observed: Mapping[str, str],
                              loop_role: str, execute_contract_current: bool,
                              user_paused: bool, run_hold: bool, awaiting_response: bool,
                              owner_verified: bool, observer_qualified: bool,
                              prepare_only: bool = True, owned_firing_verified: bool = False) -> dict[str, Any]:
    flags = (execute_contract_current, user_paused, run_hold, awaiting_response,
             owner_verified, observer_qualified, prepare_only, owned_firing_verified)
    if any(type(value) is not bool for value in flags):
        raise ValueError('BOOLEAN_CHECK_REQUIRED')
    result = {'outcome': 'BLOCKED', 'auto_resume_allowed': False,
              'typed_ce_allowed': False, 'effect_authority_granted': False,
              'effects_executed': [], 'requires_user_resume': user_paused}
    checks = [
        (loop_role == 'ENGINEERING_WORK', 'ENGINEERING_ROLE_REQUIRED'),
        (all(isinstance(expected.get(key), str) and expected[key] and expected[key] == observed.get(key)
             for key in ('session_id', 'run_id', 'head_sha')), 'BINDING_MISMATCH'),
        (not run_hold, 'RUN_HOLD'),
        (execute_contract_current, 'EXECUTE_CONTRACT_NOT_CURRENT'),
        (owner_verified, 'HOST_OWNER_UNVERIFIED'),
        (not owned_firing_verified or (awaiting_response and owner_verified), 'NO_VERIFIED_OWNER_FIRING'),
        (not awaiting_response or owned_firing_verified, 'FIRING_IN_FLIGHT'),
        (prepare_only or not user_paused, 'USER_PAUSED'),
    ]
    for passed, reason in checks:
        if not passed:
            return {**result, 'reason_code': reason}
    return {**result, 'outcome': 'ENGINEERING_LOOP_RESUME_READY' if prepare_only else 'ENGINEERING_PREFLIGHT_PASS',
            'reason_code': 'ENGINEERING_ONLY_NO_CE_ADMISSION',
            'observer_qualified': observer_qualified}


def engineering_prompt(*, run_id: str, session_id: str, repository_root: Path,
                       controller_url: str) -> str:
    return f'''SCRUM-781 Q0 — ENGINEERING_WORK, SAME RUN/SESSION/BRANCH.
Run: {run_id}
Existing native session: {session_id}
Canonical writable repository: {repository_root}
Controller strategy remains coordination; bound GPT URL: {controller_url}

This scheduler advances independently authorized GWC Universal v2 Q0 engineering.
Typed machine C/E polling and dispatch remain BLOCKED unless separately admitted.
This engineering workflow is not MAILBOX_OBSERVER or a Controller-wakeup poller.
Do not poll typed C/E/continuation, scan issue history
for authority, wake GPT periodically, create an issuer/lease, or infer qualification.

On each ACTUAL firing: bind the exact native session, live owner, counter and
worktree; read AGENTS.md UNIVERSAL_V2_DEVELOPMENT and the source-bound Q0 plan.
Run the versioned host workflow CLI in this repository BEFORE selecting work:
  python scripts/scrum781_engineering_loop.py inspect --session {session_id} --tick <ACTUAL_NATIVE_COUNTER> --workflow-mode Q0_ENGINEERING_COORDINATION
The existing inspect --tick entrypoint routes to the same workflow for compatibility.
Engineering M1 owns the one-shot #595 read inside the host workflow; do not read
the issue collection a second time outside it. Filter communication/v2 by exact
run and author, validate latest command/source/seq/reply, and keep typed bodies
opaque. Do not use #608 or create a replacement mailbox. Human consumption is
LOCAL_ONLY, persisted after validation/processing, never typed C/E admission.
Require actual graph verdict, selected work/result and durable checkpoint readback.
Engineering identity is generic-engineering-m1-m7/v1. PROTECTED_TYPED_CE remains
separate, unchanged and fail-closed; missing typed observation is not a global
engineering HOLD. Never substitute human communication for protected evidence.
Prioritize the RuntimePlan's DWO Login reproduction or real Q0 defect, not
unrelated coverage. The CLI's executed/verified work is this firing's one bounded
action. For a real source defect, RED→FIX→GREEN under the current source policy.
When M7 returns a pending report/exchange request, use #595 for the next actual
communication seq, exact-read the material report and fulfill the SAME reserved
HOST_COORDINATION request through the installed dwa-gpt-exchange skill/outbox.
Use its stored TaskContext, marker and URL; no duplicate reservation/stage/send.
Persist delivery/readback with truthful receipt strength. No protected M7 or
native settlement claim. A pending browser effect does not block unrelated
authorized engineering. If no new/ready work exists, checkpoint NO_MATERIAL_CHANGE
silently; no routine reports or GPT wakeups. Any independent
Controller exchange requires explicit user authorization or a qualified semantic
handoff; native timer movement alone never authorizes browser sends.
Substitute only this genuine firing's verified native counter; never guess one.
Treat its result as preflight data, never authority. If it reports FIRING_IN_FLIGHT,
only the owner of this exact genuine firing may continue; never clear another tick.
Verify actual effect authority, approved scope, current source and absence of a
new user stop/RUN_HOLD immediately before any effect. Missing bindings hold that effect.

Take one bounded ready engineering action permitted by the current plan: diagnose
and repair a Q0-relevant failure with RED→GREEN, verify source/reload evidence,
or resolve provenance of the original incident. Do not rerun unchanged audits
or tests as progress. Preserve six foreign untracked files and a single writer.
Keep frozen protected M1–M7 identities/topology unchanged. Do not change M1 HOLD to PASS
in protected mode or use browser text as typed C/E evidence. A protected HOLD blocks C/E effects,
not independently authorized native engineering. Never claim LOAD_PROOF, original
replay, L3 or native gate receipts from unit tests or scheduler counters.

Use drive_preview for a justified semantic Controller handoff or explicit user
contact only, on the exact URL; verify liveness, draft, fresh Send and new user turn.
Honor any newer browser hold. No duplicate/pending/busy sends and no alternate transport.
No Hermes core/plugin edits, protected-main merge, deploy, production/config/data,
secrets, migrations, cleanup/reset/rebase/force-push or silent route/strategy changes.

Do not auto-resume any control, manufacture a firing, reset counters, or manually
settle/abandon another owner's tick. Return actual action, evidence, owner/NEXT and
current blocker. Native owner retains cadence and fire/complete/abandon lifecycle.
Do not emit LOOP_COMPLETE unless the run's real terminal condition is verified.
'''
