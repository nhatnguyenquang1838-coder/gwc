#!/usr/bin/env python3
"""Correct semantic executability truth model for Node Architect.

Structural shadow-envelope reachability is intentionally independent from
semantic implementation, invocation, live Agent observation and authorized
execution. Historical W1-W6 evidence therefore remains readable without being
promoted into semantic E4/E5 proof.
"""
from __future__ import annotations

from typing import Any, Mapping

E_LEVELS = (
    "E0_CATALOGUED",
    "E1_INSTRUCTION_READY",
    "E2_SEMANTIC_IMPLEMENTATION_BOUND",
    "E3_CANONICAL_ROUTE_BOUND",
    "E4_SEMANTIC_REPLAY_PROVEN",
    "E5_LIVE_AGENT_OBSERVED",
    "E6_AUTHORIZED_AGENT_EXECUTION_PROVEN",
)


def _digest_like(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and len(value) == 71


def _binding_valid(binding: Mapping[str, Any] | None) -> bool:
    return bool(
        isinstance(binding, Mapping)
        and binding.get("implementation_ref")
        and _digest_like(binding.get("binding_digest"))
    )


def _semantic_replay_valid(replay: Mapping[str, Any] | None, binding: Mapping[str, Any] | None) -> bool:
    if not isinstance(replay, Mapping) or not _binding_valid(binding):
        return False
    if replay.get("evidence_class") == "HISTORICAL_ENVELOPE_COMPATIBILITY":
        return False
    return bool(
        replay.get("semantic_execution") is True
        and replay.get("implementation_invoked") is True
        and _digest_like(replay.get("invocation_digest"))
        and replay.get("binding_digest") == binding.get("binding_digest")
    )


def _live_valid(live: Mapping[str, Any] | None, binding: Mapping[str, Any] | None) -> bool:
    return bool(
        isinstance(live, Mapping)
        and live.get("live_agent_event") is True
        and live.get("synthetic") is not True
        and live.get("implementation_invoked") is True
        and _digest_like(live.get("invocation_digest"))
        and isinstance(binding, Mapping)
        and live.get("binding_digest") == binding.get("binding_digest")
    )


def _authorized_valid(auth: Mapping[str, Any] | None, binding: Mapping[str, Any] | None) -> bool:
    return bool(
        isinstance(auth, Mapping)
        and auth.get("execution_mode") == "authoritative"
        and auth.get("authority_validated") is True
        and auth.get("canonical_readback_verified") is True
        and auth.get("implementation_invoked") is True
        and _digest_like(auth.get("invocation_digest"))
        and isinstance(binding, Mapping)
        and auth.get("binding_digest") == binding.get("binding_digest")
    )


def qualify_semantic_node(
    *,
    node_id: str,
    instruction_ready: bool,
    implementation_binding: Mapping[str, Any] | None,
    canonical_route_bound: bool,
    replay_evidence: Mapping[str, Any] | None,
    live_evidence: Mapping[str, Any] | None,
    authorized_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    implementation_bound = _binding_valid(implementation_binding)
    semantic_replay = _semantic_replay_valid(replay_evidence, implementation_binding)
    live_observed = _live_valid(live_evidence, implementation_binding)
    authorized_proven = _authorized_valid(authorized_evidence, implementation_binding)
    historical_envelope = bool(
        isinstance(replay_evidence, Mapping)
        and replay_evidence.get("replay_proven") is True
        and replay_evidence.get("evidence_class") == "HISTORICAL_ENVELOPE_COMPATIBILITY"
    )

    level = "E0_CATALOGUED"
    if instruction_ready:
        level = "E1_INSTRUCTION_READY"
    if instruction_ready and implementation_bound:
        level = "E2_SEMANTIC_IMPLEMENTATION_BOUND"
    if instruction_ready and implementation_bound and canonical_route_bound:
        level = "E3_CANONICAL_ROUTE_BOUND"
    if instruction_ready and implementation_bound and canonical_route_bound and semantic_replay:
        level = "E4_SEMANTIC_REPLAY_PROVEN"
    if level == "E4_SEMANTIC_REPLAY_PROVEN" and live_observed:
        level = "E5_LIVE_AGENT_OBSERVED"
    if level == "E5_LIVE_AGENT_OBSERVED" and authorized_proven:
        level = "E6_AUTHORIZED_AGENT_EXECUTION_PROVEN"

    return {
        "node_id": node_id,
        "executability_level": level,
        "catalogued": True,
        "instruction_ready": instruction_ready,
        "shadow_envelope_enabled": historical_envelope,
        "semantic_implementation_bound": implementation_bound,
        "canonical_route_bound": bool(canonical_route_bound and implementation_bound),
        "semantic_replay_proven": semantic_replay,
        "live_agent_observed": live_observed,
        "authorized_agent_execution_proven": authorized_proven,
        "binding_digest": implementation_binding.get("binding_digest") if isinstance(implementation_binding, Mapping) else None,
        "semantic_invocation_digest": replay_evidence.get("invocation_digest") if semantic_replay and isinstance(replay_evidence, Mapping) else None,
    }


__all__ = ["E_LEVELS", "qualify_semantic_node"]
