# REVAMP-GWC-020 — validation_quality node family

Date: 2026-07-22  
Status: Draft PR scope

## Summary

Adds the fifth controlled node catalog family:

- family: `validation_quality`
- batch: `batch-05-validation-quality`
- planned nodes: 9
- authority boundary: `G3_PR`

## Added

- `core/node-architect/node-catalog/validation_quality/README.md`
- 9 `validation_quality` runtime node descriptors
- `tools/node_architect/validate_node_catalog_validation_quality.py`
- `tests/test_node_catalog_validation_quality.py`

## Guardrails

This change is catalog-only.

It does not add:

- all 81 node implementations in one PR
- runtime engine
- scheduler or worker
- merge or auto-merge authority
- deploy or release authority
- production configuration
- credentials or secrets
- migrations
- production data access

`package_version` remains unchanged.
