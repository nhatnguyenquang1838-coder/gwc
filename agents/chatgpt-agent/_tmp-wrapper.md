# ChatGPT Agent Instructions — Composed Entrypoint

This is the mandatory ChatGPT instruction entrypoint for GWC.

## Load order

Always load and follow:

1. parent/root `AGENTS.md` and higher-priority GWC/project instructions;
2. `agents/chatgpt-agent/gwc-governed-base.md` — the complete GWC ChatGPT base instruction set;
3. additional role overlays that apply to the active task.

## Slack Controller mode

When ChatGPT acts as Controller for a Slack-mediated Executor run, it MUST additionally load and follow, in order:

1. `agents/shared/slack-controller-executor-protocol.md`;
2. `agents/chatgpt-agent/slack-controller-mvp.md`.

The Slack Controller overlay is mandatory for that mode, not optional reference material.

It owns Controller decomposition, selected-option Executor Contract compilation, milestone/report timing, RootCard state, `CONTINUE | WAIT_CONTROLLER | TERMINAL` boundaries, in-session 60-second incremental Slack polling, report review, and bounded INTERCEPT decisions.

When GWC is active, do not delegate write-capable execution before valid G2 authority exists. Build the Executor-facing contract from canonical G0 context, the G1 selected option only, exact G2 authority, and exact current repository evidence. Do not forward rejected alternatives or brainstorming noise to the Executor.

For Slack Controller monitoring, the 60-second cadence in `slack-controller-mvp.md` overrides any generic longer ChatGPT thread-sleep cadence only for that monitoring loop. It does not weaken gate or authority rules.

## Conflict rule

If this composition entrypoint or a role overlay conflicts with parent/root governance or higher-priority instructions, follow the higher-priority instruction. Role overlays may specialize behavior and cadence but must not grant authority.