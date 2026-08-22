import unittest
from tools.node_architect.validator_execution import (
    BLOCKED,
    NODE_ID,
    PASS,
    RC_MALFORMED,
    RC_MISSING,
    RC_OK,
    run_validator_execution,
)

HEAD = "a" * 40
SCOPE = "sha256:" + "c" * 64


def base(**overrides):
    p = {
        "task_id": "SCRUM-335",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "auto/SCRUM-335-na81-recert-20260814-r10",
        "base_sha": HEAD,
        "head_sha": HEAD,
        "scope_hash": SCOPE,
    }
    p.update(overrides)
    return p


class ValidatorExecutionM5Tests(unittest.TestCase):
    def test_all_builtins_pass(self):
        r = run_validator_execution(base())
        self.assertEqual(r["status"], PASS)
        self.assertEqual(r["overall_return_code"], RC_OK)
        self.assertEqual(r["node_id"], NODE_ID)
        self.assertEqual(
            r["return_codes"],
            {
                "head_sha_format": RC_OK,
                "base_sha_format": RC_OK,
                "scope_hash_format": RC_OK,
                "identity_complete": RC_OK,
            },
        )

    def test_missing_head_sha_blocks(self):
        r = run_validator_execution(base(head_sha=""))
        self.assertEqual(r["status"], BLOCKED)
        self.assertEqual(r["return_codes"]["head_sha_format"], RC_MISSING)
        self.assertEqual(r["overall_return_code"], RC_MISSING)

    def test_malformed_head_sha_blocks(self):
        r = run_validator_execution(base(head_sha="zzz"))
        self.assertEqual(r["status"], BLOCKED)
        self.assertEqual(r["return_codes"]["head_sha_format"], RC_MALFORMED)

    def test_selective_validators(self):
        r = run_validator_execution(base(), validators=["head_sha_format"])
        self.assertEqual(set(r["return_codes"]), {"head_sha_format"})
        self.assertEqual(r["return_codes"]["head_sha_format"], RC_OK)

    def test_unknown_validator_is_malformed(self):
        r = run_validator_execution(base(), validators=["does_not_exist"])
        self.assertEqual(r["return_codes"]["does_not_exist"], RC_MALFORMED)

    def test_non_mapping_payload_raises(self):
        with self.assertRaises(TypeError):
            run_validator_execution("not-a-mapping")


if __name__ == "__main__":
    unittest.main()
