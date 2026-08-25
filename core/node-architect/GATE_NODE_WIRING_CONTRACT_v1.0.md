# Gate / Node Wiring Contract v1.0

Node Architect shadow routing is scenario-specific and never a fixed 81-node sequence.

## Gate/family applicability

- G0_CONTEXT: `intake_context`
- G1_ALIGNMENT / G2_EXECUTION: `gate_authority`
- G2_EXECUTION / G3_PR: `repo_delivery`
- G2_EXECUTION: `runtime_checkpoint`
- G3_PR: `validation_quality`
- read-only projection: `sync_projection`
- G2/G3 package scenarios: `package_export`
- G2 and selected G5 recovery: `failure_recovery`
- G3/G5/read-only scale checks: `scale_control`

## Route packs

`RP-01` standard PR delivery; `RP-02` approval wait/resume; `RP-03` CI failure/recovery; `RP-04` projection; `RP-05` package export; `RP-06` scale control.

Every runtime route pack is source-backed and typed. Visualization/catalogue-order edges are never runtime evidence. Router output carries no authority and cannot grant or advance G2-G6.
