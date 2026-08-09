from core.node_architect.tools.na81_dag import Edge, compare_projection, normalize_jira_blocks, validate_graph


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
    assert normalize_jira_blocks("SCRUM-311", [_blocks(inward="SCRUM-313")]) == {
        Edge("SCRUM-311", "SCRUM-313")
    }


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
