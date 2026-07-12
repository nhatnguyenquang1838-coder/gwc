
# User Command Format Rule

## Purpose

Make every exact command requested from the user directly copyable and prevent
ambiguous approvals.

## Required presentation

Whenever the agent asks the user to perform an approval, activation, retry, or
other exact command, place the exact command in a standalone fenced text block.

Example:

```text
APPROVE CP-20260712-001 0123456789abcdef
```

## Formatting rules

- Put exactly one executable user command in each block.
- Put explanations before the block.
- Do not put explanations, comments, bullets, or alternatives inside the block.
- Preserve exact capitalization, spacing, approval ID, and hash prefix.
- Do not present an executable command containing unresolved placeholders.
- Do not provide approval only as inline code.
- Do not shorten or invent approval tokens.

## Invalid execution approval

The following is never a valid G2 execution approval:

```text
APPROVE G2_EXECUTION
```

These responses are also invalid for G2:

```text
OK
Approved
Proceed
Do it
```

## G1 convenience command

A read-only inspection request may be presented as:

```text
APPROVE G1_INSPECT
```

Project policy determines whether ordinary language may also grant G1.

## Failure behavior

If the exact token cannot be derived from a complete validated envelope, stop
with:

```text
APPROVAL_TOKEN_UNAVAILABLE
```

Do not ask the user to approve a placeholder.
