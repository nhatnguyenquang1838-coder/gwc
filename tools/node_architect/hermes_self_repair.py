"""Non-admitted self-repair extension: evidence mechanics, never live Q0 proof.

Actual fix/Git/reload/replay effects belong to a separately admitted host.
Synthetic mode exercises validation, ordering and crash safety without claiming
original-incident provenance or creating a GWC run/gate/approval.
"""

# ruff: noqa: SIM102 -- keep each stage guard separate from its evidence predicate
from __future__ import annotations

import fcntl
import json
import os
import re
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import CodeType, FunctionType

from .hermes_workflow_compiler import canonical, digest

REPAIR_DEFINITION_DIGEST = (
    "sha256:7acafe958d2ba3eb016ad0ef3a53b48e3c485048d36a4f1e4659f1a7d779aeca"
)


def local_load_proof(source_root, module_names, instruction_refs, profile):
    """Observe this Python process only; not a live-host instruction admission.

    Record loaded function bytecode separately from current disk content and
    compare with fresh compilation. Git HEAD is deliberately not load proof.
    """
    root = Path(source_root).resolve()

    def code_identity(code):
        # Marshal object interning differs between loaded and freshly compiled
        # code. Compare semantic bytecode/metadata, not its reference encoding.
        return digest(
            {
                "bytecode": code.co_code.hex(),
                "names": code.co_names,
                "varnames": code.co_varnames,
                "freevars": code.co_freevars,
                "cellvars": code.co_cellvars,
                "flags": code.co_flags,
                "argcount": code.co_argcount,
                "kwonly": code.co_kwonlyargcount,
                "posonly": code.co_posonlyargcount,
                "constants": [constant_identity(v) for v in code.co_consts],
            }
        )

    def constant_identity(value):
        if isinstance(value, CodeType):
            return {"code": code_identity(value)}
        if isinstance(value, frozenset):
            return {"frozenset": sorted(canonical(constant_identity(v)) for v in value)}
        if isinstance(value, tuple):
            return {"tuple": [constant_identity(v) for v in value]}
        return {"literal": repr(value)}

    def bound(path):
        path = Path(path).resolve()
        if not path.is_relative_to(root):
            raise ValueError("LOAD_SURFACE_OUTSIDE_SOURCE_ROOT")
        return path

    modules = []
    for name in module_names:
        module = sys.modules.get(name)
        if module is None or not getattr(module, "__file__", None):
            raise ValueError("MODULE_NOT_LOADED")
        path = bound(module.__file__)
        source = path.read_bytes()
        compiled = compile(source, str(path), "exec", dont_inherit=True)
        disk_codes = {}

        def collect(code, prefix="", disk_codes=disk_codes):
            for child in code.co_consts:
                if isinstance(child, CodeType):
                    disk_codes[
                        getattr(child, "co_qualname", prefix + child.co_name)
                    ] = code_identity(child)
                    collect(child, prefix + child.co_name + ".")

        collect(compiled)
        loaded = {}
        generated = {}

        def observe(value, name=name, loaded=loaded, generated=generated, path=path):
            if isinstance(value, (staticmethod, classmethod)):
                value = value.__func__
            if isinstance(value, property):
                for accessor in (value.fget, value.fset, value.fdel):
                    if accessor is not None:
                        observe(accessor)
                return
            if isinstance(value, FunctionType) and value.__module__ == name:
                destination = (
                    loaded
                    if Path(value.__code__.co_filename).resolve() == path
                    else generated
                )
                destination[value.__qualname__] = code_identity(value.__code__)
            elif isinstance(value, type) and value.__module__ == name:
                for member in vars(value).values():
                    observe(member)

        for value in vars(module).values():
            observe(value)
        modules.append(
            {
                "name": name,
                "path": str(path),
                "disk_content_digest": "sha256:" + sha256(source).hexdigest(),
                "loaded_code_digest": digest(loaded),
                "loaded_function_count": len(loaded),
                "source_functions": loaded,
                "generated_functions": generated,
                "mismatched_source_functions": [
                    k for k, v in loaded.items() if disk_codes.get(k) != v
                ],
                "loaded_functions_match_disk": bool(loaded)
                and all(disk_codes.get(k) == v for k, v in loaded.items()),
            }
        )
    instructions = [
        {
            "path": str(path),
            "content_digest": "sha256:" + sha256(path.read_bytes()).hexdigest(),
            "proof_kind": "CONTENT_READ_NOT_HOST_PROMPT_ADMISSION",
        }
        for path in (bound(root / ref) for ref in instruction_refs)
    ]
    return {
        "source_root": str(root),
        "process_id": os.getpid(),
        "python_executable": sys.executable,
        "modules": modules,
        "instructions": instructions,
        "profile_digest": digest(profile),
        "host_admitted": False,
        "authority_granted": False,
    }


class SelfRepairMachine:
    def __init__(self, runtime, definition, incident, adapter, binding):
        self.runtime, self.adapter = runtime, adapter
        self.definition, self.incident, self.binding = (
            deepcopy(definition),
            deepcopy(incident),
            deepcopy(binding),
        )
        if digest(definition) != REPAIR_DEFINITION_DIGEST:
            raise ValueError("UNSUPPORTED_REPAIR_DEFINITION")
        if (
            adapter.evidence_mode != "SYNTHETIC"
            or incident.get("evidence_mode") != "SYNTHETIC"
        ):
            raise ValueError("BASE_LIVE_QUALIFICATION_REQUIRED")
        runtime._qualify(binding)
        if (
            definition["binding"]["run_id"] != runtime.graph.run_id
            or definition["binding"]["gate"] != runtime.graph.plan["current_gate"]
        ):
            raise ValueError("REPAIR_PLAN_BINDING_MISMATCH")
        fixture = json.loads(Path(incident["fixture_ref"]).read_text())
        if (
            digest(fixture) != incident.get("fixture_digest")
            or incident.get("source_sha") != binding["source_sha"]
        ):
            raise ValueError("INCIDENT_PROVENANCE_MISMATCH")
        self.routes = {node["id"]: node["routes"] for node in definition["nodes"]}
        self.identity = digest(
            {"binding": binding, "incident": incident, "definition": definition}
        )
        with runtime._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS repair (identity TEXT PRIMARY KEY, state TEXT NOT NULL)"
            )

    def _load(self):
        with self.runtime._connect() as db:
            row = db.execute(
                "SELECT state FROM repair WHERE identity=?", (self.identity,)
            ).fetchone()
        return (
            json.loads(row[0])
            if row
            else {
                "next": "classify_failure",
                "evidence": {},
                "visits": {},
                "authority_granted": False,
                "live_qualified": False,
                "status": "ENGINE_MECHANICS",
            }
        )

    def _save(self, state):
        with self.runtime._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO repair VALUES (?,?)",
                (self.identity, canonical(state)),
            )

    def tick(self, *, max_nodes=1):
        self.runtime._qualify(self.binding)
        if (
            digest(json.loads(Path(self.incident["fixture_ref"]).read_text()))
            != self.incident["fixture_digest"]
        ):
            raise ValueError("INCIDENT_PROVENANCE_MISMATCH")
        if type(max_nodes) is not int or not 1 <= max_nodes <= 100:
            raise ValueError("INVALID_REPAIR_BUDGET")
        with self.runtime.path.with_suffix(".writer.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("WRITER_OVERLAP") from None
            state = self._load()
            for _ in range(max_nodes):
                node = state["next"]
                if node in ("persist_progress", "evaluate_blocker"):
                    break
                key = digest(
                    {
                        "identity": self.identity,
                        "node": node,
                        "visit": state["visits"].get(node, 0),
                    }
                )
                receipt = self.runtime._once(
                    "SELF_REPAIR",
                    key,
                    {"node": node, "evidence": state["evidence"]},
                    lambda node=node, key=key: self.adapter.run_repair_node(
                        node, deepcopy(state["evidence"]), key
                    ),
                    self.adapter.read_repair_node,
                )
                if (
                    receipt.get("binding_digest") != digest(self.binding)
                    or receipt.get("node") != node
                    or receipt.get("evidence_mode") != "SYNTHETIC"
                ):
                    raise ValueError("REPAIR_RECEIPT_BINDING_MISMATCH")
                route = receipt.get("route")
                if route not in self.routes[node]:
                    raise ValueError("UNSUPPORTED_REPAIR_ROUTE")
                proof = receipt.get("evidence", {})
                self._validate(node, route, proof, state["evidence"])
                state["evidence"][node] = proof
                if node == "broader_tests" and route == "pass":
                    state["status"] = "ENGINE_FIX_IMPLEMENTED"
                if node == "load_proof" and route == "identity_matches":
                    state["status"] = "ENGINE_FIX_LOADED"
                if (
                    node == "replay_original"
                    and route == "progress_beyond_original_failure"
                ):
                    state["status"] = "ENGINE_REPAIR_REPLAY_VERIFIED"
                state["visits"][node] = state["visits"].get(node, 0) + 1
                state["next"] = self.routes[node][route]
                if state["next"] in (
                    "analyze_cause",
                    "recover_source",
                    "runtime_reload",
                ):
                    order = list(self.routes)
                    boundary = order.index(state["next"])
                    state["evidence"] = {
                        k: v
                        for k, v in state["evidence"].items()
                        if order.index(k) < boundary
                    }
                    state["status"] = "ENGINE_MECHANICS"
                self._save(state)
            return deepcopy(state)

    def _validate(self, node, route, proof, evidence):
        if node == "recover_source" and route == "verified":
            if (
                proof.get("fixture_digest") != self.incident["fixture_digest"]
                or proof.get("source_sha") != self.binding["source_sha"]
                or proof.get("fixture_ref") != self.incident["fixture_ref"]
            ):
                raise ValueError("SOURCE_RECOVERY_NOT_EXACT")
        if node == "capture_red" and route == "authentic_red":
            if (
                proof.get("source_sha") != self.binding["source_sha"]
                or proof.get("fixture_digest") != self.incident["fixture_digest"]
                or type(proof.get("returncode")) is not int
                or proof["returncode"] == 0
                or not proof.get("exact_test_command")
                or not proof.get("failure_signature")
                or proof["failure_signature"] not in proof.get("output", "")
            ):
                raise ValueError("RED_NOT_AUTHENTIC")
        if node == "analyze_cause" and route == "ready" and not proof.get("cause_ref"):
            raise ValueError("CAUSE_EVIDENCE_MISSING")
        if node == "plan_minimal_fix" and route == "within_existing_scope":
            from fnmatch import fnmatchcase
            from pathlib import PurePosixPath

            target = proof.get("target", "")
            if (
                not target
                or PurePosixPath(target).is_absolute()
                or ".." in PurePosixPath(target).parts
                or not any(
                    fnmatchcase(target, pattern)
                    for pattern in self.binding["writable_targets"]
                )
                or proof.get("action")
                not in self.runtime.graph.plan["scope"]["allowed_actions"]
                or proof.get("action")
                in self.runtime.graph.plan["scope"]["denied_actions"]
                or proof.get("scope_check") is not True
                or proof.get("single_writer") != self.binding["writer_id"]
            ):
                raise ValueError("FIX_SCOPE_OR_WRITER")
        if node == "apply_fix" and route == "effect_recorded":
            if (
                proof.get("scope_check") is not True
                or proof.get("single_writer") != self.binding["writer_id"]
                or not proof.get("diff_ref")
                or not proof.get("fixed_sha")
                or "capture_red" not in evidence
                or "plan_minimal_fix" not in evidence
            ):
                raise ValueError("FIX_SCOPE_OR_WRITER")
        if node in ("focused_green", "broader_tests") and route == "pass":
            if (
                proof.get("tested_sha")
                != evidence.get("apply_fix", {}).get("fixed_sha")
                or proof.get("returncode") != 0
                or type(proof.get("returncode")) is not int
                or not proof.get("exact_test_command")
                or not proof.get("receipt_ref")
                or (node == "broader_tests" and "focused_green" not in evidence)
            ):
                raise ValueError("GREEN_IDENTITY_OR_RECEIPT_MISMATCH")
        candidate = evidence.get("apply_fix", {}).get("fixed_sha")
        if node == "commit_readback" and route == "verified":
            if (
                proof.get("additive_commit_sha") != candidate
                or proof.get("remote_sha") != candidate
                or proof.get("parent_sha") != self.binding["source_sha"]
                or candidate == self.binding["source_sha"]
                or not re.fullmatch("[0-9a-f]{40}", candidate or "")
                or proof.get("exact_readback") is not True
                or proof.get("additive") is not True
                or "broader_tests" not in evidence
                or proof.get("synthetic_identity") is not True
            ):
                raise ValueError("ADDITIVE_COMMIT_READBACK_MISMATCH")
        if node == "runtime_reload" and route == "reloaded":
            if (
                proof.get("loaded_sha") != candidate
                or not proof.get("runtime_process_session")
                or "commit_readback" not in evidence
            ):
                raise ValueError("RELOAD_IDENTITY_MISMATCH")
        if node == "load_proof" and route == "identity_matches":
            surfaces = proof.get("module_and_instruction_digests", {})
            if (
                proof.get("loaded_sha") != candidate
                or proof.get("profile_digest") != self.binding.get("profile_digest")
                or proof.get("runtime_process_session")
                != evidence.get("runtime_reload", {}).get("runtime_process_session")
                or not all(
                    isinstance(surfaces.get(kind), dict)
                    and surfaces[kind]
                    and all(
                        re.fullmatch("sha256:[0-9a-f]{64}", v or "")
                        for v in surfaces[kind].values()
                    )
                    for kind in ("modules", "instructions")
                )
            ):
                raise ValueError("LOAD_PROOF_INCOMPLETE_OR_MISMATCH")
        if node == "invalidate_derivatives" and route == "completed":
            invalidated, regenerated = (
                proof.get("invalidated", []),
                proof.get("regenerated", []),
            )
            required = self.binding.get("dependent_artifacts", ["contract", "plan"])
            if (
                set(invalidated) != set(required)
                or len(invalidated) != len(set(invalidated))
                or {item.get("artifact") for item in regenerated} != set(required)
                or len(regenerated) != len(required)
                or any(
                    item.get("loaded_sha") != candidate
                    or not re.fullmatch("sha256:[0-9a-f]{64}", item.get("digest", ""))
                    for item in regenerated
                )
                or "load_proof" not in evidence
            ):
                raise ValueError("DERIVATIVE_INVALIDATION_OR_REGENERATION_MISSING")
        if node == "replay_original" and route == "progress_beyond_original_failure":
            if (
                proof.get("original_fixture_digest") != self.incident["fixture_digest"]
                or proof.get("previous_failure_state")
                != self.incident["previous_failure_state"]
                or not proof.get("readback_ref")
                or proof.get("advanced_beyond_failure") is not True
                or proof.get("legal_progress") is not True
                or proof.get("loaded_sha") != candidate
                or not proof.get("first_state_beyond_failure")
                or proof["first_state_beyond_failure"]
                == self.incident["previous_failure_state"]
                or "invalidate_derivatives" not in evidence
                or "load_proof" not in evidence
            ):
                raise ValueError("ORIGINAL_REPLAY_NOT_VERIFIED")
