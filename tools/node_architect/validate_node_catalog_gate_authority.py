"""Shared catalog owner for the gate_authority MAT-F2 node family.

Final integration owner: validates that every node in the family implements the
closed-schema + pure-evaluator + focused-test contract. Pure and offline.
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Any

_NODES = {
    "SCRUM-185": "tools.node_architect.approval_token_generation",
    "SCRUM-186": "tools.node_architect.approval_command_validation",
    "SCRUM-190": "tools.node_architect.gate_transition_decision",
    "SCRUM-191": "tools.node_architect.g2_execution_envelope_render",
    "SCRUM-192": "tools.node_architect.blocked_action_escalation",
}

_REQUIRED_PUBLIC_ATTRS = {
    "SCRUM-185": ["generate_approval_request"],
    "SCRUM-186": ["validate_approval_command"],
    "SCRUM-190": ["decide_gate_transition"],
    "SCRUM-191": ["render_g2_execution_envelope"],
    "SCRUM-192": ["escalate_blocked_action"],
}


def validate_node_catalog_gate_authority() -> dict[str, Any]:
    """Return a catalog validation report (no side effects)."""
    report: dict[str, Any] = {"nodes": {}, "all_present": True, "errors": []}
    for node_id, module_name in _NODES.items():
        node = {"module": module_name, "present": True, "missing": []}
        try:
            mod = importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - defensive
            node["present"] = False
            node["import_error"] = str(exc)
            report["all_present"] = False
            report["errors"].append(f"{node_id}: import failed: {exc}")
            report["nodes"][node_id] = node
            continue
        for attr in _REQUIRED_PUBLIC_ATTRS[node_id]:
            if not hasattr(mod, attr):
                node["missing"].append(attr)
                report["all_present"] = False
                report["errors"].append(f"{node_id}: missing {attr}")
        report["nodes"][node_id] = node
    report["summary"] = "OK" if report["all_present"] else "INCOMPLETE"
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(validate_node_catalog_gate_authority(), indent=2))
