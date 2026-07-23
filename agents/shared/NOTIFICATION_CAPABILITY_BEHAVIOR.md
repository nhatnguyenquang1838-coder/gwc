# Notification Capability Behavior

## Purpose

Define how agents consume GWC notification capability guidance without coupling execution to a specific notification provider.

## Agent Behavior

For important execution events:

1. Confirm current gate state.
2. Record evidence and audit information.
3. Check available notification capabilities.
4. Use an available notification channel when appropriate.
5. Continue execution when notification capability is unavailable.

## Supported Capability Examples

Agents may use:

- Slack connector
- Slack MCP
- Other approved notification integrations
- Audit-only reporting when no notification channel exists

## Authority Boundary

Notification is visibility only.

Source of truth remains:

- GWC governance state
- GitHub repository and CI truth
- Approved project tracking projections

Notification failure must never block:

- gate progression
- evidence recording
- valid execution outcomes

## Event Coverage

Notify for:

- Task started
- Gate started
- Gate completed
- Gate blocked
- PR created
- CI validation completed
- Approval requested
- Human override
- Task completed
