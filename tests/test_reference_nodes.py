from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.node_architect.validate_reference_nodes import main


READ_NODE = {
    "schema_version": "0.1",
    "node_id": "reference.read_context",
    "node_version": "0.1.0",
    "node_class": "read_only",
    "entry": {"requires": ["repository_identity_verified"]},
    "do": {"actions": ["fetch_required_sources"], "side_effect": False},
    "branches": [{"when": "context_ready", "route": "reference.scoped_write"}],
    "exit": {"evidence": ["context_summary"]},
    "next": ["reference.scoped_write"],
}

WRITE_NODE = {
    "schema_version": "0.1",
    "node_id": "reference.scoped_write",
    "node_version": "0.1.0",
    "node_class": "side_effect_write",
    "entry": {"requires": ["valid_g2_approval"]},
    "do": {
        "actions": ["execute_bounded_write"],
        "side_effect": True,
        "idempotency_key_required": True,
        "readback_node": "reference.read_context",
    },
    "branches": [{"when": "write_succeeded_and_readback_matches", "route": "reference.await_approval"}],
    "exit": {"evidence": ["readback_evidence"]},
    "next": ["reference.await_approval"],
}

SUSPEND_NODE = {
    "schema_version": "0.1",
    "node_id": "reference.await_approval",
    "node_version": "0.1.0",
    "node_class": "suspend_resume",
    "entry": {"requires": ["readback_evidence_current"]},
    "do": {
        "actions": ["persist_checkpoint_before_suspend"],
        "side_effect": False,
        "checkpoint_before_suspend": True,
        "resume_signal": "exact_approval_command_or_rejection",
    },
    "branches": [{"when": "exact_approval_received_and_current", "route": "next_authorized_node"}],
    "exit": {"evidence": ["approval_request_id"]},
    "next": ["next_authorized_node"],
}


class ReferenceNodeTests(unittest.TestCase):
    def _write_nodes(self, root: Path, write_node: dict | None = None) -> None:
        directory = root / "core" / "node-architect" / "reference-nodes"
        directory.mkdir(parents=True, exist_ok=True)
        nodes = {
            "read-only-context.node.json": READ_NODE,
            "scoped-write.node.json": WRITE_NODE if write_node is None else write_node,
            "suspend-resume.node.json": SUSPEND_NODE,
        }
        for name, node in nodes.items():
            (directory / name).write_text(json.dumps(node, indent=2) + "\n", encoding="utf-8")

    def test_valid_reference_nodes_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_nodes(root)
            self.assertEqual(main(["--root", str(root)]), 0)

    def test_write_node_requires_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bad_write = dict(WRITE_NODE)
            bad_do = dict(bad_write["do"])
            bad_do.pop("idempotency_key_required")
            bad_write["do"] = bad_do
            self._write_nodes(root, bad_write)
            self.assertEqual(main(["--root", str(root)]), 1)

    def test_missing_reference_directory_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(main(["--root", temp_dir]), 1)


if __name__ == "__main__":
    unittest.main()
