"""Active regression: the historical GWC v1 runtime is quarantined."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tools.node_architect.universal_run_legacy import LegacyRuntimeQuarantined, load_legacy_runtime


def test_implicit_legacy_runtime_load_fails_closed():
    with pytest.raises(LegacyRuntimeQuarantined) as caught:
        load_legacy_runtime()

    assert caught.value.code == "GWC_RUNTIME_DEFECT"
    assert "quarantined" in str(caught.value).lower()


def test_active_quarantine_sentinel_has_no_legacy_runtime_imports():
    module_path = Path(__file__).resolve().parents[1] / "tools/node_architect/universal_run_legacy.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    assert not any(name.endswith(("universal_run_kernel", "semantic_agent_runtime", "live_runtime_bridge")) for name in imported)
