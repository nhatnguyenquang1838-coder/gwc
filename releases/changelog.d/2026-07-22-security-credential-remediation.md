# Security remediation — plaintext provider credential

Date: 2026-07-22  
Status: Draft PR scope

## Summary

Removes a plaintext Alibaba provider credential from the Continue example configuration and replaces it with a Continue secret reference.

## Changed

- `.continue/agents/new-config.yaml`
  - uses `${{ secrets.ALIBABA_API_KEY }}` for both model entries
  - consolidates duplicate top-level `models` mappings into one array
- `tests/test_no_plaintext_provider_credentials.py`
  - rejects plaintext credential fields in Continue YAML configurations
  - verifies the example has one top-level `models` mapping

## Required operator action

The exposed credential must be revoked or rotated in Alibaba Cloud. Removing it from the current tree does not invalidate copies retained in Git history or external logs.

## Guardrails

This change does not perform credential rotation, history rewrite, force-push, direct main push, merge, deployment, production configuration changes, or production data access.
