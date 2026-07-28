# Implementation plan

1. Inventory the declared 116-scenario space and current materialized records.
2. Identify covered/equivalent/deferred/missing combinations without changing
   the canonical router authority.
3. Add adversarial cycles, dense branches, tied routes and typed-guard failures
   to the existing bounded evaluator.
4. Define and enforce graph-size, route-count, timeout and memory budgets with
   typed fail-closed evidence.
5. Extend focused registry/router tests and run the existing P3/regression
   validators.
