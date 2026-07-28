# Task impact

Direct files are a new validator, its focused test module, and cross-phase JSON
fixtures. Existing runtime and gate validators are read-only dependencies.

Required checks include dependency status/evidence references, per-record
repository and exact SHA bindings, replay convergence and duplicate-effect
prevention, human interrupt/resume/audited bypass, P5 metric derivation from
observed event IDs, fail-closed canary/promotion, and projection authority
boundaries.

No production or provider integration is needed. A fixture PASS is classified
as contract evidence, not live execution evidence.
