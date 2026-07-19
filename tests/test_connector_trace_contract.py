from pathlib import Path
import json
import unittest

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


class ConnectorTraceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT / "schemas/connector-trace.schema.json").read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(cls.schema)

    def assert_valid(self, payload):
        errors = sorted(self.validator.iter_errors(payload), key=lambda e: list(e.path))
        self.assertEqual([], [e.message for e in errors])

    def base_trace(self):
        return {
            "trace_id": "0123456789abcdef0123456789abcdef",
            "operation": "github_create_branch",
            "failure_stage": None,
            "connector_received": True,
            "policy_checked": True,
            "upstream_attempted": True,
            "upstream_provider": "github",
            "provider_request_id": "provider-123",
            "github_request_id": "ABC1:DEF2:123456:789ABC:00000000",
            "http_status": 201,
            "started_at": "2026-07-19T11:20:00Z",
            "completed_at": "2026-07-19T11:20:01Z",
            "duration_ms": 1000,
        }

    def test_success_envelope_is_valid(self):
        self.assert_valid({"ok": True, "trace": self.base_trace(), "error": None, "data": {"ref": "refs/heads/fix/example"}})

    def test_dw1_policy_rejection_never_claims_github_attempt(self):
        trace = self.base_trace()
        trace.update({"failure_stage": "dw1_policy", "upstream_attempted": False, "upstream_provider": None, "provider_request_id": None, "github_request_id": None, "http_status": None})
        self.assert_valid({"ok": False, "trace": trace, "error": {"code": "BRANCH_PREFIX_NOT_ALLOWED", "message": "Branch must use an allowed prefix", "retryable": False, "details": None}, "data": None})

    def test_github_rejection_requires_upstream_and_status(self):
        trace = self.base_trace()
        trace.update({"failure_stage": "github_api", "http_status": 422})
        self.assert_valid({"ok": False, "trace": trace, "error": {"code": "GITHUB_REF_INVALID", "message": "GitHub rejected the ref", "retryable": False, "details": None}, "data": None})

    def test_policy_rejection_with_upstream_attempt_is_invalid(self):
        trace = self.base_trace()
        trace.update({"failure_stage": "dw1_policy"})
        payload = {"ok": False, "trace": trace, "error": {"code": "POLICY_REJECTED", "message": "Rejected", "retryable": False, "details": None}, "data": None}
        self.assertTrue(list(self.validator.iter_errors(payload)))

    def test_contract_names_all_failure_stages(self):
        text = (ROOT / "core/CONNECTOR_TRACE_CONTRACT_v1.0.md").read_text(encoding="utf-8")
        for stage in ["platform_schema_validation", "platform_runtime", "connector_transport", "dw1_input_validation", "dw1_policy", "github_api", "response_serialization", "unknown"]:
            self.assertIn(stage, text)
        self.assertIn("Contract publication alone is not backend implementation evidence", text)


if __name__ == "__main__":
    unittest.main()
