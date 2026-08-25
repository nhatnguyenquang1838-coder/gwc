from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.node_architect.node_executability import build_qualification_records, validate_canonical_coverage


def sample_registry(count=2):
    nodes=[]
    for i in range(count):
        nodes.append({
            "id": f"family.node-{i}",
            "family": "repo_delivery",
            "version": "1.0.0",
            "maturity": "candidate" if i == 0 else "experimental",
            "source_status": "canonical_explicit" if i == 0 else "proposed_registry_slot",
            "effect_class": "read_only",
            "authority_class": "human_required",
            "idempotency": "readback_required",
            "suspension": {"suspendable": False, "resume_metadata": []},
        })
    return {"declared_slot_count": count, "nodes": nodes}


def test_maturity_does_not_imply_runtime_executable():
    records = build_qualification_records(sample_registry())
    assert records[0]["executability_level"] == "E1_INSTRUCTION_READY"
    assert records[0]["runtime_executable"] is False
    assert records[0]["qualification"]["adapter_bound"] is False
    assert records[0]["qualification"]["route_bound"] is False


def test_instruction_contract_has_entry_do_branches_exit_next():
    record = build_qualification_records(sample_registry())[0]
    assert set(record["instruction_contract"]) == {"entry", "do", "branches", "exit", "next"}
    assert record["instruction_contract"]["do"]["mode"] == "shadow_readonly"
    assert record["instruction_contract"]["do"]["authority"] == "none"


def test_canonical_coverage_requires_exactly_81_unique_ids():
    errors = validate_canonical_coverage(sample_registry(2))
    assert "CANONICAL_NODE_COUNT_MISMATCH" in errors


def test_duplicate_ids_fail_closed():
    registry = sample_registry(81)
    registry["nodes"][-1]["id"] = registry["nodes"][0]["id"]
    errors = validate_canonical_coverage(registry)
    assert "CANONICAL_NODE_ID_DUPLICATE" in errors


def test_repository_registry_has_exactly_81_unique_nodes():
    registry = json.loads((ROOT / "core/node-architect/node-registry.json").read_text(encoding="utf-8"))
    assert validate_canonical_coverage(registry) == []
    records = build_qualification_records(registry)
    assert len(records) == 81
    assert len({record["node_id"] for record in records}) == 81
