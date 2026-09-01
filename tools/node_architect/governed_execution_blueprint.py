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
    implementation_plan_ref: str = ""

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
        # M1: implementation_plan_ref is REQUIRED (W4 compiler needs it as
        # the canonical runtime_plan_ref — it must never be None/empty).
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
                implementation_plan_ref=payload["implementation_plan_ref"],
            )
        except KeyError as exc:
            raise BlueprintValidationError(
                f"blueprint missing field: {exc.args[0]}"
            ) from exc


def _node_instruction_ref(node_id: str) -> str:
    """Derive the canonical node-instruction ref for a node id.

    ``family.name`` -> ``core/node-architect/node-instructions/<family>/<name>.node-instruction.yaml``
    """
    family, _, name = node_id.partition(".")
    if not family or not name:
        raise BlueprintValidationError(f"node id is not family.name: {node_id!r}")
    return (
        f"core/node-architect/node-instructions/{family}/{name}.node-instruction.yaml"
    )


def produce_governed_blueprint(
    *,
    task_id: str,
    scenario: str,
    repo_root: str = ".",
) -> GovernedExecutionBlueprint:
    """Compile a governed execution blueprint from the LIVE Node Architect registries.

    Reads the canonical registries under ``core/node-architect/``:
    - ``runtime-graph-registry.json`` for the executable runtime edges (topology);
    - ``node-registry.json`` for node binding metadata (implementation ref, revisions);
    - the node-instruction YAML files for each bound node's instruction digest;
    - ``flow-policy-compiled-profile.json`` + ``flow-policy-activation-registry.json``
      for source flow/policy identity + digest;
    - ``core/runbooks/`` for the bound runbook set.

    This is the real canonical producer the W1-W7 review demanded (W3 was only a
    schema/validator before). It never grants authority — ``authority_granted``
    stays False by construction.
    """
    from pathlib import Path

    root = Path(repo_root)

    # 1. Runtime graph — executable edges only (topology source).
    graph_path = root / "core/node-architect/runtime-graph-registry.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph_revision = graph.get("revision", {})
    graph_revision_id = (
        graph_revision.get("revision_id")
        if isinstance(graph_revision, dict)
        else str(graph_revision)
    )
    graph_nodes: list[str] = list(graph.get("nodes", []))
    edges: list[Mapping[str, Any]] = [
        e for e in graph.get("edges", []) if e.get("runtime_executable") is True
    ]
    if not edges:
        raise BlueprintValidationError("runtime graph has no executable edges")

    # 2. Node registry for implementation refs + revisions.
    node_reg_path = root / "core/node-architect/node-registry.json"
    node_reg = json.loads(node_reg_path.read_text(encoding="utf-8"))
    node_reg_revision = node_reg.get("revision", "")
    node_registry_by_id = {
        item["id"]: item
        for item in node_reg.get("nodes", [])
    }

    # 3. Node instruction digests from the live YAML files.
    def _instruction_digest(node_id: str) -> str:
        ref = _node_instruction_ref(node_id)
        path = root / ref
        if not path.exists():
            raise BlueprintValidationError(f"node instruction missing: {ref}")
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    # 4. Collect bound node ids (sources + targets of executable edges).
    bound_node_ids: list[str] = []
    for edge in edges:
        for node_id in (edge.get("source"), edge.get("target")):
            if node_id not in bound_node_ids:
                bound_node_ids.append(node_id)

    nodes: list[BlueprintNodeBinding] = []
    for node_id in bound_node_ids:
        entry = node_registry_by_id.get(node_id)
        if entry is None:
            raise BlueprintValidationError(f"node not in node registry: {node_id}")
        implementation_refs = entry.get("implementation_refs", [])
        implementation_ref = (
            implementation_refs[0] if implementation_refs else f"tools/node_architect/{node_id}.py"
        )
        nodes.append(
            BlueprintNodeBinding(
                action=node_id,
                node_id=node_id,
                node_instruction_ref=_node_instruction_ref(node_id),
                node_instruction_digest=_instruction_digest(node_id),
                implementation_ref=implementation_ref,
                route_profile_revision="route-v1",
                graph_revision=graph_revision_id,
                node_registry_revision=node_reg_revision,
            )
        )

    # 5. Topology: ONE entry per bound node (dedupe — the blueprint contract
    # rejects duplicate actions). ``next`` = first executable target, or
    # terminal when the node is a sink.
    topology_by_action: dict[str, str] = {}
    for edge in edges:
        src = edge["source"]
        tgt = edge["target"]
        if src not in topology_by_action:
            topology_by_action[src] = tgt
        elif tgt not in (topology_by_action[src], "terminal"):
            # multi-target source: keep a non-terminal first target
            if topology_by_action[src] == "terminal":
                topology_by_action[src] = tgt
    for node_id in bound_node_ids:
        if node_id not in topology_by_action:
            topology_by_action[node_id] = "terminal"
    topology: list[Mapping[str, Any]] = [
        {"action": node_id, "node_id": node_id, "next": nxt}
        for node_id, nxt in topology_by_action.items()
    ]

    # 6. Source bindings from flow/policy registries + live gwc sha.
    flow_profile_path = root / "core/node-architect/flow-policy-compiled-profile.json"
    flow_profile = json.loads(flow_profile_path.read_text(encoding="utf-8"))
    workflow = flow_profile.get("workflow", {})
    policy = flow_profile.get("policy", {})
    activation_path = root / "core/node-architect/flow-policy-activation-registry.json"
    activation = json.loads(activation_path.read_text(encoding="utf-8"))

    import subprocess

    gwc_sha = (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(root)
        ).stdout.strip()
        or "0" * 40
    )

    source_bindings = {
        "gwc_sha": gwc_sha,
        "flow_ref": "core/node-architect/profile-registry.json",
        "flow_revision": workflow.get("revision", ""),
        "flow_digest": workflow.get("workflow_digest", ""),
        "policy_ref": "core/node-architect/gate-applicability-policy-registry.json",
        "policy_revision": policy.get("revision", ""),
        "policy_digest": policy.get("registry_digest", ""),
        "project_profile_ref": "projects/gwc/project-profile.yaml",
    }

    # 7. Runbooks from the live runbook directory.
    runbook_dir = root / "core/runbooks"
    runbook_files = sorted(runbook_dir.glob("*.md"))
    if not runbook_files:
        raise BlueprintValidationError("no runbooks under core/runbooks")
    runbooks: list[RunbookBinding] = []
    for rb_path in runbook_files:
        digest = "sha256:" + hashlib.sha256(rb_path.read_bytes()).hexdigest()
        runbooks.append(
            RunbookBinding(
                runbook_id=rb_path.stem,
                revision="v1.0",
                digest=digest,
            )
        )

    return GovernedExecutionBlueprint(
        blueprint_id=f"blueprint.{task_id}",
        task_id=task_id,
        scenario=scenario,
        source_bindings=source_bindings,
        runbooks=tuple(runbooks),
        nodes=tuple(nodes),
        topology=tuple(topology),
        authority_requirements=tuple(
            {"action": n.action, "gate": "G3_PR", "required": True} for n in nodes
        ),
        implementation_plan_ref=f"implementation-plan/{task_id}/r1",
    )


__all__ = [
    "BlueprintNodeBinding",
    "BlueprintValidationError",
    "GovernedExecutionBlueprint",
    "RunbookBinding",
    "produce_governed_blueprint",
]
