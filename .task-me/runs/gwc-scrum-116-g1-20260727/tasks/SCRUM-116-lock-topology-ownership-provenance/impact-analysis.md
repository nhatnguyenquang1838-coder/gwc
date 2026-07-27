# Task-specific impact

Direct owners: GWC owns gate artifacts and governance contracts; DW-SuperApps owns the package store and host adapters; each registered target owns its `.gwc`, `.ua`, `.task-me`, and `.bmad` runtime outputs. UA, Task-Me and BMAD provide read/analysis/planning inputs but cannot mutate canonical GWC state. GitHub/CI proves code and exact-head checks; Jira tracks roadmap/status; Notion and Slack are human projections.

Downstream consumers are SCRUM-117, SCRUM-118 and SCRUM-119 in parallel, then SCRUM-120 after the topology is locked. The principal failure mode is two agents writing the same root or artifact with incompatible provenance; CAS, lease/fencing, idempotency and scope-hash checks must fail closed.
