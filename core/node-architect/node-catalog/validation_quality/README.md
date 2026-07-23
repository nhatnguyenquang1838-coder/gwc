# validation_quality node family

Task: `REVAMP-GWC-020`  
Batch: `batch-05-validation-quality`  
Family: `validation_quality`  
Planned nodes: 9  
Authority boundary: `g3_required` / `G3_PR`

This family defines the controlled runtime node catalog entries for validation quality work: schema validation, validator execution, unit-test mapping, exact-head CI evidence, reproducibility, side-effect checks, blocker classification, and G3 pass decisions.

`g3_required` is the explicit authority label for nodes whose applicability and decision boundary are exactly `G3_PR`. It does not grant G2 execution, G4 merge, G5 deploy, or G6 production authority.

## Scope

Allowed:

- add exactly 9 `validation_quality` node descriptors
- add one family README
- add a stdlib validator and focused unit tests
- add package export entries
- add a changelog fragment

Forbidden:

- implementing the full 81-node catalog in one PR
- runtime engine implementation
- scheduler or worker implementation
- deploy or release changes
- production configuration or production data access
- merge or auto-merge authority
- package version change

## Nodes

| Node | Type | Gate |
|---|---|---|
| `validation-quality-schema-validation` | tool | G3_PR |
| `validation-quality-validator-execution` | tool | G3_PR |
| `validation-quality-unit-test-mapping` | workflow | G3_PR |
| `validation-quality-ci-evidence-capture` | workflow | G3_PR |
| `validation-quality-evidence-quality-check` | gate | G3_PR |
| `validation-quality-reproducibility-check` | tool | G3_PR |
| `validation-quality-blocker-severity-classification` | gate | G3_PR |
| `validation-quality-side-effect-check` | workflow | G3_PR |
| `validation-quality-g3-pass-decision` | gate | G3_PR |
