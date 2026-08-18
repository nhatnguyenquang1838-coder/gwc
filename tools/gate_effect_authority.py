"""Pure transitive-effect authority evaluation for gate actions.

The evaluator is data-only: it never calls connectors and never performs a
mutation.  Gate labels remain compatibility projections; semantic authority is
expressed with capabilities from the machine-readable registry.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "governance" / "gate-action-capability-registry.yaml"
NON_ESCALATING_CAPABILITIES = frozenset({"READ_ONLY", "COMPUTE"})
PROFILE_KINDS = frozenset({"NO_TRANSITIVE_MUTATION", "BOUNDED_TRANSITIVE_EFFECTS"})


def canonical_digest(value: Any) -> str:
    """Return a stable sha256 digest for one semantic JSON-compatible value."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_capability_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or REGISTRY_PATH
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("CAPABILITY_REGISTRY_INVALID: root must be an object")
    if data.get("artifact_type") != "gate-action-capability-registry":
        raise ValueError("CAPABILITY_REGISTRY_INVALID: artifact_type mismatch")
    if not isinstance(data.get("capabilities"), dict) or not isinstance(data.get("actions"), dict):
        raise ValueError("CAPABILITY_REGISTRY_INVALID: capabilities/actions required")
    return data


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _source_identity_matches(packet: dict[str, Any], identity: dict[str, Any]) -> list[str]:
    """Bind an effect policy to the exact parent action execution identity."""
    readback = packet.get("evidence_readback") if isinstance(packet.get("evidence_readback"), dict) else {}
    expected = {
        "repository": packet.get("repository"),
        "action": packet.get("action"),
        "event_id_or_idempotency_key": readback.get("event_id_or_idempotency_key"),
        "branch": packet.get("working_branch"),
        "sha": packet.get("head_sha"),
        "gate": packet.get("gate"),
    }
    expected_evidence = packet.get("expected_evidence_identity")
    if isinstance(expected_evidence, dict):
        for field in ("pr_number", "sha_kind", "workflow_run_id", "node"):
            if expected_evidence.get(field) is not None:
                expected[field] = expected_evidence[field]
    for field, value in expected.items():
        if value is not None and identity.get(field) != value:
            return ["EFFECT_SOURCE_IDENTITY_MISMATCH"]
    return []


def _grant_matches(grant: dict[str, Any], effect: dict[str, Any]) -> bool:
    return (
        grant.get("repository") == effect.get("repository")
        and grant.get("environment", "repository") == effect.get("environment", "repository")
        and grant.get("capability") == effect.get("capability")
    )


def _is_mutating(capability: str, registry: dict[str, Any]) -> bool:
    cap = registry.get("capabilities", {}).get(capability)
    return bool(isinstance(cap, dict) and cap.get("mutating"))


def _evaluate_effects(
    packet: dict[str, Any],
    effects: list[dict[str, Any]],
    source_identity: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    errors: list[str] = []
    reachable: list[str] = []
    potentially_reachable: list[str] = []
    observable: list[str] = []
    excluded: list[str] = []

    scope = packet.get("scope") if isinstance(packet.get("scope"), dict) else {}
    authorized = scope.get("authorized_capabilities") if isinstance(scope.get("authorized_capabilities"), list) else []
    independent = scope.get("independent_authorities") if isinstance(scope.get("independent_authorities"), list) else []
    parent_repo = packet.get("repository")
    source_digest = canonical_digest(source_identity)

    for index, raw in enumerate(effects):
        if not isinstance(raw, dict):
            errors.append("EFFECT_GRAPH_INVALID")
            continue
        effect_id = str(raw.get("effect_id") or f"effect-{index}")
        capability = raw.get("capability")
        if capability not in registry.get("capabilities", {}):
            errors.append("EFFECT_CAPABILITY_UNKNOWN")
            continue
        repository = raw.get("repository")
        if not isinstance(repository, str) or "/" not in repository:
            errors.append("EFFECT_GRAPH_INVALID")
            continue
        edge_state = raw.get("edge_state")
        if edge_state not in {"deterministic", "conditional"}:
            errors.append("EFFECT_GRAPH_INVALID")
            continue

        should_close = True
        if edge_state == "conditional":
            predicate = raw.get("predicate") if isinstance(raw.get("predicate"), dict) else {}
            state = predicate.get("state")
            if state == "false":
                if predicate.get("evidence_identity_digest") != source_digest:
                    errors.append("PREDICATE_EVIDENCE_REQUIRED")
                else:
                    excluded.append(effect_id)
                    should_close = False
            elif state == "true":
                reachable.append(effect_id)
            elif state == "unknown":
                if capability in NON_ESCALATING_CAPABILITIES:
                    observable.append(effect_id)
                    should_close = False
                else:
                    potentially_reachable.append(effect_id)
            else:
                errors.append("PREDICATE_STATE_INVALID")
        else:
            reachable.append(effect_id)

        if not should_close:
            continue
        if capability in NON_ESCALATING_CAPABILITIES:
            observable.append(effect_id)
            continue

        effect = {
            "repository": repository,
            "environment": raw.get("environment", "repository"),
            "capability": capability,
        }
        cross_repo = repository != parent_repo
        if cross_repo:
            if not any(isinstance(grant, dict) and _grant_matches(grant, effect) for grant in independent):
                errors.append("CROSS_REPO_AUTHORITY_REQUIRED")
        else:
            grants = [g for g in [*authorized, *independent] if isinstance(g, dict)]
            if not any(_grant_matches(grant, effect) for grant in grants):
                errors.append("TRANSITIVE_AUTHORITY_REQUIRED")

    return errors, reachable, potentially_reachable, observable, excluded


def evaluate_transitive_authority(
    packet: dict[str, Any],
    *,
    effect_graph: dict[str, Any] | None = None,
    trusted_profile: dict[str, Any] | None = None,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Close authority over deterministic and potentially reachable effects."""
    registry = registry or load_capability_registry()
    errors: list[str] = []
    action = packet.get("action")
    action_meta = registry.get("actions", {}).get(action)
    if not isinstance(action_meta, dict):
        errors.append("CAPABILITY_ACTION_UNKNOWN")
        return _result(errors, policy_source="none")

    requested = packet.get("requested_capability") or action_meta.get("capability")
    if requested not in registry.get("capabilities", {}):
        errors.append("REQUESTED_CAPABILITY_UNKNOWN")
    elif requested != action_meta.get("capability"):
        errors.append("REQUESTED_CAPABILITY_MISMATCH")

    policy_source = "none"
    effects: list[dict[str, Any]] = []
    source_identity: dict[str, Any] = {
        "repository": packet.get("repository"),
        "action": action,
        "event_id_or_idempotency_key": packet.get("evidence_readback", {}).get("event_id_or_idempotency_key"),
    }
    policy_digest: str | None = None

    if effect_graph is not None:
        policy_source = "effect_graph"
        if not isinstance(effect_graph, dict) or effect_graph.get("artifact_type") != "gate-action-effect-graph":
            errors.append("EFFECT_GRAPH_INVALID")
        else:
            policy_digest = canonical_digest(effect_graph)
            if packet.get("effect_graph_digest") != policy_digest:
                errors.append("EFFECT_GRAPH_DIGEST_MISMATCH")
            if not packet.get("effect_graph_ref"):
                errors.append("EFFECT_GRAPH_REF_REQUIRED")
            identity = effect_graph.get("source_action_identity")
            if not isinstance(identity, dict):
                errors.append("EFFECT_SOURCE_IDENTITY_MISMATCH")
            else:
                source_identity = identity
                errors.extend(_source_identity_matches(packet, identity))
            raw_effects = effect_graph.get("effects")
            if not isinstance(raw_effects, list):
                errors.append("EFFECT_GRAPH_INVALID")
            else:
                effects = raw_effects
    elif trusted_profile is not None:
        policy_source = "trusted_effect_profile"
        if not isinstance(trusted_profile, dict) or trusted_profile.get("artifact_type") != "gate-action-effect-profile":
            errors.append("EFFECT_PROFILE_INVALID")
        else:
            policy_digest = canonical_digest(trusted_profile)
            if packet.get("trusted_effect_profile_digest") != policy_digest:
                errors.append("EFFECT_PROFILE_DIGEST_MISMATCH")
            if not packet.get("trusted_effect_profile_ref"):
                errors.append("EFFECT_PROFILE_REF_REQUIRED")
            if trusted_profile.get("current") is not True:
                errors.append("EFFECT_PROFILE_STALE")
            if trusted_profile.get("complete") is not True:
                errors.append("EFFECT_PROFILE_INCOMPLETE")
            kind = trusted_profile.get("profile_kind")
            if kind not in PROFILE_KINDS:
                errors.append("EFFECT_PROFILE_INVALID")
            identity = trusted_profile.get("action_identity")
            if not isinstance(identity, dict):
                errors.append("EFFECT_SOURCE_IDENTITY_MISMATCH")
            else:
                source_identity = identity
                errors.extend(_source_identity_matches(packet, identity))
            raw_effects = trusted_profile.get("effects")
            if not isinstance(raw_effects, list):
                errors.append("EFFECT_PROFILE_INVALID")
            elif kind == "NO_TRANSITIVE_MUTATION" and raw_effects:
                errors.append("EFFECT_PROFILE_INCOMPLETE")
            else:
                effects = raw_effects
    elif action_meta.get("transitive_policy") == "NO_TRANSITIVE_MUTATION":
        policy_source = "registry_no_transitive_mutation"
    else:
        errors.append("EFFECT_GRAPH_REQUIRED")

    observed_policy_digest = packet.get("evidence_readback", {}).get("effect_policy_digest")
    if policy_digest is not None and observed_policy_digest not in (None, policy_digest):
        errors.append("EFFECT_POLICY_EVIDENCE_DRIFT")

    effect_errors: list[str] = []
    reachable: list[str] = []
    potentially: list[str] = []
    observable: list[str] = []
    excluded: list[str] = []
    # Invalid/stale/incomplete/digest-mismatched policies cannot be trusted to
    # authorize effects, but evaluating their shape is still useful diagnostic
    # evidence. The final result remains fail-closed because `errors` is nonempty.
    if effects:
        effect_errors, reachable, potentially, observable, excluded = _evaluate_effects(
            packet, effects, source_identity, registry
        )
        errors.extend(effect_errors)

    return _result(
        errors,
        policy_source=policy_source,
        requested_capability=requested,
        policy_digest=policy_digest,
        reachable_effect_ids=reachable,
        potentially_reachable_effect_ids=potentially,
        observable_effect_ids=_dedupe(observable),
        excluded_effect_ids=excluded,
    )


def _result(
    errors: list[str],
    *,
    policy_source: str,
    requested_capability: Any = None,
    policy_digest: str | None = None,
    reachable_effect_ids: list[str] | None = None,
    potentially_reachable_effect_ids: list[str] | None = None,
    observable_effect_ids: list[str] | None = None,
    excluded_effect_ids: list[str] | None = None,
) -> dict[str, Any]:
    reasons = _dedupe(errors)
    if not reasons:
        reasons = ["TRANSITIVE_AUTHORITY_CLOSED"]
    allowed = reasons == ["TRANSITIVE_AUTHORITY_CLOSED"]
    result = {
        "allowed": allowed,
        "primary_reason_code": reasons[0],
        "reason_codes": reasons,
        "policy_source": policy_source,
        "policy_digest": policy_digest,
        "requested_capability": requested_capability,
        "reachable_effect_ids": reachable_effect_ids or [],
        "potentially_reachable_effect_ids": potentially_reachable_effect_ids or [],
        "observable_effect_ids": observable_effect_ids or [],
        "excluded_effect_ids": excluded_effect_ids or [],
    }
    result["decision_digest"] = canonical_digest(result)
    return result


def validate_evidence_identity(expected: dict[str, Any], observed: dict[str, Any]) -> list[str]:
    """Compare exact execution evidence identity; historical reuse fails closed."""
    mapping = [
        ("repository", "EVIDENCE_REPOSITORY_MISMATCH"),
        ("event_id_or_idempotency_key", "EVIDENCE_EVENT_MISMATCH"),
        ("action", "EVIDENCE_ACTION_MISMATCH"),
        ("branch", "EVIDENCE_BRANCH_MISMATCH"),
        ("pr_number", "EVIDENCE_PR_MISMATCH"),
        ("sha", "EVIDENCE_SHA_MISMATCH"),
        ("sha_kind", "EVIDENCE_SHA_KIND_MISMATCH"),
        ("workflow_run_id", "EVIDENCE_WORKFLOW_RUN_MISMATCH"),
        ("gate", "EVIDENCE_GATE_MISMATCH"),
        ("node", "EVIDENCE_NODE_MISMATCH"),
    ]
    errors = [reason for field, reason in mapping if expected.get(field) != observed.get(field)]
    return errors
