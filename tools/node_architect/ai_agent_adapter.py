#!/usr/bin/env python3
"""Provider-neutral AI implementation-agent adapter (Node Architect node).

This node lets the autonomous pre-prod runtime invoke an AI implementation agent
for ONE Jira task, inside the exact G2 permission envelope derived from the
SCRUM-272 standing policy / run-manifest.

Design invariants (fail closed):
  * No G3/G4/G5 authority is ever granted (no merge/deploy/release/prod/credential).
  * Out-of-scope path/action, malformed provider output, provider timeout, duplicate
    request (replay conflict) and unknown write all terminate in a typed FAIL_CLOSED
    (or RECONCILED/REPLAY_CONFLICT) result; the node never silently proceeds.
  * Bounded repair rounds only; every repair changes the head SHA and invalidates
    prior CI/review/G4-readiness evidence (re-derived, never reused).
  * No hidden manual fallback: if no provider is available the node returns FAIL_CLOSED.

Providers are pluggable via the Provider protocol. `CustomRunnerProvider` is the
default (custom/self-hosted runner); `DeterministicFakeProvider` is used by the
tests to reproduce the contract in CI. Hermes, Codex or another agent implement
the same protocol without any change to the graph.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, MutableMapping, Protocol, Sequence

from .build_node_instruction_pack import InstructionPack, build_node_instruction_pack
from .validate_ai_agent_result import validate_ai_agent_result

DEFAULT_MAX_REPAIR_ROUNDS = 2

SUCCESS = "SUCCESS"
FAIL_CLOSED = "FAIL_CLOSED"
REPLAY_CONFLICT = "REPLAY_CONFLICT"
TIMEOUT = "TIMEOUT"
MALFORMED_OUTPUT = "MALFORMED_OUTPUT"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
RECONCILED = "RECONCILED"


class Provider(Protocol):
    """Pluggable AI implementation-agent backend."""

    name: str

    def run(self, pack: InstructionPack) -> Mapping[str, Any]:
        """Execute the pack and return the raw agent output (a mapping).

        May raise ProviderUnavailable / ProviderTimeout, or return malformed data.
        """
        ...


class ProviderUnavailable(RuntimeError):
    pass


class ProviderTimeout(RuntimeError):
    pass


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest_paths(paths: Sequence[str]) -> str:
    joined = "\n".join(sorted(paths))
    return _sha256(joined)


def _digest_validation(outputs: Sequence[str]) -> str:
    joined = "\n".join(outputs)
    return _sha256(joined)


@dataclass
class _ResultBuilder:
    run_id: str
    task_id: str
    repository: str
    scope_hash: str
    idempotency_key: str
    provider: str
    final_head_sha: str = "0" * 40
    changed_paths: list[str] = field(default_factory=list)
    recorded_actions: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    next_action: str = ""
    terminal_outcome: str = FAIL_CLOSED
    g3_g4_g5_authority_granted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "task_id": self.task_id,
            "repository": self.repository,
            "scope_hash": self.scope_hash,
            "idempotency_key": self.idempotency_key,
            "final_head_sha": self.final_head_sha,
            "changed_paths": list(self.changed_paths),
            "changed_path_digest": _digest_paths(self.changed_paths),
            "validation_digest": _digest_validation(self.findings),
            "terminal_outcome": self.terminal_outcome,
            "provider": self.provider,
            "findings": list(self.findings),
            "checkpoints": list(self.checkpoints),
            "next_action": self.next_action,
            "recorded_actions": list(self.recorded_actions),
            "g3_g4_g5_authority_granted": self.g3_g4_g5_authority_granted,
        }


def execute(
    request: Mapping[str, Any],
    *,
    provider: Provider,
    root: Any = None,
    idempotency_store: MutableMapping[str, Mapping[str, Any]] | None = None,
    max_repair_rounds: int = DEFAULT_MAX_REPAIR_ROUNDS,
    request_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one AI-agent task inside the G2 envelope.

    `root` is accepted for interface symmetry (an isolated workspace root); the
    deterministic contract does not require real filesystem mutation. `idempotency_store`
    is an injectable mapping so tests and the runtime share the same replay semantics.
    """
    store: MutableMapping[str, Mapping[str, Any]] = idempotency_store if idempotency_store is not None else {}

    # 1. Validate request structurally via the pack builder (raises on missing fields).
    try:
        pack = build_node_instruction_pack(request)
    except (KeyError, TypeError) as exc:
        return _fail_closed_dict(request, provider_name="none", findings=[f"malformed_request: {exc}"])

    content_digest = pack.content_digest
    key = pack.idempotency_key

    # 2. Idempotency / replay: same key + same digest => prior result; diff digest => conflict.
    prior = store.get(key)
    if prior is not None:
        if prior.get("_content_digest") == content_digest:
            prior_result = dict(prior)
            prior_result.pop("_content_digest", None)
            return prior_result
        return _fail_closed_dict(
            request,
            provider_name=provider.name,
            outcome=REPLAY_CONFLICT,
            findings=["replay_conflict: same idempotency_key with different content digest"],
        )

    builder = _ResultBuilder(
        run_id=pack.run_id,
        task_id=pack.task_id,
        repository=pack.repository,
        scope_hash=pack.scope_hash,
        idempotency_key=pack.idempotency_key,
        provider=provider.name,
    )

    # 3. Dispatch to provider (fail closed on unavailable / timeout).
    try:
        raw = provider.run(pack)
    except ProviderUnavailable as exc:
        builder.findings.append(f"provider_unavailable: {exc}")
        builder.terminal_outcome = FAIL_CLOSED
        builder.next_action = "escalate: provider unavailable"
        return _persist(store, key, content_digest, builder)
    except ProviderTimeout as exc:
        builder.findings.append(f"provider_timeout: {exc}")
        builder.terminal_outcome = TIMEOUT
        builder.next_action = "retry with longer budget or escalate"
        return _persist(store, key, content_digest, builder)

    # 4. Validate raw output structure.
    if not isinstance(raw, Mapping):
        builder.findings.append("malformed_output: provider output is not a mapping")
        builder.terminal_outcome = MALFORMED_OUTPUT
        builder.next_action = "escalate: malformed provider output"
        return _persist(store, key, content_digest, builder)

    changed = list(raw.get("changed_paths", []) or [])
    recorded = list(raw.get("recorded_actions", []) or [])

    # 5. Scope envelope enforcement (fail closed on violation).
    scope_errors = _enforce_scope(changed, recorded, pack)
    if scope_errors:
        builder.findings.extend(scope_errors)
        builder.terminal_outcome = OUT_OF_SCOPE
        builder.next_action = "escalate: out-of-scope change detected"
        return _persist(store, key, content_digest, builder)

    # 6. Run validation commands (sandboxed, simulated here). Bounded repair rounds.
    round_idx = 0
    valid = False
    validation_outputs: list[str] = []
    head_sha = pack.preprod_base_sha
    while round_idx <= max_repair_rounds:
        builder.checkpoints.append({
            "id": f"repair-round-{round_idx}",
            "status": "executed",
            "detail": f"validation pass {round_idx}",
        })
        # Simulated validation: the provider's validation_commands are recorded as
        # evidence; a deterministic provider returns a pass marker in `validation`.
        validation_outputs = [f"round={round_idx} head={head_sha}"]
        valid = bool(raw.get("validation_passed", True))
        if valid:
            # A repair changes the head SHA and invalidates prior evidence.
            head_sha = _derive_head(head_sha, round_idx, changed)
            break
        round_idx += 1
        if round_idx > max_repair_rounds:
            break

    builder.final_head_sha = head_sha
    builder.changed_paths = changed
    builder.recorded_actions = recorded

    if not valid:
        builder.findings.append("validation_failed: exceeded max repair rounds")
        builder.terminal_outcome = FAIL_CLOSED
        builder.next_action = "escalate: validation failed after bounded repairs"
        return _persist(store, key, content_digest, builder)

    # 7. Final schema + scope validation of the produced result (defence in depth).
    builder.terminal_outcome = SUCCESS
    builder.next_action = "proceed_to_g3: result schema-valid and scope-clean"
    candidate = builder.to_dict()
    final_errors = validate_ai_agent_result(
        candidate,
        request_identity=pack,
        authorized_actions=pack.authorized_actions,
        allowed_paths=pack.allowed_paths,
        prohibited_paths=pack.prohibited_paths,
    )
    if final_errors:
        builder.findings.extend(final_errors)
        builder.terminal_outcome = FAIL_CLOSED
        builder.next_action = "escalate: result failed final validation"
        return _persist(store, key, content_digest, builder)

    builder.findings.append("execution_complete: schema-valid, scope-clean, g3_g4_g5 authority not granted")
    return _persist(store, key, content_digest, builder)


def _derive_head(base_sha: str, round_idx: int, changed: Sequence[str]) -> str:
    """Deterministic, non-base head SHA reflecting a (repair) commit.

    Every repair yields a NEW head SHA, so prior CI/review/G4-readiness evidence
    (which is keyed on the head) is invalidated and must be re-derived.
    """
    seed = f"{base_sha}:{round_idx}:{','.join(sorted(changed))}:{time.time_ns()}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest().ljust(40, "0")[:40]


def _enforce_scope(changed: Sequence[str], recorded: Sequence[str], pack: InstructionPack) -> list[str]:
    from .validate_ai_agent_result import _is_protected

    errors: list[str] = []
    allowed = set(pack.allowed_paths)
    prohibited = set(pack.prohibited_paths)
    authorized = set(pack.authorized_actions)
    for path in changed:
        if path not in allowed:
            errors.append(f"out_of_scope_path: {path!r} not in allowed_paths")
        if path in prohibited:
            errors.append(f"prohibited_path: {path!r} in prohibited_paths")
        if _is_protected(path):
            errors.append(f"control_plane_protected_path: {path!r} is control-plane protected")
    for action in recorded:
        if action not in authorized:
            errors.append(f"unauthorized_action: {action!r} not in authorized_actions")
    return errors


def _fail_closed_dict(
    request: Mapping[str, Any],
    *,
    provider_name: str,
    outcome: str = FAIL_CLOSED,
    findings: Sequence[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": str(request.get("run_id", "")),
        "task_id": str(request.get("task_id", "")),
        "repository": str(request.get("repository", "")),
        "scope_hash": str(request.get("scope_hash", "")),
        "idempotency_key": str(request.get("idempotency_key", "")),
        "final_head_sha": "0" * 40,
        "changed_paths": [],
        "changed_path_digest": _digest_paths([]),
        "validation_digest": _digest_validation(list(findings or [])),
        "terminal_outcome": outcome,
        "provider": provider_name,
        "findings": list(findings or []),
        "checkpoints": [],
        "next_action": "escalate: fail closed",
        "recorded_actions": [],
        "g3_g4_g5_authority_granted": False,
    }


def _persist(
    store: MutableMapping[str, Mapping[str, Any]],
    key: str,
    content_digest: str,
    builder: _ResultBuilder,
) -> dict[str, Any]:
    result = builder.to_dict()
    # Cache keyed by idempotency_key; store the content digest for replay detection.
    store[key] = {**result, "_content_digest": content_digest}
    return result


class CustomRunnerProvider:
    """Default provider: a custom/self-hosted runner that executes the pack.

    In this MVP the runner is simulated (it raises if no runner is wired in), so the
    node stays fail-closed unless a concrete runner is supplied via `run_fn`.
    """

    name = "custom-runner"

    def __init__(self, run_fn: Callable[[InstructionPack], Mapping[str, Any]] | None = None) -> None:
        self._run_fn = run_fn

    def run(self, pack: InstructionPack) -> Mapping[str, Any]:
        if self._run_fn is None:
            raise ProviderUnavailable("custom-runner: no runner wired in (fail closed)")
        return self._run_fn(pack)


class DeterministicFakeProvider:
    """Test provider: replays a bounded fixture deterministically (AC-1..AC-5)."""

    name = "deterministic-fake"

    def __init__(
        self,
        *,
        changed_paths: Sequence[str] | None = None,
        recorded_actions: Sequence[str] | None = None,
        validation_passed: bool = True,
        raise_unavailable: bool = False,
        raise_timeout: bool = False,
        malformed: bool = False,
    ) -> None:
        self.changed_paths = list(changed_paths or [])
        self.recorded_actions = list(recorded_actions or [])
        self.validation_passed = validation_passed
        self.raise_unavailable = raise_unavailable
        self.raise_timeout = raise_timeout
        self.malformed = malformed

    def run(self, pack: InstructionPack) -> Mapping[str, Any]:
        if self.raise_unavailable:
            raise ProviderUnavailable("fake: unavailable")
        if self.raise_timeout:
            raise ProviderTimeout("fake: timeout")
        if self.malformed:
            return ["not", "a", "mapping"]
        return {
            "changed_paths": self.changed_paths,
            "recorded_actions": self.recorded_actions,
            "validation_passed": self.validation_passed,
        }
