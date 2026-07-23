#!/usr/bin/env python3
"""Project a small canonical runtime catalog knowledge graph.

The tool is deterministic and source-oriented. It does not replace the larger UA
or generated graph artifacts; it emits a focused governance KG projection that
normalizes the catalog taxonomy and G5 CI verification relationships.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

FAMILIES = [
    "intake_context",
    "gate_authority",
    "repo_delivery",
    "runtime_checkpoint",
    "validation_quality",
    "sync_projection",
    "package_export",
    "failure_recovery",
    "scale_control",
]
GATES = ["G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA"]
RELATIONS = {
    "BELONGS_TO_FAMILY",
    "GOVERNED_BY_GATE",
    "IMPLEMENTED_BY",
    "VALIDATED_BY",
    "HANDLES_SCENARIO",
    "DEPENDS_ON_NODE",
    "EXPORTED_BY_PACKAGE",
    "ALIASED_BY",
}


def projection() -> dict[str, object]:
    nodes = []
    edges = []
    for gate in GATES:
        nodes.append({"id": f"gate:{gate}", "type": "gate", "label": gate})
    for family in FAMILIES:
        nodes.append({"id": f"family:{family}", "type": "capability_family", "label": family})

    nodes.extend([
        {"id": "artifact:core/G5_CI_VERIFICATION_CONTRACT_v1.0.md", "type": "artifact", "label": "G5 CI Verification Contract", "source_path": "core/G5_CI_VERIFICATION_CONTRACT_v1.0.md"},
        {"id": "artifact:core/RUNTIME_CATALOG_KNOWLEDGE_GRAPH_CONTRACT_v1.0.md", "type": "artifact", "label": "Runtime Catalog KG Contract", "source_path": "core/RUNTIME_CATALOG_KNOWLEDGE_GRAPH_CONTRACT_v1.0.md"},
        {"id": "artifact:schemas/g5-ci-verification-evidence.schema.json", "type": "artifact", "label": "G5 CI Evidence Schema", "source_path": "schemas/g5-ci-verification-evidence.schema.json"},
        {"id": "scenario:missing_workflow_run", "type": "edge_scenario", "label": "Missing workflow run"},
        {"id": "scenario:sha_mismatch", "type": "edge_scenario", "label": "SHA mismatch"},
        {"id": "scenario:ci_pending", "type": "edge_scenario", "label": "CI pending"},
        {"id": "node:repo-delivery-ci-run-capture", "type": "runtime_node", "label": "CI Run Capture", "aliases": ["workflow_run_capture", "ci.resolve_workflow_run"]},
        {"id": "node:runtime-checkpoint-checkpoint-persist", "type": "runtime_node", "label": "Checkpoint Persist", "aliases": ["ci.persist_pending_checkpoint"]},
        {"id": "node:validation-quality-ci-evidence-capture", "type": "runtime_node", "label": "CI Evidence Capture", "aliases": ["ci.collect_evidence"]},
        {"id": "node:failure-recovery-timeout-recovery", "type": "runtime_node", "label": "Timeout Recovery", "aliases": ["ci.recover_failure"]}
    ])

    edges.extend([
        {"source": "node:repo-delivery-ci-run-capture", "target": "family:repo_delivery", "relationship": "BELONGS_TO_FAMILY"},
        {"source": "node:runtime-checkpoint-checkpoint-persist", "target": "family:runtime_checkpoint", "relationship": "BELONGS_TO_FAMILY"},
        {"source": "node:validation-quality-ci-evidence-capture", "target": "family:validation_quality", "relationship": "BELONGS_TO_FAMILY"},
        {"source": "node:failure-recovery-timeout-recovery", "target": "family:failure_recovery", "relationship": "BELONGS_TO_FAMILY"},
        {"source": "node:repo-delivery-ci-run-capture", "target": "gate:G5_DEPLOY", "relationship": "GOVERNED_BY_GATE"},
        {"source": "node:runtime-checkpoint-checkpoint-persist", "target": "gate:G5_DEPLOY", "relationship": "GOVERNED_BY_GATE"},
        {"source": "node:validation-quality-ci-evidence-capture", "target": "gate:G5_DEPLOY", "relationship": "GOVERNED_BY_GATE"},
        {"source": "node:repo-delivery-ci-run-capture", "target": "artifact:core/G5_CI_VERIFICATION_CONTRACT_v1.0.md", "relationship": "IMPLEMENTED_BY"},
        {"source": "node:validation-quality-ci-evidence-capture", "target": "artifact:schemas/g5-ci-verification-evidence.schema.json", "relationship": "VALIDATED_BY"},
        {"source": "node:repo-delivery-ci-run-capture", "target": "scenario:missing_workflow_run", "relationship": "HANDLES_SCENARIO"},
        {"source": "node:repo-delivery-ci-run-capture", "target": "scenario:sha_mismatch", "relationship": "HANDLES_SCENARIO"},
        {"source": "node:runtime-checkpoint-checkpoint-persist", "target": "scenario:ci_pending", "relationship": "HANDLES_SCENARIO"},
    ])

    return {"schema_version": "1.0", "artifact_type": "runtime-knowledge-graph", "nodes": nodes, "edges": edges}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    graph = projection()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote runtime KG projection to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
