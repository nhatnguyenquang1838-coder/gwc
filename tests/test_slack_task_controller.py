from pathlib import Path
import importlib.util
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "slack_task_controller", ROOT / "tools/node_architect/slack_task_controller.py"
)
mod = importlib.util.module_from_spec(SPEC)
sys.modules["slack_task_controller"] = mod
SPEC.loader.exec_module(mod)


class ChatGPTConversationDeeplinkTests(unittest.TestCase):
    def test_direct_conversation_url_is_preserved(self):
        url = "https://chatgpt.com/c/abc-123?foo=bar#message"
        self.assertEqual(
            mod.validate_chatgpt_conversation_deeplink(
                conversation_id="abc-123", deeplink=url
            ),
            url,
        )

    def test_custom_gpt_conversation_url_is_preserved(self):
        url = "https://chatgpt.com/g/g-xyz-dw-super/c/abc-123"
        self.assertEqual(
            mod.validate_chatgpt_conversation_deeplink(
                conversation_id="abc-123", deeplink=url
            ),
            url,
        )

    def test_home_fallback_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HOME_FORBIDDEN"):
            mod.validate_chatgpt_conversation_deeplink(
                conversation_id="abc-123", deeplink="https://chatgpt.com/"
            )

    def test_share_link_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHARE_FORBIDDEN"):
            mod.validate_chatgpt_conversation_deeplink(
                conversation_id="abc-123",
                deeplink="https://chatgpt.com/share/abc-123",
            )

    def test_wrong_host_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "DEEPLINK_INVALID"):
            mod.validate_chatgpt_conversation_deeplink(
                conversation_id="abc-123",
                deeplink="https://example.com/c/abc-123",
            )

    def test_conversation_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "CONVERSATION_MISMATCH"):
            mod.validate_chatgpt_conversation_deeplink(
                conversation_id="abc-123",
                deeplink="https://chatgpt.com/c/other-conversation",
            )

    def test_missing_conversation_reference_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "CONVERSATION_REQUIRED"):
            mod.validate_chatgpt_conversation_deeplink(
                conversation_id="", deeplink="https://chatgpt.com/c/abc-123"
            )


class RootCardCompilerTests(unittest.TestCase):
    def kwargs(self):
        return {
            "run_id": "RUN-1",
            "task_id": "SCRUM-402",
            "human_owner": "nhat",
            "gate": "G2",
            "controller_id": "chatgpt",
            "executor_id": "hermes-cloud",
            "active_subtask": "S1",
            "progress": "1/4",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "branch": "pre-prod",
            "head_sha": "a" * 40,
            "ci": "pending",
            "risk": "none",
            "now": "patch RootCard contract",
            "next_action": "run tests",
            "last_material_update": "2026-08-13T19:14:00+07:00",
            "conversation": {
                "platform": "chatgpt",
                "conversation_id": "abc-123",
                "deeplink": "https://chatgpt.com/g/g-xyz/c/abc-123?view=1#latest",
                "context_key": "SCRUM-402/RUN-1",
            },
            "actions": {"pause": True, "stop": True},
        }

    def test_open_in_gpt_is_derived_and_exact(self):
        card = mod.compile_root_card(**self.kwargs())
        self.assertEqual(
            card["actions"]["open_in_gpt"]["url"],
            self.kwargs()["conversation"]["deeplink"],
        )
        self.assertEqual(card["schema_ref"], "schemas/task-controller-root-card.schema.json")
        self.assertEqual(card["schema_version"], "1.0")
        self.assertTrue(card["card_digest"].startswith("sha256:"))

    def test_caller_cannot_override_open_in_gpt(self):
        kwargs = self.kwargs()
        kwargs["actions"]["open_in_gpt"] = {
            "label": "Open in GPT",
            "url": "https://chatgpt.com/",
        }
        with self.assertRaisesRegex(ValueError, "OPEN_IN_GPT_DERIVED"):
            mod.compile_root_card(**kwargs)

    def test_invalid_deeplink_fails_root_card_compilation(self):
        kwargs = self.kwargs()
        kwargs["conversation"]["deeplink"] = "https://chatgpt.com/"
        with self.assertRaisesRegex(ValueError, "HOME_FORBIDDEN"):
            mod.compile_root_card(**kwargs)

    def test_schema_declares_conversation_and_derived_action(self):
        schema = json.loads(
            (ROOT / "schemas/task-controller-root-card.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("conversation", schema["required"])
        self.assertIn("actions", schema["required"])
        self.assertEqual(
            schema["properties"]["actions"]["properties"]["open_in_gpt"]
            ["properties"]["label"]["const"],
            "Open in GPT",
        )


if __name__ == "__main__":
    unittest.main()
