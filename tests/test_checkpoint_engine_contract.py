from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.node_architect.validate_checkpoint_engine_contract import main


DOC_TEXT = """# Checkpoint Runtime Engine Contract v0.1

## Invariants

1. CAS required.
2. Lease required.
3. Reconcile before retry.
4. Checkpoint before suspend.
5. No false pass.

## Engine state fields

run_id
checkpoint_id
checkpoint_revision
lease_owner
lease_expires_at_utc
current_node_id
current_node_version
pending_action
last_reconciled_at_utc
next_node_id
status

## Failure routing

CAS mismatch
expired lease
unknown write result
node version drift
stale approval
live state mismatch
"""


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://gwc.local/schemas/node-architect/checkpoint-engine.schema.json",
    "title": "Checkpoint Runtime Engine Contract",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "engine_id",
        "required_phases",
        "invariants",
        "state_fields",
        "failure_routes",
        "authority_boundaries",
    ],
    "properties": {
        "invariants": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "cas_required",
                "lease_required",
                "reconcile_before_retry",
                "checkpoint_before_suspend",
                "no_false_pass",
            ],
            "properties": {
                "cas_required": {"const": True},
                "lease_required": {"const": True},
                "reconcile_before_retry": {"const": True},
                "checkpoint_before_suspend": {"const": True},
                "no_false_pass": {"const": True},
            },
        }
    },
}


class CheckpointEngineContractTests(unittest.TestCase):
    def _write_contract(self, root: Path, schema: dict | None = None, doc_text: str = DOC_TEXT) -> None:
        doc = root / "core" / "node-architect" / "CHECKPOINT_RUNTIME_ENGINE_CONTRACT_v0.1.md"
        schema_path = root / "schemas" / "node-architect" / "checkpoint-engine.schema.json"
        doc.parent.mkdir(parents=True, exist_ok=True)
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text(doc_text, encoding="utf-8")
        schema_path.write_text(json.dumps(SCHEMA if schema is None else schema, indent=2) + "\n", encoding="utf-8")

    def test_valid_contract_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_contract(root)
            self.assertEqual(main(["--root", str(root)]), 0)

    def test_schema_missing_lease_invariant_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            schema = json.loads(json.dumps(SCHEMA))
            schema["properties"]["invariants"]["required"].remove("lease_required")
            self._write_contract(root, schema=schema)
            self.assertEqual(main(["--root", str(root)]), 1)

    def test_doc_missing_reconcile_phrase_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_contract(root, doc_text=DOC_TEXT.replace("Reconcile before retry.", ""))
            self.assertEqual(main(["--root", str(root)]), 1)


if __name__ == "__main__":
    unittest.main()
