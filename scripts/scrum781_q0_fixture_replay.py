#!/usr/bin/env python3
"""Q0 source-bound reconstructed fixture runner; no effect or gate authority.

Native runner is mandatory. Optional LangGraph drives the SAME pure steps;
its checkpoints are not native GWC events, DWO source state or LOAD_PROOF.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
from pathlib import Path
from typing import Any, Callable, TypedDict

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / ".gwc/tasks/SCRUM-781/fixtures/q0-c91-e52-reconstructed-v1.json"
RUN_ID = "scrum781-q0-fresh-20261010-r1"
BRANCH = "fix/SCRUM-781-q0-fresh-20261010-r1"
ADAPTER = "tools.node_architect.universal_run_epoch:replay_c91_incident"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class FixtureError(ValueError):
    """Stable fail-closed fixture verification error."""


class FixtureState(TypedDict, total=False):
    validated: bool
    actual: dict[str, Any]
    verified: bool


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def load_fixture(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    return json.loads(raw), digest(raw)


def validate_fixture(fixture: dict[str, Any], *, root: Path = ROOT) -> None:
    if (fixture.get("schema_id") != "gwc.q0.reconstructed-fixture.v1"
        or fixture.get("run_id") != RUN_ID
        or fixture.get("task_id") != "SCRUM-781"
        or fixture.get("runtime_epoch") != "UNIVERSAL_V2_DEVELOPMENT"
        or fixture.get("gate") != "UR.G2"):
        raise FixtureError("Q0_FIXTURE_IDENTITY_INVALID")
    bound = fixture.get("source_binding", {})
    if (bound.get("repository") != "nhatnguyenquang1838-coder/gwc"
        or bound.get("branch") != BRANCH
        or bound.get("baseline_sha") != "80a3995ce374d678eaeaf223d25959aba4ea8d35"
        or not SHA40.fullmatch(str(bound.get("baseline_sha", "")))):
        raise FixtureError("Q0_FIXTURE_SOURCE_BINDING_INVALID")
    plan_path = "core/node-architect/scrum781-q0-fresh-execution-plan-r2.json"
    checksum = str(bound.get("runtimeplan_sha256", ""))
    if bound.get("runtimeplan_path") != plan_path or not SHA256.fullmatch(checksum):
        raise FixtureError("Q0_FIXTURE_PLAN_BINDING_INVALID")
    if digest((root / plan_path).read_bytes()) != "sha256:" + checksum:
        raise FixtureError("Q0_FIXTURE_PLAN_DRIFT")
    incident = fixture.get("incident", {})
    if (incident.get("parent_id") != "DWO-LOGIN-AUTH-R1"
        or incident.get("covered_subcase") != "C91/E52 legacy-G0G1-controller-block"
        or incident.get("original_trace_status") != "MISSING"
        or incident.get("provenance_class") != "RECONSTRUCTED_SOURCE_BOUND"
        or incident.get("previous_failure_signature") != "NEEDS_EXACT_HITL"
        or not incident.get("source_refs")):
        raise FixtureError("Q0_FIXTURE_PROVENANCE_INVALID")
    replay = fixture.get("replay", {})
    if replay.get("adapter") != ADAPTER or replay.get("inputs") != {
        "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
        "legacy_g01_package_present": False,
        "universal_native_state_valid": True,
    }:
        raise FixtureError("Q0_FIXTURE_REPLAY_INPUT_INVALID")
    if replay.get("expected") != {
        "outcome": "UNIVERSAL_CONTINUES",
        "needs_exact_hitl": False,
        "advance_beyond_old_failure": True,
        "first_state_beyond_failure": "UR.G1_TYPED_CONTROLLER_NEXT",
    }:
        raise FixtureError("Q0_FIXTURE_ORACLE_INVALID")
    if fixture.get("dwo_v2_projection_contract") != {
        "source_profile": "DEV_NATIVE", "sync_state": "LIVE",
        "semantic_qualification": "PENDING", "authority_state": "NOT_APPLICABLE",
    }:
        raise FixtureError("Q0_DWO_V2_PROJECTION_CONTRACT_INVALID")


def execute_replay(fixture: dict[str, Any], executor: Callable[..., dict] | None = None) -> dict:
    if executor is None:
        module = importlib.import_module("tools.node_architect.universal_run_epoch")
        executor = getattr(module, "replay_c91_incident")
    return executor(**fixture["replay"]["inputs"])


def verify_replay(fixture: dict[str, Any], actual: dict) -> None:
    for key, expected in fixture["replay"]["expected"].items():
        if key not in actual or actual[key] != expected:
            raise FixtureError("Q0_FIXTURE_REPLAY_MISMATCH:" + key)
    if actual.get("authority_granted") is True or actual.get("executed_effects"):\n        raise FixtureError("Q0_FIXTURE_UNAUTHORIZED_EFFECT_CLAIM")\n    if actual.get("needs_exact_hitl") or not actual.get("advance_beyond_old_failure"):
        raise FixtureError("Q0_FIXTURE_DID_NOT_ADVANCE")


def run_fixture(fixture: dict[str, Any], *, root: Path = ROOT,
                engine: str = "native", executor: Callable[..., dict] | None = None,
                thread_id: str | None = None) -> dict:
    def validate(_: FixtureState) -> FixtureState:
        validate_fixture(fixture, root=root)
        return {"validated": True}

    def replay(_: FixtureState) -> FixtureState:
        return {"actual": execute_replay(fixture, executor=executor)}

    def verify(state: FixtureState) -> FixtureState:
        verify_replay(fixture, state["actual"])
        return {"verified": True}

    if engine == "native":
        validate({})
        state = replay({})
        verify(state)
        checkpoint = "NONE"
    elif engine == "langgraph":
        try:
            from langgraph.graph import StateGraph, START, END
            from langgraph.checkpoint.memory import MemorySaver
        except ImportError as exc:
            raise FixtureError("LANGGRAPH_BACKEND_UNAVAILABLE") from exc
        graph = StateGraph(FixtureState)
        graph.add_node("validate", validate)
        graph.add_node("replay", replay)
        graph.add_node("verify", verify)
        graph.add_edge(START, "validate")
        graph.add_edge("validate", "replay")
        graph.add_edge("replay", "verify")
        graph.add_edge("verify", END)
        compiled = graph.compile(checkpointer=MemorySaver())
        state = compiled.invoke({}, {"configurable": {"thread_id": thread_id or RUN_ID + ":c91-e52"}})
        checkpoint = "EPHEMERAL_MECHANICS_ONLY"
    else:
        raise FixtureError("Q0_FIXTURE_ENGINE_UNKNOWN")
    return {
        "run_id": RUN_ID, "fixture_id": fixture["fixture_id"],
        "engine": engine, "checkpoint_class": checkpoint,
        "result": "RECONSTRUCTED_SUBCASE_PASS",
        "observed": state["actual"],
        "incident_provenance": "RECONSTRUCTED_SOURCE_BOUND",
        "authentic_dwo_login_replay": False,
        "q0_l3_qualified": False,
        "native_gate_receipt": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--engine", choices=["native", "langgraph"], default="native")
    parser.add_argument("--out", type=Path, help="Optional explicit local evidence JSON destination")
    args = parser.parse_args()
    try:
        fixture, fixture_digest = load_fixture(args.fixture)
        result = run_fixture(fixture, engine=args.engine)
        result["fixture_digest"] = fixture_digest
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        result = {"result": "BLOCKED", "reason_code": str(exc), "q0_l3_qualified": False}
        print(json.dumps(result, sort_keys=True))
        return 2
    output = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.out:
        args.out.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
