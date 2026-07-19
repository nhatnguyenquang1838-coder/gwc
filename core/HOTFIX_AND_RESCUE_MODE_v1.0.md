# Hotfix and Rescue Mode v1.0

## Status

- Document ID: `hotfix-and-rescue-mode`
- Version: `1.0`
- Lifecycle: `active`
- Priority: 25 (between runtime contract and registry)
- SHA-256: `pending` (verify after write)

## Purpose

The GWC policy is intentionally strict to prevent uncontrolled changes, but real-world software development sometimes requires rapid action when systems are broken. This document defines **HOTFIX** and **RESCUE** modes that allow bounded bypasses while maintaining core safety guarantees.

These modes do NOT replace the standard G0→G6 gate sequence—they provide a parallel path for time-critical work with documented, explicit human authority and full audit trails.

## Activation Conditions

A HOTFIX or RESCUE mode can ONLY be activated when ALL of the following are true:

1. **User explicitly states** one of the activation phrases:
   - `HOTFIX`
   - `RESCUE MODE`
   - `EMERGENCY FIX`
   - `BYPASS STANDARD GATES`
   - `APPLY HOTFIX PROTOCOL`

2. **The user identifies exactly what needs to be fixed** (scope, files, behavior)

3. **No existing DS Admin task claim or approval envelope exists** for this work item (if one does exist, the standard G0-G6 process applies instead)

4. **The change does NOT involve:**
   - Production data reads/writes (G6 remains forbidden)
   - Credential/secret rotation (security boundary maintained)
   - Production configuration changes (except in explicit emergency scenarios where user confirms)
   - Financial transactions or irreversible destructive operations
   - Architecture changes that affect other project systems

5. **The user accepts the consequences** including: "I understand this bypasses standard gates and requires post-facto audit"

## Activation Command Format

When a user activates this mode, they must provide the following in a standalone fenced block:

```text
ACTIVATE HOTFIX <scope-hash-prefix> [DESCRIPTION]
OR
ACTIVATE RESCUE <scope-hash-prefix> [DESCRIPTION]
```

Example valid activations:
```text
ACTIVATE HOTFIX abc1234567890def "Fix login 500 error on /api/auth endpoint"
```

The `<scope-hash-prefix>` should be the first 16 characters of a hash derived from the task description. The user can generate this by:
- Asking the agent to compute it, OR
- Providing any unique identifier they choose (the agent records and validates consistency)

## Execution Mode Selection

### HOTFIX MODE

**Use when:**
- A system is broken but there's time for minimal due process
- The fix is small and localized (1-3 files, <50 lines of code change)
- No production data access or deployment is needed

**Gate Sequence for HOTFIX:**
```text
G0_INTAKE → G1_MINIMAL → H2_EXECUTION → G3_DRAFT_PR → STOP
```

### RESCUE MODE

**Use when:**
- An emergency requires immediate action with minimal validation
- The system is actively breaking customers/users
- Standard gates would cause unacceptable delay

**Gate Sequence for RESCUE:**
```text
G0_INTAKE → H2_EXECUTION → G3_DRAFT_PR → STOP
```

## Detailed Gate Definitions

### G0_INTAKE (Both Modes)

For chat-only brainstorming before an explicit G2 transition request, use the
conversation-local `CHAT_ONLY_PREPARATION` state. Do not create a physical
intake artifact, task, or approval token in that state. Once the user requests
G2, the formal rescue intake below becomes mandatory before execution.

The agent MUST create a minimal context snapshot:

```yaml
schema_version: '1.0'
artifact_type: g0-hotfix-intake
generated_at: <ISO-8601>
mode: hotfix|rescue
task_description: <user-provided text>
activation_phrase: <exact user command>
risk_assessment: low|medium|high
affected_files: [<list of files>]
scope_hash_prefix: <16-char prefix from activation>
approval_recorded: true
human_author: <user identifier>
```

**Output:** Report the intake to the user and confirm no prohibited actions are included.

### G1_MINIMAL (HOTFIX Only)

For HOTFIX mode, run a lightweight preflight:

1. Verify the affected files exist and are readable
2. Confirm changes don't touch prohibited areas (production data, credentials)
3. Generate minimal option analysis (at least one alternative considered)
4. Record decision with rationale

**Validator:** If `tools/validate_g01.py` is available, run it against a simplified g0/g1 workspace. If not, record that validation was skipped due to mode constraints.

### H2_EXECUTION (Both Modes)

**This is the bypass gate.** Standard G2 rules are relaxed but NOT eliminated:

#### Common Rules (Apply to Both Modes):
- Use ONE dedicated branch per task (never push to main directly)
- Keep changes bounded to explicitly stated scope
- No force-push, no rewrite shared history
- No unrelated cleanup or formatting sweeps
- Commit messages must reference the activation phrase and scope hash

#### Additional HOTFIX Rules:
- Run local validation if available and quick (<30 seconds)
- Record what validation was skipped and why
- All file modifications must be in the approved scope list
- Generate a minimal diff review before push

#### Additional RESCUE Rules:
- SKIP optional validations, but document exactly what was skipped
- Focus on correctness of the fix itself
- If the fix is trivial (typo, missing config), minimal testing suffices
- If the fix involves multiple components, still maintain basic structure
- **Critical:** Document every assumption made and every shortcut taken

### H2_EXECUTION: Execution Constraints

Regardless of mode, the agent MUST:

1. Create a dedicated branch with clear naming:
   ```
   hotfix/<hash-prefix>/fix-description
   rescue/<hash-prefix>/fix-description
   ```

2. Make changes ONLY to explicitly authorized files

3. Run validation commands that are clearly available and non-destructive

4. Review the complete diff against base SHA before pushing

5. Report ALL skipped validations with reasons

6. Never touch: production data, credentials, secrets, protected-branch main

### G3_DRAFT_PR (Both Modes)

After H2_EXECUTION:
1. Push the branch to origin
2. Create a Draft PR with clear labels: `hotfix` or `rescue`
3. Include in PR description:
   - Activation phrase and scope hash
   - Problem statement
   - What was changed and why
   - List of skipped validations
   - Risk assessment
   - Explicit note: "This was a bypass of standard gates due to user request"

### STOP CONDITION

After delivering the Draft PR, the agent MUST stop. No merge, deploy, or production operations are authorized. The PR enters standard G4_MERGE review via normal channels.

## Post-Activity Requirements (User Obligation)

When HOTFIX or RESCUE mode is used, the user should:

1. **Review the Draft PR** through normal processes
2. **Create a retroactive DS Admin task claim** if applicable for their workflow
3. **Document what happened** for audit purposes
4. **Consider whether standard gates need adjustment** for future similar situations

## Failure Modes and Safety Nets

### Automatic Failures (Always Block):
- Attempting to read/write production data
- Credential/secret rotation without separate G6 approval
- Architecture changes affecting other systems
- Destructive irreversible operations
- Merging or deploying without explicit G4/G5 authority

### Soft Failures (Block Until Resolved):
- Cannot verify target files exist
- Validation script fails with errors
- Diff includes unexpected file changes
- Base SHA mismatch detected

### Recovery Path:
If the hotfix/rescue process itself fails mid-execution, the agent must:
1. Stop all writes immediately
2. Report the failure state clearly
3. Suggest next steps (standard G0-G6 path is always available)
4. Not attempt to "fix" the hotfix within the same bypass session

## Verification and Audit

Every HOTFIX or RESCUE execution produces:
1. The activation phrase in conversation history
2. A context intake file (G0_INTAKE)
3. Branch with changes and commits on origin
4. Draft PR with evidence of bypass rationale
5. Record of all skipped validations

These provide an audit trail for post-facto review.

## Emergency Override Clause

In truly critical situations (system down, data corruption risk, active security breach):
- The user may state: `TRULY EMERGENCY OVERRIDE`
- The agent proceeds with H2_EXECUTION using minimum viable checks
- All other protections remain in place (no production data access, no main branch writes)
- Full post-mortem required after the fact

This clause is intentionally high-threshold to prevent casual bypass.

## Example Workflows

### Example 1: Minor Bug Fix (HOTFIX)

User: `ACTIVATE HOTFIX a1b2c3d4e5f6g7h8 "Fix null pointer in login validation"`

Agent:
- Creates G0_INTAKE with scope and risk assessment
- Runs G1_MINIMAL verification
- Creates branch `hotfix/a1b2/fix-login-null`
- Makes change to auth validation file
- Runs lint/typecheck (quick)
- Pushes branch, creates Draft PR with hotfix label
- Reports: "Hotfix delivered as Draft PR. Not merged."

### Example 2: Critical Hotfix (RESCUE)

User: `ACTIVATE RESCUE i9j8k7l6m5n4o3p2 "Fix payment processing failure affecting all users"`

Agent:
- Creates G0_INTAKE with high risk flag
- Skips G1_MINIMAL due to rescue mode
- Creates branch `rescue/i9j8/fix-payment-processing`
- Makes targeted fix to payment service
- Runs only smoke tests (no time for full suite)
- Pushes and creates Draft PR labeled `rescue emergency`
- Reports: "Rescue-mode hotfix delivered. Not merged."

## Prohibited Statements

The agent must NEVER claim during HOTFIX/RESCUE mode:
- "This is safe" (without evidence)
- "All tests pass" (when they didn't actually run)
- "No risks identified" (always document potential issues)
- Ready for production without G5 approval
- Merged or deployed without explicit separate authority

## Summary Table

| Aspect | Standard | HOTFIX | RESCUE |
|--------|----------|--------|--------|
| Gate Sequence | G0→G1→G2→G3→G4→G5→G6 | G0→G1_MINIMAL→H2→G3 | G0_INTAKE→H2→G3 |
| Validation | Full suite | Minimal, quick | Best-effort |
| Documentation | Complete | Summary | Post-mortem required |
| Branch Safety | Yes | Yes | Yes |
| Production Data | Forbidden | Forbidden | Forbidden |
| Merge Authority | G4 Human | G4 Human | G4 Human |
| Audit Trail | Full | Partial | Retrospective |

## Activation Command Examples

```text
ACTIVATE HOTFIX a1b2c3d4e5f6g7h8 "Fix null pointer in login validation"
```

```text
ACTIVATE RESCUE i9j8k7l6m5n4o3p2 "Payment processing failure affecting all users"
```

```text
TRULY EMERGENCY OVERRIDE - Fix data corruption risk in user records
```

**Note:** Each activation must be in a standalone fenced text block. The agent will provide the exact hash prefix for future reference.

## Implementation Note

This document establishes the policy framework. Actual implementation requires:
1. Creating intake card templates if they don't exist
2. Defining branch naming conventions
3. Establishing post-facto review procedures
4. Updating project profiles to acknowledge these modes exist

---

**NOTICE:** This is a governance document addition, not execution authorization. No repository changes are performed until a user explicitly activates the mode with proper activation phrases and accepts the consequences.
