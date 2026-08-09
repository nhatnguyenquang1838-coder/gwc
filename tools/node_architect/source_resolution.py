#!/usr/bin/env python3
"""Deterministic source-resolution evaluator for intake_context.source-resolution (SCRUM-299).

Resolves the authoritative instruction/source set for a task and binds every
selected source to repository / ref / SHA / provenance. Read-only G0_CONTEXT
node: it records provenance only and never grants execution authority.

Fail-closed invariants (mirrors the intake_context family contract):
* Canonical source precedence is declared by this node, never taken from input.
* Unknown, unavailable, unverified or unbound sources never PASS; they are
  rejected with an explicit reason and recorded as alternatives.
* Mandatory-source disagreement -> deterministic HUMAN_REQUIRED; missing
  mandatory source -> BLOCKED; transient unavailability -> PENDING/RETRY.
* A prior binding that drifted invalidates the stale evidence and routes for
  refresh instead of reusing it.
* Success emits a deterministic source-set digest; every authority field is
  fixed to false.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "source-resolution"

SHA40 = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[^/\s]+/[^/\s]+$")

AUTH_FIELDS = (
    "write_authority_granted",
    "commit_authority_granted",
    "push_authority_granted",
    "pr_authority_granted",
    "merge_authority_granted",
    "deployment_authority_granted",
    "production_authority_granted",
)

# Canonical source precedence — declared by the node, never by the caller.
# Lower number = higher authority.
CLASS_PRECEDENCE: dict[str, int] = {
    "REPO_INSTRUCTION": 10,
    "REPO_CORE_CONTRACT": 20,
    "REPO_NODE_DESCRIPTOR": 30,
    "PACKAGE_MANIFEST": 40,
    "PACKAGE_CORE_CONTRACT": 50,
    "PACKAGE_RUNBOOK": 60,
}

CLASS_DOMAIN: dict[str, str] = {
    "REPO_INSTRUCTION": "REPO",
    "REPO_CORE_CONTRACT": "REPO",
    "REPO_NODE_DESCRIPTOR": "REPO",
    "PACKAGE_MANIFEST": "PACKAGE",
    "PACKAGE_CORE_CONTRACT": "PACKAGE",
    "PACKAGE_RUNBOOK": "PACKAGE",
}

DEFAULT_MANDATORY_CLASSES = ("REPO_INSTRUCTION", "REPO_CORE_CONTRACT")

VALID_MODES = ("REPO", "PACKAGE", "MIXED")
AVAILABILITY = {"AVAILABLE", "UNAVAILABLE", "UNKNOWN"}

# Closed taxonomy — unknown/unavailable never PASS.
REASONS = {
    "SOURCE_ACCEPTED",
    "SOURCE_MALFORMED_INPUT",
    "SOURCE_AMBIGUOUS_AUTHORITY",
    "SOURCE_MISSING_MANDATORY",
    "SOURCE_MISSING_EVIDENCE",
    "SOURCE_INVALID_MODE",
    "SOURCE_UNBOUND_REF",
    "SOURCE_UNAVAILABLE",
    "SOURCE_STALE_DRIFT",
    "SOURCE_REPLAY_IDEMPOTENT",
    "SOURCE_HUMAN_REQUIRED",
}

# Higher precedence wins when multiple codes apply (lower number = louder).
PRECEDENCE = {
    "SOURCE_MALFORMED_INPUT": 10,
    "SOURCE_INVALID_MODE": 20,
    "SOURCE_AMBIGUOUS_AUTHORITY": 30,
    "SOURCE_MISSING_MANDATORY": 40,
    "SOURCE_UNBOUND_REF": 45,
    "SOURCE_MISSING_EVIDENCE": 50,
    "SOURCE_UNAVAILABLE": 55,
    "SOURCE_STALE_DRIFT": 70,
    "SOURCE_HUMAN_REQUIRED": 80,
    "SOURCE_REPLAY_IDEMPOTENT": 90,
    "SOURCE_ACCEPTED": 999,
}

# Total routing table: every non-accepted reason has exactly one outcome+route.
ROUTING: dict[str, tuple[str, str]] = {
    "SOURCE_MALFORMED_INPUT": ("BLOCKED", "BLOCK_G1_REVIEW"),
    "SOURCE_INVALID_MODE": ("BLOCKED", "BLOCK_G1_REVIEW"),
    "SOURCE_AMBIGUOUS_AUTHORITY": ("HUMAN_REQUIRED", "REQUEST_HUMAN_INPUT"),
    "SOURCE_MISSING_MANDATORY": ("BLOCKED", "REQUEST_HUMAN_INPUT"),
    "SOURCE_UNBOUND_REF": ("BLOCKED", "REQUEST_HUMAN_INPUT"),
    "SOURCE_MISSING_EVIDENCE": ("BLOCKED", "REQUEST_HUMAN_INPUT"),
    "SOURCE_UNAVAILABLE": ("PENDING", "RETRY_RESOLUTION"),
    "SOURCE_STALE_DRIFT": ("PENDING", "REFRESH_SOURCE"),
    "SOURCE_HUMAN_REQUIRED": ("HUMAN_REQUIRED", "REQUEST_HUMAN_INPUT"),
}

ALLOWED_NEXT_NODES = [
    "intake_context.repo-identity-check",
    "intake_context.context-gap-escalation",
]


def _canon(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, list):
        return [_canon(x) for x in value]
    return value


def canonical_json(payload: Any) -> str:
    return json.dumps(_canon(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _input_issues(
    *, task_id: Any, repository: Any, base_sha: Any, candidates: Any,
    mandatory_classes: Any, declared_mode: Any,
) -> bool:
    if not isinstance(task_id, str) or not task_id:
        return True
    if not isinstance(repository, str) or not REPO.fullmatch(repository):
        return True
    if not isinstance(base_sha, str) or not SHA40.fullmatch(base_sha):
        return True
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return True
    if not candidates:
        return True
    if not all(isinstance(c, Mapping) for c in candidates):
        return True
    if mandatory_classes is not None:
        if not isinstance(mandatory_classes, Sequence) or isinstance(mandatory_classes, (str, bytes)):
            return True
        if not all(isinstance(c, str) and c in CLASS_PRECEDENCE for c in mandatory_classes):
            return True
    if declared_mode is not None and not isinstance(declared_mode, str):
        return True
    return False


def _classify_candidate(candidate: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Return (binding, rejection_reason). Exactly one of the two is not None."""
    source_class = candidate.get("source_class")
    source_id = candidate.get("source_id")
    path = candidate.get("path")
    ref = candidate.get("ref")
    sha = candidate.get("sha")
    availability = candidate.get("availability", "AVAILABLE")
    provenance = candidate.get("provenance")

    if (
        not isinstance(source_class, str)
        or source_class not in CLASS_PRECEDENCE
        or not isinstance(source_id, str)
        or not source_id
        or not isinstance(path, str)
        or not path
        or not isinstance(availability, str)
        or availability not in AVAILABILITY
        or not isinstance(provenance, Mapping)
        or not isinstance(provenance.get("origin"), str)
        or not provenance.get("origin")
    ):
        return None, "MALFORMED_CANDIDATE"

    # Unknown availability is treated exactly like unavailable: it never passes.
    if availability != "AVAILABLE":
        return None, "UNAVAILABLE"

    if not isinstance(ref, str) or not ref or not isinstance(sha, str) or not SHA40.fullmatch(sha):
        return None, "UNBOUND_REF"

    if provenance.get("verified") is not True:
        return None, "UNVERIFIED_PROVENANCE"

    binding = {
        "source_id": source_id,
        "source_class": source_class,
        "domain": CLASS_DOMAIN[source_class],
        "precedence": CLASS_PRECEDENCE[source_class],
        "path": path,
        "ref": ref,
        "sha": sha,
        "provenance_origin": provenance["origin"],
    }
    return binding, None


def _binding_identity(binding: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(binding["source_class"]),
        str(binding["path"]),
        str(binding["ref"]),
        str(binding["sha"]),
    )


def _sort_bindings(bindings: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(b)
        for b in sorted(bindings, key=lambda b: (int(b["precedence"]), str(b["source_id"])))
    ]


def render_source_resolution(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    candidates: Sequence[Mapping[str, Any]],
    mandatory_classes: Sequence[str] | None = None,
    declared_mode: str | None = None,
    prior_resolution: Mapping[str, Any] | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Resolve the authoritative source set for a task.

    Returns a schema-valid ``source-resolution`` artifact. Fail-closed: malformed
    input, ambiguity, missing/unbound/unverified mandatory sources and drifted
    prior bindings never yield ACCEPTED.
    """
    if _input_issues(
        task_id=task_id, repository=repository, base_sha=base_sha, candidates=candidates,
        mandatory_classes=mandatory_classes, declared_mode=declared_mode,
    ):
        return _make(
            task_id=task_id if isinstance(task_id, str) and task_id else "UNKNOWN",
            repository=repository if isinstance(repository, str) and REPO.fullmatch(repository) else "invalid/invalid",
            base_sha=base_sha if isinstance(base_sha, str) and SHA40.fullmatch(base_sha) else "0" * 40,
            declared_mode=declared_mode if isinstance(declared_mode, str) else None,
            source_mode=None, authoritative_source=None, selected_sources=[],
            rejected_alternatives=[], invalidated_evidence=[], source_set_digest=None,
            reason_codes=["SOURCE_MALFORMED_INPUT"], observed_at=observed_at,
        )

    required = tuple(mandatory_classes) if mandatory_classes is not None else DEFAULT_MANDATORY_CLASSES

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    rejected_by_class: dict[str, set[str]] = {}

    for candidate in candidates:
        binding, rejection = _classify_candidate(candidate)
        if binding is not None:
            accepted.append(binding)
            continue
        source_id = candidate.get("source_id")
        source_class = candidate.get("source_class")
        rejected.append({
            "source_id": source_id if isinstance(source_id, str) and source_id else "UNKNOWN",
            "source_class": source_class if isinstance(source_class, str) and source_class else "UNKNOWN",
            "rejection_reason": rejection,
            "detail": None,
        })
        if isinstance(source_class, str):
            rejected_by_class.setdefault(source_class, set()).add(str(rejection))

    # Precedence selection: at most one binding per source class.
    by_class: dict[str, list[dict[str, Any]]] = {}
    for binding in accepted:
        by_class.setdefault(str(binding["source_class"]), []).append(binding)

    selected: list[dict[str, Any]] = []
    ambiguous_classes: list[str] = []
    for source_class, group in by_class.items():
        identities = {_binding_identity(b) for b in group}
        if len(identities) > 1:
            ambiguous_classes.append(source_class)
            for b in sorted(group, key=lambda b: str(b["source_id"])):
                rejected.append({
                    "source_id": str(b["source_id"]),
                    "source_class": source_class,
                    "rejection_reason": "CONFLICTING_BINDING",
                    "detail": f"{b['ref']}@{b['sha']}",
                })
            continue
        winner = sorted(group, key=lambda b: str(b["source_id"]))[0]
        selected.append(winner)
        for b in sorted(group, key=lambda b: str(b["source_id"]))[1:]:
            rejected.append({
                "source_id": str(b["source_id"]),
                "source_class": source_class,
                "rejection_reason": "DUPLICATE_IDENTICAL_BINDING",
                "detail": None,
            })

    selected = _sort_bindings(selected)
    selected_classes = {str(b["source_class"]) for b in selected}

    reason_codes: list[str] = []
    if ambiguous_classes:
        reason_codes.append("SOURCE_AMBIGUOUS_AUTHORITY")

    # Mandatory-class coverage — the *cause* of a gap decides the route.
    for source_class in required:
        if source_class in selected_classes or source_class in ambiguous_classes:
            continue
        causes = rejected_by_class.get(source_class, set())
        if "UNAVAILABLE" in causes:
            reason_codes.append("SOURCE_UNAVAILABLE")
        elif "UNBOUND_REF" in causes:
            reason_codes.append("SOURCE_UNBOUND_REF")
        elif "UNVERIFIED_PROVENANCE" in causes or "MALFORMED_CANDIDATE" in causes:
            reason_codes.append("SOURCE_MISSING_EVIDENCE")
        else:
            reason_codes.append("SOURCE_MISSING_MANDATORY")

    # Mode derivation — never taken from the caller, only cross-checked.
    domains = {str(b["domain"]) for b in selected}
    if not domains:
        source_mode = None
    elif domains == {"REPO"}:
        source_mode = "REPO"
    elif domains == {"PACKAGE"}:
        source_mode = "PACKAGE"
    else:
        source_mode = "MIXED"

    if source_mode is not None and source_mode not in VALID_MODES:
        reason_codes.append("SOURCE_INVALID_MODE")
    if declared_mode is not None and declared_mode != source_mode:
        reason_codes.append("SOURCE_INVALID_MODE")

    source_set_digest = (
        digest_payload({
            "repository": repository,
            "base_sha": base_sha,
            "sources": [
                {k: b[k] for k in ("source_class", "source_id", "path", "ref", "sha")}
                for b in selected
            ],
        })
        if selected
        else None
    )

    # Drift: a prior binding whose SHA moved invalidates the stale evidence.
    invalidated: list[dict[str, Any]] = []
    prior_digest = None
    if isinstance(prior_resolution, Mapping):
        prior_digest = prior_resolution.get("source_set_digest")
        prior_bindings = prior_resolution.get("bindings")
        if isinstance(prior_bindings, Mapping):
            for binding in selected:
                prior_sha = prior_bindings.get(binding["source_id"])
                if isinstance(prior_sha, str) and prior_sha != binding["sha"]:
                    invalidated.append({
                        "source_id": str(binding["source_id"]),
                        "prior_sha": prior_sha,
                        "current_sha": str(binding["sha"]),
                    })
    if invalidated:
        reason_codes.append("SOURCE_STALE_DRIFT")
    elif (
        prior_digest is not None
        and source_set_digest is not None
        and prior_digest == source_set_digest
        and not reason_codes
    ):
        reason_codes.append("SOURCE_REPLAY_IDEMPOTENT")

    if not reason_codes:
        reason_codes.append("SOURCE_ACCEPTED")

    authoritative = selected[0] if selected else None
    if any(c not in ("SOURCE_ACCEPTED", "SOURCE_REPLAY_IDEMPOTENT") for c in reason_codes):
        # Fail-closed: no authoritative binding is published on a non-accepting route.
        authoritative = None

    return _make(
        task_id=task_id, repository=repository, base_sha=base_sha,
        declared_mode=declared_mode, source_mode=source_mode,
        authoritative_source=authoritative, selected_sources=selected,
        rejected_alternatives=rejected, invalidated_evidence=invalidated,
        source_set_digest=source_set_digest, reason_codes=reason_codes,
        observed_at=observed_at,
    )


def _next_action(primary: str, artifact_bits: Mapping[str, Any]) -> str:
    return {
        "SOURCE_MALFORMED_INPUT": "Repair malformed source-resolution evaluator inputs.",
        "SOURCE_INVALID_MODE": "Reconcile the declared source mode with the derived REPO/PACKAGE/MIXED mode.",
        "SOURCE_AMBIGUOUS_AUTHORITY": "Two candidates of the same source class disagree; a human must pick the authoritative binding.",
        "SOURCE_MISSING_MANDATORY": "Supply the missing mandatory source class before resolution can proceed.",
        "SOURCE_UNBOUND_REF": "Bind the mandatory source to an exact ref and 40-character SHA.",
        "SOURCE_MISSING_EVIDENCE": "Provide verified provenance for the mandatory source; unverified evidence never passes.",
        "SOURCE_UNAVAILABLE": "Mandatory source is unavailable; retry resolution once it can be read.",
        "SOURCE_STALE_DRIFT": "A prior binding drifted; stale evidence is invalidated — refresh the source before downstream use.",
        "SOURCE_HUMAN_REQUIRED": "Human input is required to resolve the source set.",
    }.get(primary, "Repair source-resolution inputs and replay.")


def _stop_condition(route: str) -> str:
    return {
        "RETRY_RESOLUTION": "Stop until the unavailable source can be read and resolution is replayed.",
        "REQUEST_HUMAN_INPUT": "Stop until a human supplies or disambiguates the mandatory source.",
        "BLOCK_G1_REVIEW": "Stop until the malformed input or mode conflict is resolved by review.",
        "REFRESH_SOURCE": "Stop until the drifted source is refreshed and re-bound to an exact SHA.",
    }.get(route, "Stop until inputs conform to the runtime interface.")


def _make(
    *, task_id: str, repository: str, base_sha: str, declared_mode: str | None,
    source_mode: str | None, authoritative_source: Mapping[str, Any] | None,
    selected_sources: list[dict[str, Any]], rejected_alternatives: list[dict[str, Any]],
    invalidated_evidence: list[dict[str, Any]], source_set_digest: str | None,
    reason_codes: list[str], observed_at: str | None,
) -> dict[str, Any]:
    ordered = sorted(set(reason_codes), key=lambda c: PRECEDENCE.get(c, 500))
    primary = ordered[0]
    if primary in ROUTING:
        outcome, route = ROUTING[primary]
        remediation = {
            "route": route,
            "next_action": _next_action(primary, {}),
            "stop_condition": _stop_condition(route),
        }
        next_allowed: list[str] = []
    else:
        outcome = "ACCEPTED"
        remediation = None
        next_allowed = list(ALLOWED_NEXT_NODES)

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "declared_mode": declared_mode,
        "source_mode": source_mode,
        "authoritative_source": dict(authoritative_source) if authoritative_source else None,
        "selected_sources": selected_sources,
        "rejected_alternatives": sorted(
            rejected_alternatives, key=lambda r: (str(r["source_class"]), str(r["source_id"]), str(r["rejection_reason"]))
        ),
        "invalidated_evidence": sorted(invalidated_evidence, key=lambda r: str(r["source_id"])),
        "source_set_digest": source_set_digest,
        "outcome": outcome,
        "reason_code": primary,
        "reason_codes": ordered,
        "remediation": remediation,
        "next_allowed_nodes": next_allowed,
        "observed_at": observed_at,
        "read_only_projection": True,
        "write_authority_granted": False,
        "commit_authority_granted": False,
        "push_authority_granted": False,
        "pr_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    artifact["decision_digest"] = digest_payload(
        {k: v for k, v in artifact.items() if k != "decision_digest"}
    )
    return artifact


if __name__ == "__main__":
    import sys
    payload = json.load(sys.stdin)
    print(json.dumps(render_source_resolution(**payload), indent=2, ensure_ascii=False))
