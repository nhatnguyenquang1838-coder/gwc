"""Test for request-intake evaluator."""
from __future__ import annotations
import json, re
from node_architect.request_intake import normalize_request_intake, _validate_artifact

SHA40 = re.compile(r"^[0-9a-f]{40}$")

def test_accept_case():
    """Test a valid request that should be accepted."""
    art = normalize_request_intake(
        task_id="SCRUM-298",
        repository="nhatnguyenquang1838-coder/gwc",
        base_sha="cff9fb1bbe55493ccc8bc7b48e48f613521a58b2",
        request={
            "intent": "Normalize user request into typed intake record",
            "outcome": "Typed intake record with intent, outcome, constraints",
            "constraints": [
                "Input must be canonical request shape",
                "No ambiguous or conflicting signals"
            ],
            "exclusions": [
                "Production runtime behavior",
                "Deployment or migration operations"
            ],
            "entry_guards": [
                "G0_CONTEXT",
                "read_only authority_boundary"
            ]
        }
    )
    assert art["outcome"] == "ACCEPTED"
    assert art["reason_code"] == "ACCEPTED"
    assert "ACCEPTED" in art["reason_codes"]
    assert art["task_id"] == "SCRUM-298"
    assert art["repository"] == "nhatnguyenquang1838-coder/gwc"
    assert SHA40.fullmatch(art["base_sha"])
    assert _validate_artifact(art) == []

def test_malformed_input():
    """Test malformed request input."""
    art = normalize_request_intake(
        task_id="SCRUM-298",
        repository="nhatnguyenquang1838-coder/gwc",
        base_sha="cff9fb1bbe55493ccc8bc7b48e48f613521a58b2",
        request={}  # missing required fields
    )
    assert art["outcome"] == "BLOCKED"
    assert art["reason_code"] == "MALFORMED_INPUT"
    assert "MALFORMED_INPUT" in art["reason_codes"]
    assert _validate_artifact(art) == []

def test_ambiguous_intent():
    """Test ambiguous intent."""
    art = normalize_request_intake(
        task_id="SCRUM-298",
        repository="nhatnguyenquang1838-coder/gwc",
        base_sha="cff9fb1bbe55493ccc8bc7b48e48f613521a58b2",
        request={
            "intent": "test",  # too generic
            "outcome": "something",
            "constraints": ["some constraint"],
            "exclusions": ["some exclusion"],
            "entry_guards": ["G0_CONTEXT"]  # missing read_only guard
        }
    )
    assert art["outcome"] == "BLOCKED"
    # Should be either AMBIGUOUS_INTENT or SCOPE_DRIFT based on precedence
    assert art["reason_code"] in {"AMBIGUOUS_INTENT", "SCOPE_DRIFT"}
    assert _validate_artifact(art) == []

def test_scope_drift():
    """Test scope drift into production authority."""
    art = normalize_request_intake(
        task_id="SCRUM-298",
        repository="nhatnguyenquang1838-coder/gwc",
        base_sha="cff9fb1bbe55493ccc8bc7b48e48f613521a58b2",
        request={
            "intent": "Deploy to production with merge authority",
            "outcome": "Production deployment",
            "constraints": ["Must deploy"],
            "exclusions": [],
            "entry_guards": ["G0_CONTEXT", "read_only authority_boundary"]
        }
    )
    assert art["outcome"] == "BLOCKED"
    assert art["reason_code"] == "SCOPE_DRIFT"
    assert _validate_artifact(art) == []

def test_artifact_validation():
    """Test that valid artifacts pass validation."""
    art = normalize_request_intake(
        task_id="SCRUM-298",
        repository="nhatnguyenquang1838-coder/gwc",
        base_sha="cff9fb1bbe55493ccc8bc7b48e48f613521a58b2",
        request={
            "intent": "Normalize request",
            "outcome": "Normalized intake",
            "constraints": ["Canonical input only"],
            "exclusions": ["No prod ops"],
            "entry_guards": ["G0_CONTEXT", "read_only authority_boundary"]
        }
    )
    assert _validate_artifact(art) == []
    # Tamper with artifact
    tampered = dict(art)
    tampered["request"]["intent"] = "tampered"
    assert _validate_artifact(tampered) != []

if __name__ == "__main__":
    test_accept_case()
    test_malformed_input()
    test_ambiguous_intent()
    test_scope_drift()
    test_artifact_validation()
    print("All tests PASS")