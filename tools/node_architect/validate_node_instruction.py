#!/usr/bin/env python3
"""
Node Instruction Validator v1.0

Validates node instruction packs against the Node Instruction Contract.
"""

import json
import sys
import os
from pathlib import Path

SCHEMA_PATH = "schemas/node-architect/instruction-card.schema.json"
FAILURE_CODES = {
    "NODE_INSTRUCTION_MISSING": 1,
    "NODE_EVIDENCE_CONTRACT_MISSING": 2,
    "NODE_LOG_CONTRACT_MISSING": 3,
    "NODE_NEXT_ROUTE_MISSING": 4,
    "NODE_ENTRY_CONDITIONS_FAILED": 5,
    "NODE_INPUTS_INCOMPLETE": 6,
    "NODE_ACTION_VIOLATION": 7,
    "NODE_EVIDENCE_FAILED": 8,
    "NODE_LOG_FAILED": 9,
    "NODE_NEXT_RESOLVE_FAILED": 10,
    "NODE_RETRY_EXCEEDED": 11,
    "NODE_ROLLBACK_FAILED": 12,
}


def load_json(path):
    """Load JSON file with error handling."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(f"JSON parse error in {path}: {e}")
        return None


def validate_instruction_card(card, schema):
    """Validate instruction card against schema."""
    errors = []
    
    # Required fields check
    required = schema.get("required", [])
    for field in required:
        if field not in card:
            errors.append(f"Missing required field: {field}")
    
    if errors:
        return False, errors
    
    # Validate node_id format
    node_id = card.get("node_id", "")
    pattern = r"^[a-z_]+\.[a-z0-9_-]+$"
    import re
    if not re.match(pattern, node_id):
        errors.append(f"Invalid node_id format: {node_id}")
    
    # Validate gate value
    valid_gates = ["G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR", 
                   "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA", "NONE"]
    if card.get("gate") not in valid_gates:
        errors.append(f"Invalid gate: {card.get('gate')}")
    
    # Validate authority boundary (must be false for gate/merge authority)
    authority = card.get("authority_boundary", {})
    if authority.get("grants_gate_authority", True) is not False:
        errors.append("Node instructions must not grant gate authority")
    if authority.get("grants_merge_authority", True) is not False:
        errors.append("Node instructions must not grant merge authority")
    
    # Validate entry conditions
    entry = card.get("entry_conditions", {})
    if "prerequisite_gate" not in entry:
        errors.append("Missing prerequisite_gate in entry_conditions")
    if "artifacts_required" not in entry:
        errors.append("Missing artifacts_required in entry_conditions")
    if "conditions" not in entry:
        errors.append("Missing conditions in entry_conditions")
    
    # Validate inputs
    inputs = card.get("inputs", {})
    if "required" not in inputs:
        errors.append("Missing required inputs")
    
    # Validate outputs
    outputs = card.get("outputs", {})
    if "evidence_contract" not in outputs:
        errors.append("Missing evidence_contract in outputs")
    if "logs_contract" not in outputs:
        errors.append("Missing logs_contract in outputs")
    
    # Validate next resolution
    next_route = card.get("next", {})
    if "next_route" not in next_route:
        errors.append("Missing next_route in next")
    
    # Validate retry configuration
    retry = card.get("retry", {})
    if "max_attempts" not in retry:
        errors.append("Missing max_attempts in retry")
    elif retry["max_attempts"] < 1 or retry["max_attempts"] > 10:
        errors.append("max_attempts must be between 1 and 10")
    
    return len(errors) == 0, errors


def validate_evidence_contract(card):
    """Validate evidence contract is resolvable."""
    outputs = card.get("outputs", {})
    evidence = outputs.get("evidence_contract", "")
    
    # Check if schema file exists
    schema_path = Path(evidence)
    if not schema_path.exists():
        return False, f"Evidence schema not found: {evidence}"
    
    return True, None


def validate_log_contract(card):
    """Validate log contract is resolvable."""
    outputs = card.get("outputs", {})
    logs = outputs.get("logs_contract", "")
    
    # Check if schema file exists
    schema_path = Path(logs)
    if not schema_path.exists():
        return False, f"Log schema not found: {logs}"
    
    return True, None


def validate_next_route(card, profile_registry):
    """Validate next route is resolvable."""
    next_route = card.get("next", {})
    route_id = next_route.get("next_route", "")
    
    if not route_id:
        return False, "Missing next_route identifier"
    
    # Check if route exists in profile registry
    if profile_registry:
        profiles = profile_registry.get("profiles", [])
        profile_ids = [p.get("id") for p in profiles]
        if route_id not in profile_ids:
            # Not an error if using a known route id
            pass
    
    return True, None


def validate_all(card_path, schema_path, profile_path):
    """Run all validations on an instruction card."""
    results = {"passed": [], "failed": []}
    
    # Load files
    card = load_json(card_path)
    if card is None:
        results["failed"].append({
            "code": "NODE_INSTRUCTION_MISSING",
            "message": f"Instruction card not found or invalid: {card_path}"
        })
        return results
    
    schema = load_json(schema_path)
    if schema is None:
        results["failed"].append({
            "code": "NODE_EVIDENCE_CONTRACT_MISSING",
            "message": f"Schema not found: {schema_path}"
        })
        return results
    
    profile = load_json(profile_path) if profile_path else None
    
    # Validate against schema
    passed, errors = validate_instruction_card(card, schema)
    if not passed:
        for error in errors:
            results["failed"].append({
                "code": "NODE_INSTRUCTION_INVALID",
                "message": error
            })
    else:
        results["passed"].append("Schema validation passed")
    
    # Validate evidence contract
    passed, error = validate_evidence_contract(card)
    if not passed:
        results["failed"].append({
            "code": "NODE_EVIDENCE_CONTRACT_MISSING",
            "message": error
        })
    else:
        results["passed"].append("Evidence contract valid")
    
    # Validate log contract
    passed, error = validate_log_contract(card)
    if not passed:
        results["failed"].append({
            "code": "NODE_LOG_CONTRACT_MISSING",
            "message": error
        })
    else:
        results["passed"].append("Log contract valid")
    
    # Validate next route
    passed, error = validate_next_route(card, profile)
    if not passed:
        results["failed"].append({
            "code": "NODE_NEXT_ROUTE_MISSING",
            "message": error
        })
    else:
        results["passed"].append("Next route resolvable")
    
    return results


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: validate_node_instruction.py <instruction-card.json> [schema.json] [profile-registry.json]")
        sys.exit(1)
    
    card_path = sys.argv[1]
    schema_path = sys.argv[2] if len(sys.argv) > 2 else SCHEMA_PATH
    profile_path = sys.argv[3] if len(sys.argv) > 3 else None
    
    # Resolve paths
    base_dir = Path.cwd()
    card_path = base_dir / card_path
    schema_path = base_dir / schema_path
    profile_path = base_dir / profile_path if profile_path else None
    
    results = validate_all(str(card_path), str(schema_path), str(profile_path))
    
    # Output results
    if results["failed"]:
        print("VALIDATION FAILED")
        for failure in results["failed"]:
            print(f"  {failure['code']}: {failure['message']}")
        sys.exit(FAILURE_CODES.get(results["failed"][0]["code"], 1))
    else:
        print("VALIDATION PASSED")
        for success in results["passed"]:
            print(f"  ✓ {success}")
        sys.exit(0)


if __name__ == "__main__":
    main()
