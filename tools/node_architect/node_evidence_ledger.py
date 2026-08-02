#!/usr/bin/env python3
"""Canonical replay-safe task/run/node evidence ledger for Node Architect."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

RECORD_SEQUENCE = {
    "node-start": 1,
    "node-decision": 2,
    "node-result": 3,
    "node-readback": 4,
    "checkpoint": 5,
    "next-route-decision": 6,
}


class EvidenceConflict(RuntimeError):
    """Raised when an idempotency identity resolves to different evidence."""


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_segment(value: str, field: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"invalid {field}")
    return value


class NodeEvidenceLedger:
    def __init__(
        self, *, root: Path, task_id: str, run_id: str, node_id: str,
        repository: str, branch: str, base_sha: str, head_sha: str,
        scope_hash: str, idempotency_key: str, occurred_at: str | None = None,
    ) -> None:
        self.root = Path(root)
        self.task_id = _safe_segment(task_id, "task_id")
        self.run_id = _safe_segment(run_id, "run_id")
        self.node_id = _safe_segment(node_id, "node_id")
        self.repository = repository
        self.branch = branch
        self.base_sha = base_sha
        self.head_sha = head_sha
        self.scope_hash = scope_hash
        self.idempotency_key = idempotency_key
        self.occurred_at = occurred_at or utc_now()
        self.run_root = self.root / ".gwc" / "tasks" / self.task_id / "node-runtime" / self.run_id
        self.node_root = self.run_root / self.node_id
        self.events_path = self.run_root / "runtime-events.jsonl"

    def _record(self, artifact_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if artifact_type not in RECORD_SEQUENCE:
            raise ValueError(f"unsupported artifact_type: {artifact_type}")
        record: dict[str, Any] = {
            "schema_version": "1.0",
            "artifact_type": artifact_type,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "repository": self.repository,
            "branch": self.branch,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "scope_hash": self.scope_hash,
            "sequence": RECORD_SEQUENCE[artifact_type],
            "occurred_at": self.occurred_at,
            "idempotency_key": self.idempotency_key,
            "payload": dict(payload),
            "state_digest": digest_payload(payload),
        }
        if artifact_type in {"node-decision", "next-route-decision"}:
            record["decision_digest"] = digest_payload({"artifact_type": artifact_type, "payload": payload})
        record["record_digest"] = digest_payload(record)
        return record

    def _event(self, record: Mapping[str, Any]) -> dict[str, Any]:
        event = {
            "schema_version": "1.0",
            "artifact_type": "runtime-event",
            "event_type": record["artifact_type"],
            "task_id": self.task_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "repository": self.repository,
            "branch": self.branch,
            "head_sha": self.head_sha,
            "scope_hash": self.scope_hash,
            "sequence": record["sequence"],
            "occurred_at": self.occurred_at,
            "idempotency_key": self.idempotency_key,
            "state_digest": record["state_digest"],
            "record_digest": record["record_digest"],
        }
        if "decision_digest" in record:
            event["decision_digest"] = record["decision_digest"]
        event["event_digest"] = digest_payload(event)
        return event

    @staticmethod
    def _write_json_idempotent(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if path.exists():
            current = path.read_text(encoding="utf-8")
            if current == rendered:
                return
            raise EvidenceConflict(f"conflicting evidence at {path}")
        path.write_text(rendered, encoding="utf-8")

    def _append_event_idempotent(self, event: Mapping[str, Any]) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        existing: list[dict[str, Any]] = []
        if self.events_path.exists():
            for line in self.events_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    existing.append(json.loads(line))
        for item in existing:
            if item.get("event_digest") == event.get("event_digest"):
                return
            if (item.get("node_id"), item.get("sequence"), item.get("idempotency_key")) == (
                event.get("node_id"), event.get("sequence"), event.get("idempotency_key")
            ):
                raise EvidenceConflict("conflicting runtime event for idempotency identity")
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(event) + "\n")

    def record(self, artifact_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        record = self._record(artifact_type, payload)
        path = self.node_root / f"{artifact_type}.json"
        self._write_json_idempotent(path, record)
        self._append_event_idempotent(self._event(record))
        return record

    def record_start(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.record("node-start", payload)

    def record_decision(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.record("node-decision", payload)

    def record_result(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.record("node-result", payload)

    def record_readback(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.record("node-readback", payload)

    def record_checkpoint(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.record("checkpoint", payload)

    def record_next_route(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.record("next-route-decision", payload)

    def summary(self) -> dict[str, Any]:
        paths = [str(self.node_root / f"{name}.json") for name in RECORD_SEQUENCE]
        paths.append(str(self.events_path))
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "paths": paths,
            "events_path": str(self.events_path),
        }


def emit_complete_node_evidence(*, ledger: NodeEvidenceLedger, evidence: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    methods = {
        "node-start": ledger.record_start,
        "node-decision": ledger.record_decision,
        "node-result": ledger.record_result,
        "node-readback": ledger.record_readback,
        "checkpoint": ledger.record_checkpoint,
        "next-route-decision": ledger.record_next_route,
    }
    records = {name: methods[name](evidence[name]) for name in RECORD_SEQUENCE}
    return {"records": records, "summary": ledger.summary()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    evidence = payload.pop("evidence")
    ledger = NodeEvidenceLedger(root=args.root, **payload)
    result = emit_complete_node_evidence(ledger=ledger, evidence=evidence)
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
