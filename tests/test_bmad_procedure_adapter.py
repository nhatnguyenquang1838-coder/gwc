import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validator", ROOT / "tools" / "validate_bmad_procedure_adapter.py")
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(validator)

def test_contract_validator_passes():
    report = validator.validate(ROOT)
    assert report["status"] == "PASS", report["failures"]

def test_procedure_registry_is_complete():
    contract = json.loads((ROOT / "core/integration/bmad-procedure-adapter-contract.json").read_text())
    assert {p["id"] for p in contract["registry"]["procedures"]} == validator.REQUIRED_PROCEDURES

def test_scope_violation_rejects_before_side_effects():
    examples = json.loads((ROOT / "core/integration/examples/bmad-procedure-adapter-examples.json").read_text())["examples"]
    rejected = next(e for e in examples if e["id"] == "scope-violation")
    assert rejected["result"]["status"] == "REJECTED"
    assert rejected["result"]["failure_code"] == "SCOPE_VIOLATION"
    assert rejected["result"]["changed_paths"] == []

def test_review_is_read_only_and_non_authoritative():
    examples = json.loads((ROOT / "core/integration/examples/bmad-procedure-adapter-examples.json").read_text())["examples"]
    review = next(e for e in examples if e["id"] == "review-only")
    assert review["request"]["permission"]["mode"] == "read_only_analysis"
    assert review["result"]["changed_paths"] == []
    assert review["result"]["recommendation"]["type"] == "BLOCK"

def test_ready_unpublished_provider_is_exactly_pinned():
    contract = json.loads((ROOT / "core/integration/bmad-procedure-adapter-contract.json").read_text())
    provider = contract["registry"]["provider"]
    assert provider["state"] == "ready-unpublished"
    assert provider["source_commit"] == "bb45db4aa4496c69239f9c0629c290fd1b072fc9"
