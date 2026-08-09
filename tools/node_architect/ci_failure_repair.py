"""Deterministic CI failure classification for bounded PR repair (SCRUM-322).

Exposes one side-effect-free function:

    classify_ci_failure(...) -> dict

It classifies a terminal exact-head CI failure as:

  - REPAIR_REPOSITORY  — repo-fixable inside the current PR's approved scope
  - EXTERNAL_BLOCKED   — infrastructure / external / out-of-scope
  - EVIDENCE_INVALID   — required fields missing (fail closed)

Repair decisions invalidate prior head evidence because the CI failure
occurred against an exact head SHA; any remediation changes the head and
renders the old CI/review evidence stale.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any


_REASON_RE = re.compile(r"^CI_[A-Z_]+$")

# Patterns that, when present in a single job step, indicate the failure
# originates inside the repository and is therefore within bounded-repair
# authority. Patterns are matched case-insensitively against the lower-cased
# failure text.
_REPO_FIXABLE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"SyntaxError", re.I),
    re.compile(r"IndentationError", re.I),
    re.compile(r"NameError", re.I),
    re.compile(r"ModuleNotFoundError", re.I),
    re.compile(r"ImportError", re.I),
    re.compile(r"AttributeError", re.I),
    re.compile(r"TypeError", re.I),
    re.compile(r"FileNotFoundError", re.I),
    re.compile(r"\bFAILED\b.*test_", re.I),
    re.compile(r"test_.*FAILED", re.I),
    re.compile(r"FAIL:\s*test_", re.I),
    re.compile(r"ERROR:\s*test_", re.I),
    re.compile(r"pytest\s+.*--cov", re.I),
    re.compile(r"failed\s*\d+", re.I),            # e.g. "FAILED 12 passed, 3 failed"
    re.compile(r"error\s*\[", re.I),              # ruff / flake8 style
    re.compile(r"flake8", re.I),
    re.compile(r"ruff\s+check", re.I),
    re.compile(r"mypy:\s*error", re.I),
    re.compile(r"mypy\s+--", re.I),
    re.compile(r"pylint", re.I),
    re.compile(r"security\s+vulnerability", re.I),
    re.compile(r"bandit", re.I),
    re.compile(r"semgrep", re.I),
    re.compile(r"dependency\s+conflict", re.I),
    re.compile(r"resolve\s+dependencies", re.I),
    re.compile(r"npm\s+err", re.I),
    re.compile(r"pip\s+install.*failed", re.I),
    re.compile(r"poetry\s+install", re.I),
    re.compile(r"yarn\s+install", re.I),
    re.compile(r"deno\s+cache", re.I),
    re.compile(r"go\s+mod\s+tidy", re.I),
    re.compile(r"cargo\s+check", re.I),
    re.compile(r"cargo\s+test", re.I),
    re.compile(r"java\.lang\.", re.I),
    re.compile(r"NoClassDefFoundError", re.I),
    re.compile(r"build\s+failed", re.I),
    re.compile(r"compilation\s+failed", re.I),
    re.compile(r"linker\s+command\s+failed", re.I),
)

# Patterns that indicate the failure is external and must not be repaired
# by the agent. If any of these match and no repo-fixable pattern also
# matches, the decision is EXTERNAL_BLOCKED.
_EXTERNAL_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"Error\s+during\s+connection", re.I),
    re.compile(r"Could\s+not\s+resolve\s+host", re.I),
    re.compile(r"Connection\s+timed?\s*out", re.I),
    re.compile(r"read\s+timeout", re.I),
    re.compile(r"connect\s+timeout", re.I),
    re.compile(r"gateway\s+timeout", re.I),
    re.compile(r"502\s+Bad\s+Gateway", re.I),
    re.compile(r"503\s+Service\s+Unavailable", re.I),
    re.compile(r"504\s+Gateway\s+Timeout", re.I),
    re.compile(r"No\s+route\s+to\s+host", re.I),
    re.compile(r"Network\s+is\s+unreachable", re.I),
    re.compile(r"OOMKilled", re.I),
    re.compile(r"out\s+of\s+memory", re.I),
    re.compile(r"cgroup\s+memory", re.I),
    re.compile(r"runner\s+offline", re.I),
    re.compile(r"self-hosted\s+runner", re.I),
    re.compile(r"Host\s+key\s+verification\s+failed", re.I),
    re.compile(r"Permission\s+denied\s*\(publickey\)", re.I),
    re.compile(r"no\s+space\s+left\s+on\s+device", re.I),
    re.compile(r"disk\s+quota\s+exceeded", re.I),
    re.compile(r"quota\s+exceeded", re.I),
    re.compile(r"resource\s+temporarily\s+unavailable", re.I),
    re.compile(r"operation\s+not\s+permitted", re.I),
)


def _canon(obj: Any) -> str:
    if isinstance(obj, dict):
        return "{" + ",".join(f"{k}:{_canon(v)}" for k, v in sorted(obj.items())) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_canon(v) for v in obj) + "]"
    return str(obj)


def _digest(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(_canon(p).encode("utf-8"))
    return "sha256:" + h.hexdigest()


def _classify_failure(
    failure_text: str,
    failure_type: str | None = None,
) -> str:
    lower = failure_text.lower()

    repo_hits = sum(p.search(lower) is not None for p in _REPO_FIXABLE_PATTERNS)
    ext_hits = sum(p.search(lower) is not None for p in _EXTERNAL_PATTERNS)

    if ext_hits and not repo_hits:
        return "EXTERNAL_BLOCKED"

    if repo_hits:
        return "REPAIR_REPOSITORY"

    # Unknown / unclassified — fail closed rather than silently authorize.
    return "EVIDENCE_INVALID"


def classify_ci_failure(
    *,
    task_id: str,
    repository: str,
    pr_number: int,
    head_sha: str,
    run_id: str,
    workflow_name: str,
    failure_text: str,
    failure_type: str | None = None,
    job_name: str | None = None,
    step_name: str | None = None,
    approved_file_scope: list[str] | None = None,
    prior_escalation: dict[str, object] | None = None,
    event_id_or_idempotency_key: str,
    decided_at: str | None = None,
) -> dict[str, object]:
    """Classify a terminal exact-head CI failure for bounded PR repair.

    Parameters
    ----------
    task_id:
        GWC task identifier (e.g. ``SCRUM-322``).
    repository:
        owner/repo string.
    pr_number:
        Pull request number.
    head_sha:
        40-hex SHA-1 of the exact head that failed.
    run_id:
        CI provider run identifier.
    workflow_name:
        Name of the workflow that failed.
    failure_text:
        Plain-text or ADF-extracted failure summary.
    failure_type:
        Optional normalized type hint.
    job_name:
        Optional CI job name.
    step_name:
        Optional CI step name.
    approved_file_scope:
        Explicit file/glob scope allowed for repair under the active G2
        envelope. Must be present for a repair decision; absent => blocked.
    prior_escalation:
        Optional prior escalation record for replay conflict detection.
    event_id_or_idempotency_key:
        Stable key for replay/idempotency verification.
    decided_at:
        ISO-8601 timestamp of the decision; defaults to current UTC time.

    Returns
    -------
    dict with keys:
        schema_version, artifact_type, task_id, repository, pr_number,
        head_sha, run_id, workflow_name, failure_text, failure_type,
        job_name, step_name, decision, reason_code, is_repo_fixable,
        approved_file_scope, invalidate_prior_head_evidence,
        prior_head_sha, remediation_scope, execution_performed,
        replay_status, escalation_digest, event_id_or_idempotency_key,
        decided_at.
    """
    failure_text = str(failure_text)
    event_id_or_idempotency_key = str(event_id_or_idempotency_key)

    if not re.fullmatch(r"^SCRUM-\d+$", str(task_id)):
        raise ValueError(f"task_id must match ^SCRUM-\d+$, got {task_id!r}")

    if not re.fullmatch(r"^[\w.-]+/[\w.-]+$", str(repository)):
        raise ValueError(
            f"repository must be owner/repo, got {repository!r}"
        )

    if not re.fullmatch(r"[0-9a-f]{40}", str(head_sha), re.I):
        raise ValueError(
            f"head_sha must be a 40-hex SHA-1, got {head_sha!r}"
        )

    if not str(run_id).strip():
        raise ValueError("run_id is required")

    if not str(workflow_name).strip():
        raise ValueError("workflow_name is required")

    if not str(failure_text).strip():
        raise ValueError("failure_text is required")

    decision = _classify_failure(failure_text, failure_type)

    # Replay conflict detection.
    replay_status = "IDEMPOTENT"
    if prior_escalation is not None:
        prior_key = str(prior_escalation.get("event_id_or_idempotency_key", ""))
        if prior_key and prior_key == event_id_or_idempotency_key:
            replay_status = "CONFLICT"

    if decision == "REPAIR_REPOSITORY":
        if not approved_file_scope:
            # Cannot authorize repair without an explicit approved scope.
            decision = "EVIDENCE_INVALID"
            reason_code = "CI_REPAIR_SCOPE_MISSING"
            remediation_scope = None
            is_repo_fixable = False
        else:
            reason_code = "CI_REPO_FIXABLE"
            remediation_scope = (
                f"bounded-pr:{pr_number}:"
                + ",".join(str(p) for p in sorted(set(approved_file_scope)))
            )
            is_repo_fixable = True
    elif decision == "EXTERNAL_BLOCKED":
        reason_code = "CI_EXTERNAL_FAILURE"
        remediation_scope = None
        is_repo_fixable = False
    else:
        reason_code = "CI_EVIDENCE_INVALID"
        remediation_scope = None
        is_repo_fixable = False

    prior_head_sha = str(prior_escalation.get("head_sha", "")) \
        if prior_escalation is not None else ""

    # Any repair decision creates a new head; prior evidence is stale.
    invalidate_prior_head_evidence = decision == "REPAIR_REPOSITORY"

    escalation_digest = _digest(
        task_id,
        repository,
        pr_number,
        head_sha,
        run_id,
        workflow_name,
        failure_text,
        decision,
        reason_code,
        remediation_scope,
        invalidate_prior_head_evidence,
        event_id_or_idempotency_key,
    )

    return {
        "schema_version": "1.0",
        "artifact_type": "ci-failure-repair",
        "task_id": str(task_id),
        "repository": str(repository),
        "pr_number": int(pr_number),
        "head_sha": str(head_sha),
        "run_id": str(run_id),
        "workflow_name": str(workflow_name),
        "failure_text": failure_text,
        "failure_type": str(failure_type) if failure_type is not None else None,
        "job_name": str(job_name) if job_name is not None else None,
        "step_name": str(step_name) if step_name is not None else None,
        "decision": decision,
        "reason_code": reason_code,
        "is_repo_fixable": is_repo_fixable,
        "approved_file_scope": (
            list(approved_file_scope) if approved_file_scope else None
        ),
        "invalidate_prior_head_evidence": invalidate_prior_head_evidence,
        "prior_head_sha": prior_head_sha or None,
        "remediation_scope": remediation_scope,
        "execution_performed": False,
        "replay_status": replay_status,
        "escalation_digest": escalation_digest,
        "event_id_or_idempotency_key": event_id_or_idempotency_key,
        "decided_at": str(decided_at) if decided_at is not None else None,
    }


__all__ = ["classify_ci_failure"]
