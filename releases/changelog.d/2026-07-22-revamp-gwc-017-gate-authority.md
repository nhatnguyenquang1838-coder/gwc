# REVAMP-GWC-017 — Gate authority node family

## Type

```text
feature
```

## Summary

Adds the second controlled runtime node catalog family:

```text
family: gate_authority
batch: batch-02-gate-authority
planned_nodes: 9
authority_boundary: G1_ALIGNMENT_G2_EXECUTION
```

## Scope

```text
core/node-architect/node-catalog/gate_authority/
tools/node_architect/validate_node_catalog_gate_authority.py
tests/test_node_catalog_gate_authority.py
projects/gwc/package.yaml
```

## Guardrails

```text
No merge authority.
No deploy authority.
No production data authority.
No all-81 catalog implementation.
No runtime engine implementation.
```
