#!/usr/bin/env python3
"""semantic_agent_runtime.py
CR0-GWC-NODE-BINDING implementation for SCRUM-780.
Semantic runtime layer for executing GWC agent tasks under bounded authority.
"""
import logging, os, hashlib, json
from typing import Dict, Any, List, Optional

log = logging.getLogger(__name__)


class SemanticAgentRuntime:
    """Bounded runtime executing GWC agent tasks under G1/G2 authority."""

    def __init__(self, workspace: str, scope_hash: str):
        self.workspace = workspace
        self.scope_hash = scope_hash
        self._verify_scope_binding()

    def _verify_scope_binding(self) -> None:
        """Ensure runtime scope matches approved envelope."""
        env_path = os.path.join(self.workspace, ".gwc", "tasks", "SCRUM-780", "g2", "execution-envelope.yaml")
        import yaml
        with open(env_path) as f:
            env = yaml.safe_load(f)
        if env.get("scope_hash") != self.scope_hash:
            raise PermissionError("Scope hash mismatch — failing closed")
        log.info("Scope binding verified: %s", self.scope_hash)

    def execute_task(self, phase: str, commands: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute bounded task phase under authority contract."""
        log.info("Executing phase=%s", phase)
        result = {
            "phase": phase,
            "executed_actions": [],
            "state": "ACTIVE",
        }
        for c in commands:
            action = c.get("action", "noop")
            if action in ("read", "validate"):
                result["executed_actions"].append({"action": action, "status": "PASS"})
            elif action == "stop":
                raise PermissionError("Stop action — fail closed")
        return result


def compute_scope_hash(paths: List[str]) -> str:
    """Compute canonical scope hash for semantic runtime binding."""
    h = hashlib.sha256()
    for p in sorted(paths):
        if os.path.isfile(p):
            h.update(p.encode())
            h.update(open(p, "rb").read())
    return "sha256:" + h.hexdigest()


__all__ = ["SemanticAgentRuntime", "compute_scope_hash"]
