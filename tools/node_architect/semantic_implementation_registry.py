#!/usr/bin/env python3
"""Compile and validate the canonical-81 semantic implementation registry.

Binding precedence is deterministic:
1. explicit callable already bound by the canonical gate-node route profile;
2. descriptor-declared evaluator / exact named semantic tool with a concrete
   public callable discovered from its AST;
3. the node's validated Node Instruction Card interpreted by the explicit
   ``instruction_contract_evaluator``.

The old generic shadow adapter is never an implementation fallback.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator

from .node_executability import validate_canonical_coverage
from .semantic_source_resolver import resolve_semantic_source
from .validate_node_instruction import bridge_node_identity, digest_payload

INSTRUCTION_EVALUATOR = "tools/node_architect/instruction_contract_evaluator.py:evaluate_instruction_contract"
PREFERRED_CALL_PREFIXES = (
    "evaluate", "validate", "resolve", "decide", "capture", "build", "generate",
    "materialize", "check", "verify", "classify", "compute", "execute", "run", "load",
)


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _digest(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def node_registry_revision(registry: Mapping[str, Any]) -> str:
    revision = registry.get("revision")
    return str(revision.get("revision_id", "")) if isinstance(revision, Mapping) else str(revision or "")


def _safe_ref(path: str) -> bool:
    if not path or "\\" in path:
        return False
    value = PurePosixPath(path)
    return not value.is_absolute() and all(part not in {"", ".", ".."} for part in value.parts)


def _load_json(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _load_yaml(path: Path) -> Mapping[str, Any] | None:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, Mapping) else None


def _instruction_ref(node: Mapping[str, Any]) -> str:
    node_id = str(node.get("id", ""))
    family, _, slug = node_id.partition(".")
    return f"core/node-architect/node-instructions/{family}/{slug}.node-instruction.yaml"


def _descriptor_ref(node: Mapping[str, Any]) -> str | None:
    provenance = node.get("provenance") if isinstance(node.get("provenance"), Mapping) else {}
    ref = provenance.get("source_path")
    return str(ref) if isinstance(ref, str) and ref else None


def _instruction(root: Path, node: Mapping[str, Any], schema: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, str | None]:
    ref = _instruction_ref(node)
    path = root / ref
    card = _load_yaml(path)
    if card is None:
        return None, "SEMANTIC_NODE_INSTRUCTION_MISSING"
    try:
        errors = list(Draft202012Validator(schema).iter_errors(card))
    except Exception:
        return None, "SEMANTIC_NODE_INSTRUCTION_INVALID"
    if errors:
        return None, "SEMANTIC_NODE_INSTRUCTION_INVALID"
    if bridge_node_identity(card.get("node_id", "")) != bridge_node_identity(node.get("id", "")):
        return None, "SEMANTIC_NODE_INSTRUCTION_ID_MISMATCH"
    return card, None


def _route_implementations(root: Path) -> dict[str, str]:
    profile = _load_json(root / "core/node-architect/gate-node-route-profile.json") or {}
    result: dict[str, str] = {}
    conflicts: set[str] = set()
    for route in profile.get("routes", []):
        if not isinstance(route, Mapping):
            continue
        node_id = route.get("current_node")
        implementation = route.get("implementation") if isinstance(route.get("implementation"), Mapping) else {}
        ref = implementation.get("ref")
        if not isinstance(node_id, str) or not isinstance(ref, str) or not ref:
            continue
        previous = result.get(node_id)
        if previous is not None and previous != ref:
            conflicts.add(node_id)
        else:
            result[node_id] = ref
    for node_id in conflicts:
        result.pop(node_id, None)
    return result


def _public_callables(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return []
    return [
        item.name
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not item.name.startswith("_")
        and item.name != "main"
    ]


def _callable_ref_valid(root: Path, ref: str) -> bool:
    path_text, sep, callable_name = ref.partition(":")
    if not sep or not callable_name.isidentifier() or not _safe_ref(path_text):
        return False
    path = root / path_text
    return path.is_file() and callable_name in _public_callables(path)


def _resolve_callable_for_source(root: Path, source_path: str) -> str | None:
    if not _safe_ref(source_path):
        return None
    path = root / source_path
    if not path.is_file():
        return None
    callables = _public_callables(path)
    if not callables:
        return None
    for prefix in PREFERRED_CALL_PREFIXES:
        matches = [name for name in callables if name == prefix or name.startswith(prefix + "_")]
        if len(matches) == 1:
            return f"{source_path}:{matches[0]}"
    if len(callables) == 1:
        return f"{source_path}:{callables[0]}"
    return None


def _authority_requirements(card: Mapping[str, Any], node: Mapping[str, Any]) -> dict[str, Any]:
    boundary = card.get("authority_boundary") if isinstance(card.get("authority_boundary"), Mapping) else {}
    return {
        "gate_authority_required": bool((card.get("mode_policy") or {}).get("gate_authority_required", True)) if isinstance(card.get("mode_policy"), Mapping) else True,
        "authority_class": node.get("authority_class"),
        "node_grants_gate_authority": False,
        "g2_authority_granted": False,
        "g3_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "statement": boundary.get("statement"),
    }


def _binding_payload(
    *,
    node: Mapping[str, Any],
    registry_revision: str,
    card: Mapping[str, Any],
    implementation_kind: str,
    implementation_ref: str,
    semantic_source_kind: str,
    descriptor_ref: str | None,
) -> dict[str, Any]:
    instruction_ref = _instruction_ref(node)
    payload = {
        "node_id": str(node.get("id", "")),
        "node_version": str(node.get("version", "")),
        "family": node.get("family"),
        "node_registry_revision": registry_revision,
        "implementation_kind": implementation_kind,
        "implementation_ref": implementation_ref,
        "semantic_source_kind": semantic_source_kind,
        "descriptor_ref": descriptor_ref,
        "instruction_ref": instruction_ref,
        "instruction_digest": digest_payload(card),
        "instruction_valid": True,
        "implementation_callable_valid": True,
        "gates": list(card.get("gate", []) or []),
        "entry_contract": list(card.get("inputs", []) or []),
        "input_schema": {"required": list(card.get("inputs", []) or [])},
        "output_schema": {"declared": list(card.get("outputs", []) or [])},
        "readback_contract": {
            "required": "node-readback" in set(card.get("evidence_required", []) or []),
            "evidence_required": list(card.get("evidence_required", []) or []),
        },
        "side_effect_class": str(node.get("effect_class") or "read_only"),
        "authority_requirements": _authority_requirements(card, node),
        "checkpoint_contract": {
            "required": "checkpoint" in set(card.get("evidence_required", []) or []),
            "suspension": dict(node.get("suspension") or {}) if isinstance(node.get("suspension"), Mapping) else {},
            "retry": dict(card.get("retry") or {}) if isinstance(card.get("retry"), Mapping) else {},
        },
        "next_route_contract": dict(card.get("next") or {}) if isinstance(card.get("next"), Mapping) else {},
    }
    payload["binding_digest"] = _digest(payload)
    return payload


def compile_semantic_implementation_registry(
    node_registry: Mapping[str, Any],
    *,
    root: Path | str = Path("."),
) -> dict[str, Any]:
    repo_root = Path(root).resolve()
    errors = list(validate_canonical_coverage(dict(node_registry)))
    schema = _load_json(repo_root / "schemas/node-architect/node-instruction.schema.json")
    if schema is None:
        errors.append("SEMANTIC_INSTRUCTION_SCHEMA_MISSING")
        schema = {}
    revision = node_registry_revision(node_registry)
    route_refs = _route_implementations(repo_root)
    bindings: list[dict[str, Any]] = []
    binding_errors: list[dict[str, Any]] = []

    for node in node_registry.get("nodes", []):
        if not isinstance(node, Mapping) or not node.get("id"):
            continue
        node_id = str(node["id"])
        card, instruction_error = _instruction(repo_root, node, schema)
        if card is None:
            binding_errors.append({"node_id": node_id, "reason_code": instruction_error})
            continue
        descriptor_ref = _descriptor_ref(node)

        implementation_kind = ""
        implementation_ref = ""
        semantic_source_kind = ""
        route_ref = route_refs.get(node_id)
        if route_ref and _callable_ref_valid(repo_root, route_ref):
            implementation_kind = "canonical_route_callable"
            implementation_ref = route_ref
            semantic_source_kind = "CANONICAL_ROUTE_IMPLEMENTATION"
        else:
            source = resolve_semantic_source(node, root=repo_root)
            source_path = source.get("evaluator_path") if isinstance(source, Mapping) else None
            callable_ref = _resolve_callable_for_source(repo_root, str(source_path)) if isinstance(source_path, str) else None
            if callable_ref is not None:
                implementation_kind = "semantic_tool_callable"
                implementation_ref = callable_ref
                semantic_source_kind = str(source.get("status") or "SEMANTIC_TOOL")
            elif (repo_root / _instruction_ref(node)).is_file():
                implementation_kind = "instruction_contract"
                implementation_ref = INSTRUCTION_EVALUATOR
                semantic_source_kind = "NODE_INSTRUCTION_CONTRACT"

        if not implementation_ref or not _callable_ref_valid(repo_root, implementation_ref):
            binding_errors.append({"node_id": node_id, "reason_code": "SEMANTIC_IMPLEMENTATION_MISSING_OR_INVALID"})
            continue

        bindings.append(
            _binding_payload(
                node=node,
                registry_revision=revision,
                card=card,
                implementation_kind=implementation_kind,
                implementation_ref=implementation_ref,
                semantic_source_kind=semantic_source_kind,
                descriptor_ref=descriptor_ref,
            )
        )

    ids = [item["node_id"] for item in bindings]
    if len(ids) != len(set(ids)):
        errors.append("SEMANTIC_IMPLEMENTATION_DUPLICATE_BINDING")
    if len(bindings) != 81:
        errors.append("SEMANTIC_IMPLEMENTATION_COVERAGE_GAP")
    errors.extend(
        f"{item['reason_code']}:{item['node_id']}" for item in binding_errors if item.get("reason_code")
    )
    summary = {
        "canonical_node_count": len(node_registry.get("nodes", [])) if isinstance(node_registry.get("nodes"), list) else 0,
        "implementation_bound_count": len(bindings),
        "instruction_contract_bound_count": sum(item["implementation_kind"] == "instruction_contract" for item in bindings),
        "existing_implementation_reused_count": sum(item["implementation_kind"] != "instruction_contract" for item in bindings),
    }
    report = {
        "schema_version": "1.0",
        "artifact_type": "semantic-implementation-registry",
        "status": "PASS" if not errors else "FAIL",
        "node_registry_revision": revision,
        "summary": summary,
        "bindings": sorted(bindings, key=lambda item: item["node_id"]),
        "binding_errors": binding_errors,
        "errors": sorted(set(errors)),
    }
    report["registry_digest"] = _digest(report)
    return report


def validate_semantic_implementation_registry(
    compiled: Mapping[str, Any],
    *,
    node_registry: Mapping[str, Any],
    root: Path | str = Path("."),
) -> list[str]:
    repo_root = Path(root).resolve()
    errors: list[str] = []
    current_revision = node_registry_revision(node_registry)
    if compiled.get("node_registry_revision") != current_revision:
        errors.append("SEMANTIC_BINDING_REGISTRY_REVISION_DRIFT")
    node_map = {
        str(node.get("id")): node
        for node in node_registry.get("nodes", [])
        if isinstance(node, Mapping) and node.get("id")
    }
    bindings = compiled.get("bindings") if isinstance(compiled.get("bindings"), list) else []
    if len(bindings) != 81 or len({item.get("node_id") for item in bindings if isinstance(item, Mapping)}) != 81:
        errors.append("SEMANTIC_IMPLEMENTATION_COVERAGE_GAP")
    for binding in bindings:
        if not isinstance(binding, Mapping):
            errors.append("SEMANTIC_BINDING_INVALID")
            continue
        node = node_map.get(str(binding.get("node_id", "")))
        if node is None:
            errors.append("SEMANTIC_BINDING_NODE_MISSING")
            continue
        if str(binding.get("node_version", "")) != str(node.get("version", "")):
            errors.append("SEMANTIC_BINDING_NODE_VERSION_DRIFT")
        if binding.get("node_registry_revision") != current_revision:
            errors.append("SEMANTIC_BINDING_REGISTRY_REVISION_DRIFT")
        ref = binding.get("implementation_ref")
        if not isinstance(ref, str) or not _callable_ref_valid(repo_root, ref):
            errors.append("SEMANTIC_BINDING_CALLABLE_INVALID")
        if not binding.get("readback_contract"):
            errors.append("SEMANTIC_BINDING_READBACK_CONTRACT_MISSING")
        if not binding.get("next_route_contract"):
            errors.append("SEMANTIC_BINDING_NEXT_ROUTE_CONTRACT_MISSING")
        if not binding.get("authority_requirements"):
            errors.append("SEMANTIC_BINDING_AUTHORITY_METADATA_MISSING")
    return list(dict.fromkeys(errors))


__all__ = [
    "INSTRUCTION_EVALUATOR",
    "compile_semantic_implementation_registry",
    "node_registry_revision",
    "validate_semantic_implementation_registry",
]
