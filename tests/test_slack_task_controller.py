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


class SlackTaskControllerTests(unittest.TestCase):
    def subtasks(self):
        return [
            {"id": "S1", "objective": "inspect", "allowed_work": ["read"], "expected_output": "evidence", "report_requirement": "report evidence", "after_report": "CONTINUE"},
            {"id": "S2", "objective": "implement", "allowed_work": ["write scoped files"], "expected_output": "patch", "report_requirement": "report diff/tests", "after_report": "WAIT_CONTROLLER"},
            {"id": "S3", "objective": "validate", "allowed_work": ["test"], "expected_output": "terminal evidence", "report_requirement": "report exact evidence", "after_report": "TERMINAL"},
        ]

    def kwargs(self, **overrides):
        values = dict(
            task_id="SCRUM-300", repository="owner/gwc", base_sha="a" * 40, branch="auto/run/SCRUM-300",
            selected_option={"id": "OPTION-A"}, g2_authority_ref="G2-REF", subtasks=self.subtasks(),
            controller_id="controller-1", executor_id="executor-1", slack_thread_ref="C1:123.456",
        )
        values.update(overrides)
        return values

    def test_contract_is_bounded_and_slack_is_not_authority(self):
        contract = mod.compile_executor_contract(**self.kwargs())
        self.assertFalse(contract["slack_is_authority"])
        self.assertEqual(len(contract["subtasks"]), 3)
        self.assertNotIn("rejected_options", contract)

    def test_subtask_count_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "SUBTASK_COUNT"):
            mod.compile_executor_contract(**self.kwargs(subtasks=self.subtasks()[:2]))

    def test_non_hex_base_sha_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "BINDING_INVALID"):
            mod.compile_executor_contract(**self.kwargs(base_sha="z" * 40))

    def test_controller_cannot_be_executor(self):
        with self.assertRaisesRegex(ValueError, "ROLE_IDENTITY_INVALID"):
            mod.compile_executor_contract(**self.kwargs(executor_id="controller-1"))

    def test_rejected_option_noise_is_not_forwarded(self):
        with self.assertRaisesRegex(ValueError, "CONTAINS_NOISE"):
            mod.compile_executor_contract(**self.kwargs(selected_option={"id": "A", "rejected_options": ["B"]}))

    def test_duplicate_subtask_id_is_blocked(self):
        subtasks = self.subtasks()
        subtasks[1]["id"] = "S1"
        with self.assertRaisesRegex(ValueError, "ID_DUPLICATE"):
            mod.compile_executor_contract(**self.kwargs(subtasks=subtasks))

    def test_wait_controller_is_respected(self):
        result = mod.controller_next_action(
            {"subtask_id": "S2", "status": "DONE", "after_report": "WAIT_CONTROLLER"},
            expected_subtask_id="S2",
        )
        self.assertEqual(result["outcome"], "WAIT_CONTROLLER")

    def test_material_drift_intercepts(self):
        result = mod.controller_next_action(
            {"subtask_id": "S1", "status": "RUNNING", "after_report": "CONTINUE", "scope_drift": True},
            expected_subtask_id="S1",
        )
        self.assertEqual(result["outcome"], "INTERCEPT")


class ChatGPTConversationDeeplinkTests(unittest.TestCase):
    def test_direct_chat_url_is_preserved(self):
        url = "https://chatgpt.com/c/abc-123?foo=bar#message"
        self.assertEqual(mod.validate_chatgpt_conversation_deeplink(deeplink=url), url)

    def test_custom_gpt_chat_url_is_preserved(self):
        url = "https://chatgpt.com/g/g-xyz-dw-super/c/abc-123"
        self.assertEqual(mod.validate_chatgpt_conversation_deeplink(deeplink=url), url)

    def test_future_opaque_chat_route_is_preserved(self):
        url = "https://chatgpt.com/workspaces/team/chats/thread-42?foo=bar#latest"
        self.assertEqual(mod.validate_chatgpt_conversation_deeplink(deeplink=url), url)

    def test_home_fallback_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HOME_FORBIDDEN"):
            mod.validate_chatgpt_conversation_deeplink(deeplink="https://chatgpt.com/")

    def test_share_link_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHARE_FORBIDDEN"):
            mod.validate_chatgpt_conversation_deeplink(
                deeplink="https://chatgpt.com/share/abc-123"
            )

    def test_wrong_host_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "DEEPLINK_INVALID"):
            mod.validate_chatgpt_conversation_deeplink(
                deeplink="https://example.com/c/abc-123"
            )

    def test_missing_chat_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "CONVERSATION_REQUIRED"):
            mod.validate_chatgpt_conversation_deeplink(deeplink="")


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
            "last_material_update": "2026-08-13T21:32:00+07:00",
            "conversation": {
                "platform": "chatgpt",
                "source": "gpt_runtime_current_chat",
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
        self.assertEqual(card["schema_version"], "1.1")
        self.assertTrue(card["card_digest"].startswith("sha256:"))

    def test_conversation_id_is_not_required_or_emitted(self):
        card = mod.compile_root_card(**self.kwargs())
        self.assertNotIn("conversation_id", card["conversation"])

    def test_runtime_source_is_required(self):
        kwargs = self.kwargs()
        kwargs["conversation"]["source"] = "caller_supplied"
        with self.assertRaisesRegex(ValueError, "SOURCE_INVALID"):
            mod.compile_root_card(**kwargs)

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

    def test_schema_declares_current_chat_source_and_derived_action(self):
        schema = json.loads(
            (ROOT / "schemas/task-controller-root-card.schema.json").read_text(
                encoding="utf-8"
            )
        )
        conversation = schema["properties"]["conversation"]
        self.assertIn("conversation", schema["required"])
        self.assertIn("actions", schema["required"])
        self.assertNotIn("conversation_id", conversation["required"])
        self.assertEqual(
            conversation["properties"]["source"]["const"],
            "gpt_runtime_current_chat",
        )
        self.assertEqual(
            schema["properties"]["actions"]["properties"]["open_in_gpt"]
            ["properties"]["label"]["const"],
            "Open in GPT",
        )


if __name__ == "__main__":
    unittest.main()
