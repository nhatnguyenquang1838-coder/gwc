# Notification Capability Usage Guide

## Purpose

Define how agents should use notification capabilities during GWC execution without coupling governance to a specific provider.

## Agent Behavior

After important execution events, the agent should:

1. Confirm current gate/task state.
2. Record evidence and audit information.
3. Check available notification capabilities.
4. Publish a notification when an appropriate capability exists.
5. Continue execution if notification delivery is unavailable.

## Supported Capability Examples

Agents may use any approved available capability:

- Slack connector
- Slack MCP
- Other messaging connectors
- Console or execution logs

The agent must not assume Slack is always available.

## Gate Events

Notify on:

- Task started
- Gate started
- Gate completed
- Gate blocked
- PR created
- CI validation completed
- Approval requested
- Human override
- Task completed

## Message Content

Notifications should include:

- Project
- Task ID
- Gate
- Status
- Evidence
- Actor
- UTC timestamp
- Next action

## Authority Boundary

Notification channels provide visibility only.

Authority remains:

- GWC state engine: governance truth
- GitHub: code and CI truth
- Jira: tracking projection

A notification failure must never block gate execution.
