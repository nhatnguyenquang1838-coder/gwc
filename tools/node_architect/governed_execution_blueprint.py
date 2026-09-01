"""GWC-owned governed execution blueprint contract.

The blueprint describes a prospective, source-backed execution topology.  It is
provider-neutral and declarative: authority requirements are recorded, but no
field in this module can grant authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_NODE_INSTRUCTION_SUFFIX = ".node-instruction.yaml"
_REQUIRED_SOURCE_KEYS = frozenset(
    {
        "gwc_sha",
        "flow_ref",
        "flow_revision",
        "flow_digest",
        "policy_ref",
        "policy_revision",
        "policy_digest",
        "project_profile_ref",
    }
)


class BlueprintValidationError(ValueError):
    """Raised when a blueprint is missing or contradicts a required binding."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BlueprintValidationError(f"{field} must be a non-empty string")
    return value


def _digest(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256(value: Any, field: str) -> str:
    value = _text(value, field)
    if not _SHA256_RE.fullmatch(value):
        raise BlueprintValidationError(f"{field} must be a sha256 digest")
    return value


@dataclass(frozen=True)
class RunbookBinding:
    """Reference to one immutable modular runbook revision."""

    runbook_id: str
    revision: str
    digest: str

    def __post_init__(self) -> None:
        _text(self.runbook_id, "runbook_id")
        _text(self.revision, "runbook.revision")
        _sha256(self.digest, "runbook.digest")

    def to_dict(self) -> dict[str, str]:
        return {
            "runbook_id": self.runbook_id,
            "revision": self.revision,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunbookBinding":
        try:
            return cls(
                runbook_id=payload["runbook_id"],
                revision=payload["revision"],
                digest=payload["digest"],
            )
        except KeyError as exc:
            raise BlueprintValidationError(
                f"runbook binding missing field: {exc.args[0]}"
            ) from exc


@dataclass(frozen=True)
class BlueprintNodeBinding:
    """Exact Node Architect binding for one semantic action."""

    action: str
    node_id: str
    node_instruction_ref: str
    node_instruction_digest: str
    implementation_ref: str
    route_profile_revision: str
    graph_revision: str
    node_registry_revision: str

    def __post_init__(self) -> None:
        for name in (
            "action",
            "node_id",
            "node_instruction_ref",
            "implementation_ref",
            "route_profile_revision",
            "graph_revision",
            "node_registry_revision",
        ):
            _text(getattr(self, name), f"node.{name}")
        if not self.node_instruction_ref.endswith(_NODE_INSTRUCTION_SUFFIX):
            raise BlueprintValidationError("node instruction ref is invalid")
        _sha256(self.node_instruction_digest, "node instruction digest")

    def to_dict(self) -> dict[str, str]:
        return {
            "action": self.action,
            "node_id": self.node_id,
            "node_instruction_ref": self.node_instruction_ref,
            "node_instruction_digest": self.node_instruction_digest,
            "implementation_ref": self.implementation_ref,
            "route_profile_revision": self.route_profile_revision,
            "graph_revision": self.graph_revision,
            "node_registry_revision": self.node_registry_revision,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BlueprintNodeBinding":
        required = (
            "action",
            "node_id",
            "node_instruction_ref",
            "node_instruction_digest",
            "implementation_ref",
            "route_profile_revision",
            "graph_revision",
            "node_registry_revision",
        )
        try:
            return cls(**{name: payload[name] for name in required})
        except KeyError as exc:
            raise BlueprintValidationError(
                f"node binding missing field: {exc.args[0]}"
            ) from exc


@dataclass(frozen=True)
class GovernedExecutionBlueprint:
    """Deterministic prospective topology emitted by GWC."""

    blueprint_id: str
    task_id: str
    scenario: str
    source_bindings: Mapping[str, str]
    runbooks: tuple[RunbookBinding, ...]
    nodes: tuple[BlueprintNodeBinding, ...]
    topology: tuple[Mapping[str, Any], ...]
    authority_requirements: tuple[Mapping[str, Any], ...] = ()
    implementation_plan_ref: str | None = None

    def __post_init__(self) -> None:
        for name in ("blueprint_id", "task_id", "scenario"):
            _text(getattr(self, name), name)
        if not isinstance(self.source_bindings, Mapping):
            raise BlueprintValidationError("source_bindings must be a mapping")
        source = {str(key): value for key, value in self.source_bindings.items()}
        missing = sorted(_REQUIRED_SOURCE_KEYS - set(source))
        if missing:
            raise BlueprintValidationError(
                f"source bindings missing fields: {', '.join(missing)}"
            )
        if not _SHA40_RE.fullmatch(str(source["gwc_sha"])):
            raise BlueprintValidationError("source gwc_sha must be a 40-character SHA")
        _sha256(source["flow_digest"], "source flow_digest")
        _sha256(source["policy_digest"], "source policy_digest")
        for key, value in source.items():
            _text(value, f"source {key}")
        object.__setattr__(self, "source_bindings", MappingProxyType(source))

        if not isinstance(self.runbooks, Sequence) or isinstance(self.runbooks, (str, bytes)):
            raise BlueprintValidationError("runbooks must be a sequence")
        runbooks = tuple(self.runbooks)
        if not runbooks:
            raise BlueprintValidationError("blueprint requires at least one runbook")
        if any(not isinstance(item, RunbookBinding) for item in runbooks):
            raise BlueprintValidationError("runbooks must contain RunbookBinding values")
        if len({item.runbook_id for item in runbooks}) != len(runbooks):
            raise BlueprintValidationError("runbook bindings must be unique")
        object.__setattr__(self, "runbooks", runbooks)

        if not isinstance(self.nodes, Sequence) or isinstance(self.nodes, (str, bytes)):
            raise BlueprintValidationError("nodes must be a sequence")
        nodes = tuple(self.nodes)
        if not nodes or any(not isinstance(item, BlueprintNodeBinding) for item in nodes):
            raise BlueprintValidationError("blueprint requires Node Architect bindings")
        actions = [item.action for item in nodes]
        if len(set(actions)) != len(actions):
            raise BlueprintValidationError("node actions must be unambiguous")
        object.__setattr__(self, "nodes", nodes)

        if not isinstance(self.topology, Sequence) or isinstance(self.topology, (str, bytes)):
            raise BlueprintValidationError("topology must be a sequence")
        topology = tuple(dict(item) for item in self.topology)
        if not topology:
            raise BlueprintValidationError("blueprint topology must not be empty")
        known_actions = set(actions)
        seen_actions: set[str] = set()
        for item in topology:
            action = _text(item.get("action"), "topology.action")
            node_id = _text(item.get("node_id"), "topology.node_id")
            _text(item.get("next"), "topology.next")
            if action in seen_actions or action not in known_actions:
                raise BlueprintValidationError(
                    f"topology action is ambiguous or unbound: {action}"
                )
            matching = [node for node in nodes if node.action == action]
            if matching[0].node_id != node_id:
                raise BlueprintValidationError(
                    f"topology node binding mismatch for action: {action}"
                )
            seen_actions.add(action)
        object.__setattr__(self, "topology", topology)

        if not isinstance(self.authority_requirements, Sequence) or isinstance(
            self.authority_requirements, (str, bytes)
        ):
            raise BlueprintValidationError("authority_requirements must be a sequence")
        authority = tuple(dict(item) for item in self.authority_requirements)
        for item in authority:
            _text(item.get("action"), "authority.action")
            _text(item.get("gate"), "authority.gate")
            if not isinstance(item.get("required"), bool):
                raise BlueprintValidationError("authority.required must be boolean")
        object.__setattr__(self, "authority_requirements", authority)
        if self.implementation_plan_ref is not None:
            _text(self.implementation_plan_ref, "implementation_plan_ref")

    @property
    def authority_granted(self) -> bool:
        """Always false: the blueprint is not a GWC authority source."""
        return False

    @property
    def blueprint_digest(self) -> str:
        return _digest(self.to_dict())

    def validate_source_bindings(self, expected: Mapping[str, str]) -> None:
        """Compare this blueprint to independently resolved source bindings."""
        if dict(self.source_bindings) != dict(expected):
            raise BlueprintValidationError("source binding drift detected")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": "1.0",
            "artifact_type": "governed-execution-blueprint",
            "blueprint_id": self.blueprint_id,
            "task_id": self.task_id,
            "scenario": self.scenario,
            "source_bindings": dict(sorted(self.source_bindings.items())),
            "runbooks": [item.to_dict() for item in self.runbooks],
            "nodes": [item.to_dict() for item in self.nodes],
            "topology": [dict(item) for item in self.topology],
            "authority_requirements": [dict(item) for item in self.authority_requirements],
            "implementation_plan_ref": self.implementation_plan_ref,
        }
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GovernedExecutionBlueprint":
        if not isinstance(payload, Mapping):
            raise BlueprintValidationError("blueprint payload must be a mapping")
        forbidden = sorted(
            key
            for key in (
                "authority_granted",
                "write_authority_granted",
                "merge_authority_granted",
                "deployment_authority_granted",
            )
            if key in payload
        )
        if forbidden:
            raise BlueprintValidationError(
                f"authority_granted fields are forbidden: {forbidden}"
            )
        try:
            return cls(
                blueprint_id=payload["blueprint_id"],
                task_id=payload["task_id"],
                scenario=payload["scenario"],
                source_bindings=payload["source_bindings"],
                runbooks=tuple(RunbookBinding.from_dict(item) for item in payload["runbooks"]),
                nodes=tuple(BlueprintNodeBinding.from_dict(item) for item in payload["nodes"]),
                topology=tuple(payload["topology"]),
                authority_requirements=tuple(payload.get("authority_requirements", ())),
                implementation_plan_ref=payload.get("implementation_plan_ref"),
            )
        except KeyError as exc:
            raise BlueprintValidationError(
                f"blueprint missing field: {exc.args[0]}"
            ) from exc


__all__ = [
    "BlueprintNodeBinding",
    "BlueprintValidationError",
    "GovernedExecutionBlueprint",
    "RunbookBinding",
]
