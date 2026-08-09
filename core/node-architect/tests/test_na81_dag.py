import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "na81_dag.py"
SPEC = importlib.util.spec_from_file_location("na81_dag", MODULE_PATH)
assert SPEC and SPEC.loader
na81_dag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(na81_dag)

Edge = na81_dag.Edge
compare_projection = na81_dag.compare_projection
normalize_jira_blocks = na81_dag.normalize_jira_blocks
validate_graph = na81_dag.validate_graph


def _blocks(*, outward=None, inward=None):
    link = {"type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"}}
    if outward:
        link["outwardIssue"] = {"key": outward}
    if inward:
        link["inwardIssue"] = {"key": inward}
    return link


def test_scrum_313_regression_outward_is_predecessor():
    observed = normalize_jira_blocks(
        "SCRUM-313",
        [_blocks(outward="SCRUM-311"), _blocks(outward="SCRUM-312")],
    )
    assert observed == {Edge("SCRUM-311", "SCRUM-313"), Edge("SCRUM-312", "SCRUM-313")}


def test_inward_is_successor():
    assert normalize_jira_blocks("SCRUM-311", [_blocks(inward="SCRUM-313")]) == {Edge("SCRUM-311", "SCRUM-313")}


def test_projection_drift_is_exact_set_difference():
    expected = {Edge("SCRUM-311", "SCRUM-313"), Edge("SCRUM-312", "SCRUM-313")}
    actual = {Edge("SCRUM-311", "SCRUM-313")}
    result = compare_projection(expected, actual)
    assert result["code"] == "DAG_PROJECTION_DRIFT"
    assert result["missing"] == [{"from": "SCRUM-312", "to": "SCRUM-313"}]


def test_81_node_graph_accepts_acyclic_edges():
    nodes = [f"SCRUM-{n}" for n in range(298, 379)]
    result = validate_graph(nodes, [Edge("SCRUM-311", "SCRUM-313"), Edge("SCRUM-312", "SCRUM-313")])
    assert result["node_count"] == 81
    assert result["valid"] is True
