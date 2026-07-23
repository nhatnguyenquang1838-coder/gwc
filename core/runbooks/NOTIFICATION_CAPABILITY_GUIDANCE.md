# Gate Notification Capability Guidance

## Purpose

Define how agents provide execution visibility after governance events without coupling GWC to a specific communication provider.

## Design Principle

GWC defines the required behavior. Agents decide which available capability to use.

GWC MUST NOT depend on a specific notification implementation.

Supported delivery mechanisms may include:

- Slack connector
- Slack MCP
- Microsoft Teams connector
- Email integration
- Console/log output
- Other approved notification capabilities

## Gate Event Rule

After important execution events, the agent should:

1. Confirm or update the current task and gate state.
2. Record evidence and audit information.
3. Publish execution visibility through an available notification capability.
4. Continue execution if no notification capability is available.

## Important Events

Notifications should be considered for:

- Task started
- Gate started
- Gate completed
- Gate blocked
- PR created
- CI validation completed
- Approval requested
- Human override
- Task completed

## Authority Boundary

Notification channels are projections only.

Authority remains:

- GWC state engine: governance state
- GitHub: code and CI truth
- Jira: tracking projection

A notification message MUST NOT be treated as approval authority or governance state.

## Failure Handling

Notification failure MUST NOT block execution.

The agent should:

- continue the workflow;
- record or mention that notification was unavailable;
- preserve the original execution result.

## Agent Decision Rule

Before notifying, the agent should inspect available capabilities and select the appropriate route.

Example:

```
ChatGPT runtime  -> Slack connector
Local agent      -> Slack MCP
CI runner        -> build log / artifact
No capability   -> audit only
```
