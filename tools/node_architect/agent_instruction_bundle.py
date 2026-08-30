#!/usr/bin/env python3
"""Deterministically materialize repository instructions and skills for an Agent node.

The Agent Host, not the model, selects the ordered instruction refs, role overlays,
required skill names and current node instruction. This module reads the exact
repository bytes, hashes every source, preserves the actual content for provider
context, and emits one immutable bundle digest. Missing, unsafe or duplicate
sources fail closed; there is no silent skill or instruction fallback.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_NODE_INSTRUCTION_PREFIX = "core/node-architect/node-instructions/"
_NODE_INSTRUCTION_SUFFIX = ".node-instruction.yaml"


class InstructionBundleError(ValueError):
    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _safe_ref(ref: str) -> bool:
    if not ref or "\\" in ref:
        return False
    path = PurePosixPath(ref)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def _read_source(root: Path, ref: str, kind: str) -> dict[str, str]:
    if not _safe_ref(ref):
        raise InstructionBundleError("AGENT_INSTRUCTION_SOURCE_UNSAFE", ref)
    path = (root / ref).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise InstructionBundleError("AGENT_INSTRUCTION_SOURCE_UNSAFE", ref) from exc
    if not path.is_file():
        raise InstructionBundleError("AGENT_INSTRUCTION_SOURCE_MISSING", ref)
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InstructionBundleError("AGENT_INSTRUCTION_SOURCE_UNREADABLE", ref) from exc
    return {"kind": kind, "ref": ref, "digest": _sha256_text(content), "content": content}


def _validate_node_instruction_ref(ref: str) -> None:
    if not (
        _safe_ref(ref)
        and ref.startswith(_NODE_INSTRUCTION_PREFIX)
        and ref.endswith(_NODE_INSTRUCTION_SUFFIX)
    ):
        raise InstructionBundleError("AGENT_NODE_INSTRUCTION_REF_INVALID", ref)


def _skill_ref(name: str) -> str:
    if not isinstance(name, str) or _SKILL_NAME_RE.fullmatch(name) is None:
        raise InstructionBundleError("AGENT_SKILL_NAME_INVALID", str(name))
    return f"skills/{name}/SKILL.md"


def _bundle_digest(artifacts: Sequence[Mapping[str, Any]]) -> str:
    identity = [
        {"kind": item["kind"], "ref": item["ref"], "digest": item["digest"]}
        for item in artifacts
    ]
    return _sha256_text(_canonical(identity))


def resolve_agent_instruction_bundle(
    *,
    root: Path | str,
    instruction_refs: Sequence[str],
    required_skill_names: Sequence[str],
    node_instruction_ref: str,
    role_overlay_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Resolve the exact repository instruction/skill context for one Agent node.

    Ordering is intentional and digest-bearing:
    base instructions -> role overlays -> required skills -> current node instruction.
    ``required_skill_names`` is supplied by the host/runtime contract; the LLM is
    never asked to discover or choose skills dynamically.
    """
    repo_root = Path(root).resolve()
    _validate_node_instruction_ref(node_instruction_ref)

    skill_refs = [_skill_ref(name) for name in required_skill_names]
    ordered: list[tuple[str, str]] = []
    ordered.extend(("instruction", str(ref)) for ref in instruction_refs)
    ordered.extend(("role_overlay", str(ref)) for ref in role_overlay_refs)
    ordered.extend(("skill", ref) for ref in skill_refs)
    ordered.append(("node_instruction", node_instruction_ref))

    refs = [ref for _, ref in ordered]
    if len(refs) != len(set(refs)):
        raise InstructionBundleError("AGENT_INSTRUCTION_SOURCE_DUPLICATE")

    artifacts = [_read_source(repo_root, ref, kind) for kind, ref in ordered]
    by_kind: dict[str, list[dict[str, str]]] = {}
    for item in artifacts:
        by_kind.setdefault(item["kind"], []).append(item)

    instructions = by_kind.get("instruction", [])
    overlays = by_kind.get("role_overlay", [])
    skills = by_kind.get("skill", [])
    nodes = by_kind.get("node_instruction", [])
    if len(nodes) != 1:
        raise InstructionBundleError("AGENT_NODE_INSTRUCTION_CARDINALITY_INVALID")

    bundle = {
        "schema_version": "1.0",
        "artifact_type": "agent-instruction-bundle",
        "instruction_refs": [item["ref"] for item in instructions],
        "instruction_digests": [item["digest"] for item in instructions],
        "role_overlay_refs": [item["ref"] for item in overlays],
        "role_overlay_digests": [item["digest"] for item in overlays],
        "skill_refs": [item["ref"] for item in skills],
        "skill_digests": [item["digest"] for item in skills],
        "node_instruction_ref": nodes[0]["ref"],
        "node_instruction_digest": nodes[0]["digest"],
        "artifacts": artifacts,
    }
    bundle["bundle_digest"] = _bundle_digest(artifacts)
    return bundle


def validate_agent_instruction_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize a previously materialized instruction bundle."""
    if not isinstance(bundle, Mapping):
        raise InstructionBundleError("AGENT_INSTRUCTION_BUNDLE_INVALID", "not a mapping")
    if bundle.get("schema_version") != "1.0" or bundle.get("artifact_type") != "agent-instruction-bundle":
        raise InstructionBundleError("AGENT_INSTRUCTION_BUNDLE_INVALID", "schema/artifact type")
    raw_artifacts = bundle.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise InstructionBundleError("AGENT_INSTRUCTION_BUNDLE_INVALID", "artifacts")

    artifacts: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in raw_artifacts:
        if not isinstance(raw, Mapping):
            raise InstructionBundleError("AGENT_INSTRUCTION_BUNDLE_INVALID", "artifact")
        kind = raw.get("kind")
        ref = raw.get("ref")
        digest = raw.get("digest")
        content = raw.get("content")
        if kind not in {"instruction", "role_overlay", "skill", "node_instruction"}:
            raise InstructionBundleError("AGENT_INSTRUCTION_BUNDLE_INVALID", "artifact kind")
        if not isinstance(ref, str) or not _safe_ref(ref) or ref in seen:
            raise InstructionBundleError("AGENT_INSTRUCTION_BUNDLE_INVALID", "artifact ref")
        if not isinstance(content, str) or digest != _sha256_text(content):
            raise InstructionBundleError("AGENT_INSTRUCTION_BUNDLE_DIGEST_MISMATCH", ref)
        seen.add(ref)
        artifacts.append({"kind": str(kind), "ref": ref, "digest": str(digest), "content": content})

    instructions = [item for item in artifacts if item["kind"] == "instruction"]
    overlays = [item for item in artifacts if item["kind"] == "role_overlay"]
    skills = [item for item in artifacts if item["kind"] == "skill"]
    nodes = [item for item in artifacts if item["kind"] == "node_instruction"]
    if len(nodes) != 1:
        raise InstructionBundleError("AGENT_NODE_INSTRUCTION_CARDINALITY_INVALID")
    _validate_node_instruction_ref(nodes[0]["ref"])
    for item in skills:
        parts = PurePosixPath(item["ref"]).parts
        if len(parts) != 3 or parts[0] != "skills" or parts[2] != "SKILL.md" or _SKILL_NAME_RE.fullmatch(parts[1]) is None:
            raise InstructionBundleError("AGENT_INSTRUCTION_BUNDLE_INVALID", item["ref"])

    expected = _bundle_digest(artifacts)
    if bundle.get("bundle_digest") != expected:
        raise InstructionBundleError("AGENT_INSTRUCTION_BUNDLE_DIGEST_MISMATCH", "bundle")

    canonical = {
        "schema_version": "1.0",
        "artifact_type": "agent-instruction-bundle",
        "instruction_refs": [item["ref"] for item in instructions],
        "instruction_digests": [item["digest"] for item in instructions],
        "role_overlay_refs": [item["ref"] for item in overlays],
        "role_overlay_digests": [item["digest"] for item in overlays],
        "skill_refs": [item["ref"] for item in skills],
        "skill_digests": [item["digest"] for item in skills],
        "node_instruction_ref": nodes[0]["ref"],
        "node_instruction_digest": nodes[0]["digest"],
        "artifacts": artifacts,
        "bundle_digest": expected,
    }
    # Ref/digest summaries are derived from artifacts, never trusted from input.
    return canonical


__all__ = [
    "InstructionBundleError",
    "resolve_agent_instruction_bundle",
    "validate_agent_instruction_bundle",
]
