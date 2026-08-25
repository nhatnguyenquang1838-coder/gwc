import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.node_architect.gate_node_routes import FAMILY_GATE_BINDINGS, ROUTE_PACKS, build_route_coverage, select_route_pack

FAMILIES = {
    "intake_context", "gate_authority", "repo_delivery", "runtime_checkpoint",
    "validation_quality", "sync_projection", "package_export", "failure_recovery", "scale_control"
}


def registry():
    return {"nodes": [{"id": f"{family}.n", "family": family} for family in sorted(FAMILIES)]}


def test_all_nine_families_have_gate_bindings():
    assert set(FAMILY_GATE_BINDINGS) == FAMILIES


def test_six_source_backed_route_packs_exist():
    assert set(ROUTE_PACKS) == {"RP-01", "RP-02", "RP-03", "RP-04", "RP-05", "RP-06"}
    assert all(pack["runtime_executable"] for pack in ROUTE_PACKS.values())
    assert all(pack["provenance"]["source"] == "SCRUM-588" for pack in ROUTE_PACKS.values())


def test_every_family_gets_route_coverage():
    coverage = build_route_coverage(registry())
    assert len(coverage) == 9
    assert all(item["route_packs"] for item in coverage)
    assert all(item["route_bound"] for item in coverage)


def test_scenario_selection_is_typed_and_not_catalogue_order():
    assert select_route_pack("standard_pr_delivery") == "RP-01"
    assert select_route_pack("ci_failure") == "RP-03"
    assert select_route_pack("unknown") is None


def test_repository_canonical_81_all_have_route_coverage():
    payload = json.loads((ROOT / "core/node-architect/node-registry.json").read_text(encoding="utf-8"))
    coverage = build_route_coverage(payload)
    assert len(coverage) == 81
    assert len({item["node_id"] for item in coverage}) == 81
    assert all(item["route_bound"] for item in coverage)
