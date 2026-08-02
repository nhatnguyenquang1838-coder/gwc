# GWC governance hotfix — agent claim intake and default boot

Date: 2026-08-02
Task: SCRUM-262

## Summary

- Adds default-on GWC boot semantics for GWC-governed requests.
- Defines explicit opt-out phrases: `NO GWC`, `Không GWC`, `loại bỏ GWC`, and `ignored GWC`.
- Makes Jira `AI Agent` and `Claimed At` mandatory intake evidence only when the executor is an AI or automated agent.
- Preserves human workflow flexibility: empty agent claim fields do not invalidate human-executed work.
- Clarifies that hotfix/rescue modes do not bypass agent claim intake, G4, G5, G6, or production-data/secret safeguards.

## Guardrails

This change is documentation/governance only. It does not authorize merge, deploy, release, production configuration, production data, migration, credential/secret operation, package/export, branch deletion, force-push, manual G5, or G6 action.
