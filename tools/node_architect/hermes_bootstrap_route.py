"""Select Hermes instruction overlay from explicit working-mode binding.

This is a fail-closed, side-effect-free routing helper, not a skill loader or
approval authority. A selected route is not Hermes runtime load proof.
"""
from __future__ import annotations

NATIVE = "agents/hermes/native-universal-v2.md"
SLACK = ("agents/shared/slack-controller-executor-protocol.md",
         "agents/hermes/agent-instructions.md")
V2 = "UNIVERSAL_V2_DEVELOPMENT"


def resolve_hermes_bootstrap_route(*, runtime_epoch: str, working_mode: str | None,
                                   slack_binding_verified: bool = False) -> dict:
    """Return mode-specific overlays; reject unverified Slack selection."""
    if not isinstance(runtime_epoch, str) or not runtime_epoch:
        return {"status": "ROUTE_UNRESOLVED", "reason": "RUNTIME_EPOCH_MISSING",
                "role_overlays": [], "effect_admission": False, "read_only_allowed": True}
    if runtime_epoch != V2:
        return {"status": "ROUTE_UNRESOLVED", "reason": "NATIVE_V2_NOT_SELECTED",
                "role_overlays": [], "effect_admission": False, "read_only_allowed": True}
    if working_mode in (None, "", "native_universal_v2"):
        if slack_binding_verified:
            return {"status": "ROUTE_UNRESOLVED", "reason": "MODE_BINDING_CONFLICT",
                    "role_overlays": [], "effect_admission": False, "read_only_allowed": True}
        return {"status": "ROUTE_RESOLVED", "mode": "native_universal_v2",
                "role_overlays": [NATIVE], "effect_admission": False,
                "read_only_allowed": True}
    if working_mode == "slack_controller_executor":
        if not slack_binding_verified:
            return {"status": "ROUTE_UNRESOLVED", "reason": "SLACK_BINDING_UNVERIFIED",
                    "role_overlays": [], "effect_admission": False, "read_only_allowed": True}
        return {"status": "ROUTE_RESOLVED", "mode": "slack_controller_executor",
                "role_overlays": list(SLACK), "effect_admission": False,
                "read_only_allowed": True}
    return {"status": "ROUTE_UNRESOLVED", "reason": "WORKING_MODE_UNKNOWN",
            "role_overlays": [], "effect_admission": False, "read_only_allowed": True}
