#!/usr/bin/env python3
"""Deterministic NA81 DAG normalization and validation.

Canonical direction is blocker/predecessor -> blocked/successor.
This module intentionally contains no LLM/prose interpretation.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable, Mapping, Any


@dataclass(frozen=True, order=True)
class Edge:
    from_key: str
    to_key: str

    def as_dict(self) -> dict[str, str]:
        return {"from": self.from_key, "to": self.to_key}


def normalize_jira_blocks(current_key: str, links: Iterable[Mapping[str, Any]]) -> set[Edge]:
    """Normalize Jira `Blocks` links observed from current_key.

    Jira endpoint semantics for a fetched current issue C:
      outwardIssue=X => X blocks C => X -> C
      inwardIssue=Y  => C blocks Y => C -> Y
    """
    edges: set[Edge] = set()
    for link in links:
        link_type = link.get("type") or {}
        if link_type.get("name") != "Blocks":
            continue
        outward = link.get("outwardIssue")
        inward = link.get("inwardIssue")
        if outward and inward:
            raise ValueError("DAG_LINK_SHAPE_INVALID: both inwardIssue and outwardIssue are present")
        if outward:
            edges.add(Edge(str(outward["key"]), current_key))
        elif inward:
            edges.add(Edge(current_key, str(inward["key"])))
        else:
            raise ValueError("DAG_LINK_SHAPE_INVALID: Blocks link has no endpoint")
    return edges


def validate_graph(nodes: Iterable[str], edges: Iterable[Edge]) -> dict[str, Any]:
    node_set = set(nodes)
    edge_list = list(edges)
    unique = set(edge_list)
    unknown = sorted({k for e in edge_list for k in (e.from_key, e.to_key) if k not in node_set})
    self_edges = sorted(e.as_dict().items() for e in unique if e.from_key == e.to_key)
    duplicates = len(edge_list) - len(unique)
    reverse = sorted(
        (e.from_key, e.to_key)
        for e in unique
        if e.from_key != e.to_key and Edge(e.to_key, e.from_key) in unique and e.from_key < e.to_key
    )

    indegree = {n: 0 for n in node_set}
    outgoing: dict[str, set[str]] = defaultdict(set)
    for e in unique:
        if e.from_key in node_set and e.to_key in node_set and e.from_key != e.to_key:
            if e.to_key not in outgoing[e.from_key]:
                outgoing[e.from_key].add(e.to_key)
                indegree[e.to_key] += 1
    q = deque(sorted(n for n, d in indegree.items() if d == 0))
    visited = 0
    while q:
        n = q.popleft()
        visited += 1
        for nxt in sorted(outgoing[n]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                q.append(nxt)
    cycle_count = 0 if visited == len(node_set) else 1

    return {
        "node_count": len(node_set),
        "edge_count": len(unique),
        "unknown_nodes": unknown,
        "self_edge_count": len(self_edges),
        "duplicate_edge_count": duplicates,
        "reverse_contradiction_count": len(reverse),
        "cycle_count": cycle_count,
        "valid": not unknown and not self_edges and duplicates == 0 and not reverse and cycle_count == 0,
    }


def compare_projection(canonical: Iterable[Edge], observed: Iterable[Edge]) -> dict[str, Any]:
    expected, actual = set(canonical), set(observed)
    missing, extra = expected - actual, actual - expected
    return {
        "code": "PASS" if not missing and not extra else "DAG_PROJECTION_DRIFT",
        "missing": [e.as_dict() for e in sorted(missing)],
        "extra": [e.as_dict() for e in sorted(extra)],
        "equal": not missing and not extra,
    }
