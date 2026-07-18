---
id: requesting-code-review
version: 0.1.0
role: primary
compatible_gate: G3_PR
source_type: gwc-normalized-offline-adaptation
upstream_reference: /obra/superpowers
---
# Requesting Code Review — GWC Offline Adaptation

Build a read-only review request for the exact current PR head SHA. Include task id, base SHA, head SHA, scope hash, changed paths, requirements, validation evidence, CI evidence, acceptance criteria, and GWC review lanes: requirement, design, code, test, governance, delivery, CI.

The reviewer must inspect the actual diff and return a verdict with findings by severity: BLOCKER, MAJOR, MINOR, or NIT. Reviewer output is evidence only and never grants merge authority.
