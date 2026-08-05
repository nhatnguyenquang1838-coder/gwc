# SCRUM-188 implementation design

Implement one pure policy evaluator backed by immutable canonical action metadata. Normalize and validate inputs first, bind every decision to task/repository/scope/base/head identity, apply replay conflict precedence before gate evaluation, then return a schema-valid decision with no executable authority flags.

Test the evaluator by action class and precedence rule: read-only G0/G1, execution G2, Draft PR G3, merge G4, automatic G5 status, manual G5 deployment, G6 applicability, exclusions, drift, invalid input, and replay conflict.
