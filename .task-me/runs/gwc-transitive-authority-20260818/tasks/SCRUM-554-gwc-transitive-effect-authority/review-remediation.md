# G3 independent review remediation

Reviewed head: `4b3d39c8be10b53a502ea3a887fd8dc2ced97540`
Reviewer: Hermes Cloud `U0BNANGC3PB`
Decision: `CHANGES_REQUIRED`

| Finding | Severity | Planned repair in this R2 package |
|---|---|---|
| B-1 | MAJOR | Added historical-success wrong-SHA/event/gate rejection scenario and trace to issue AC7. |
| B-2 | MAJOR | Rewrote GWC test plan around effect-graph/evidence semantics; removed TaskController-only materialization wording. |
| B-3 | MINOR | Added downstream consumer SCRUM-553 and DAG edge. |
| B-4 | MINOR | Added normative true/false/unknown conditional-effect policy and tests. |
| B-5 | MINOR | Retention/delete explicitly maps to destructive capability, with AC and regression. |
| B-6 | MINOR | Defined bounded legacy compatibility: trusted no-transitive-mutation profile only; otherwise effect graph required. |
| B-7 | NIT | Validator bundle is explicitly marked external materialized provenance, not repo-derived authority. |
| B-8 | NIT | DAG now shows downstream SCRUM-553 consumer. |

## Fresh-context GPT R2 review

Reviewed head: `f4fed3ffc16778cf17dd5bc659e2c2ae0a0e5329`
Review mode: `fresh-context` (GPT is implementation/spec author; Hermes verdict is not governance authority)
Decision: `CHANGES_REQUIRED`

| Finding | Severity | Planned repair in R3 |
|---|---|---|
| R2-GWC-1 | MAJOR | Reconcile issue AC8 with fail-closed legacy behavior using a versioned trusted bounded-effect profile. Trigger-capable legacy actions can remain compatible only when the complete profile closure proves all effects are within current/independent authority; otherwise an effect graph is required. |
