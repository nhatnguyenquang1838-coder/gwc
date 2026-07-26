"""Normalize read-only repository and CI observations into an exact-state result.

The capture operation only evaluates supplied observations. It never calls a
provider, changes repository state, or treats a latest/non-matching observation
as evidence for the requested SHA.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class ExactState(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    OBSERVABILITY_INCOMPLETE = "observability_incomplete"
    SHA_MISMATCH = "sha_mismatch"


@dataclass(frozen=True)
class ExactStateEvidence:
    state: ExactState
    task_id: str
    repository: str
    expected_sha: str
    observed_sha: str | None
    workflow: str | None
    run_id: int | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "task_id": self.task_id,
            "repository": self.repository,
            "expected_sha": self.expected_sha,
            "observed_sha": self.observed_sha,
            "workflow": self.workflow,
            "run_id": self.run_id,
            "reason": self.reason,
        }


def capture_exact_state(
    *,
    task_id: str,
    repository: str,
    expected_sha: str,
    observation: Mapping[str, Any] | None,
) -> ExactStateEvidence:
    """Classify one already-observed run without producing side effects.

    ``observation`` must contain ``head_sha`` and may contain ``status``,
    ``conclusion``, ``workflow``, and ``run_id``. Missing observations are
    deliberately different from a pending run: no exact state was observable.
    """
    if observation is None or not observation.get("head_sha"):
        return ExactStateEvidence(
            ExactState.OBSERVABILITY_INCOMPLETE,
            task_id,
            repository,
            expected_sha,
            None,
            None,
            None,
            "no exact-head observation was available",
        )

    observed_sha = str(observation["head_sha"])
    common = {
        "task_id": task_id,
        "repository": repository,
        "expected_sha": expected_sha,
        "observed_sha": observed_sha,
        "workflow": observation.get("workflow"),
        "run_id": observation.get("run_id"),
    }
    if observed_sha != expected_sha:
        return ExactStateEvidence(
            ExactState.SHA_MISMATCH,
            reason="observed head SHA differs from expected SHA",
            **common,
        )

    status = observation.get("status")
    conclusion = observation.get("conclusion")
    if status in {"queued", "waiting", "requested", "in_progress"}:
        return ExactStateEvidence(
            ExactState.PENDING,
            reason="exact-head run is not terminal",
            **common,
        )
    if conclusion in {"failure", "cancelled", "timed_out", "action_required"}:
        return ExactStateEvidence(
            ExactState.FAILURE,
            reason=f"exact-head run concluded {conclusion}",
            **common,
        )
    if conclusion == "success":
        return ExactStateEvidence(
            ExactState.SUCCESS,
            reason="exact-head run completed successfully",
            **common,
        )
    return ExactStateEvidence(
        ExactState.OBSERVABILITY_INCOMPLETE,
        reason="exact-head run lacks a recognized terminal state",
        **common,
    )
