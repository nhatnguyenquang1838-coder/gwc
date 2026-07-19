from pathlib import Path
import json
import unittest

import jsonschema


ROOT = Path(__file__).resolve().parents[1]


class ConnectorTraceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(
            (ROOT / "schemas/connector-trace.schema.json").read_text(encoding="utf-8")
        )

    def test_success_trace_is_valid(self):
        payload = {
            "ok": True,
            "trace": {
                "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                "operation": "github_create_branch",
                "stage": "completed",
                "connector_received": True,
                "policy_checked": True,
                "upstream_provider": "github",
                "upstream_attempted": True,
                "provider_request_id": "ABC1:DEF2:12345",
                "http_status": 201,
            },
            "error": None,
        }
        jsonschema.validate(payload, self.schema)

    def test_policy_rejection_does_not_claim_upstream_call(self):
        payload = {
            "ok": False,
            "trace": {
                "trace_id": "trace-policy-reject",
                "operation": "github_create_branch",
                "stage": "connector_policy",
                "connector_received": True,
                "policy_checked": True,
                "upstream_provider": None,
                "upstream_attempted": False,
                "provider_request_id": None,
                "http_status": None,
            },
            "error": {
                "code": "BRANCH_PREFIX_NOT_ALLOWED",
                "message": "Branch must use an allowed prefix",
                "retryable": False,
            },
        }
        jsonschema.validate(payload, self.schema)

    def test_failed_response_requires_error(self):
        payload = {
            "ok": False,
            "trace": {
                "trace_id": "trace-missing-error",
                "operation": "github_create_branch",
                "stage": "unknown",
                "connector_received": True,
                "policy_checked": False,
                "upstream_provider": None,
                "upstream_attempted": False,
                "provider_request_id": None,
                "http_status": None,
            },
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(payload, self.schema)

    def test_contract_requires_non_speculative_attribution(self):
        contract = (ROOT / "core/CONNECTOR_TRACE_CONTRACT_v1.0.md").read_text(encoding="utf-8")
        self.assertIn("must not state that a named safety layer blocked", contract)
        self.assertIn("X-GitHub-Request-Id", contract)
        self.assertIn("Bootstrap gap", contract)


if __name__ == "__main__":
    unittest.main()
