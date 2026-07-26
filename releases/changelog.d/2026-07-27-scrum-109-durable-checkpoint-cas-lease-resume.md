# SCRUM-109 durable checkpoint/CAS/lease/resume runtime

- Added provider-neutral in-memory durable checkpoint runtime pilot.
- Enforced expected-revision CAS before checkpoint advancement.
- Enforced active lease owner and current fencing token before mutation.
- Bound resume to task, repository, base SHA, scope hash, graph revision, runtime version, and node version.
- Added safe takeover behavior after lease expiry while rejecting stale-owner writes.
- Added focused unit tests for CAS, stale revision rejection, lease conflict, fencing token mismatch, binding mismatch, safe takeover, and checkpoint-before-wait state.

Explicit exclusions retained: scheduler, database adapter, migration, deployment, production configuration, credentials, production data, merge, auto-merge, force-push, branch deletion, and PR base change.
