import re
import unittest


APPROVAL_RE = re.compile(
    r"^APPROVE G[2-6] [a-z0-9][a-z0-9._-]{2,120} [0-9a-f]{16} .+Z$"
)


class ApprovalRequestTests(unittest.TestCase):
    def test_plain_acknowledgements_are_not_authority(self):
        for text in [
            "ok",
            "okay",
            "yes",
            "approve",
            "approved",
            "continue",
            "go",
            "làm đi",
            "fix ngay",
            "Approve, fix ngay",
        ]:
            with self.subTest(text=text):
                self.assertIsNone(APPROVAL_RE.match(text))

    def test_agent_generated_approval_command_matches(self):
        command = "APPROVE G2 gwc-op-runtime-20260715-001 c11617b17c357dd3 2026-07-16T17:00:00Z"
        self.assertIsNotNone(APPROVAL_RE.match(command))

    def test_human_does_not_construct_partial_token(self):
        partial = "APPROVE G2 gwc-op-runtime-20260715-001"
        self.assertIsNone(APPROVAL_RE.match(partial))


if __name__ == "__main__":
    unittest.main()
