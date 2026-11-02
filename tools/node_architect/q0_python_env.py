"""Canonical Python interpreter and PYTHONPATH hygiene for Q0 workflows."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping


def _source_sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture_native_load_proof(*, source_root: str | Path, candidate_sha: str,
                              qualification_profile_digest: str, load_proof_ref: str,
                              activation_id: str, runtime_session_id: str,
                              module_names: list[str]) -> dict[str, Any]:
    """Capture identities of modules actually loaded by this runtime process."""
    import hashlib
    import time

    root = Path(source_root).resolve(strict=True)
    if not re.fullmatch(r"[0-9a-f]{40}", candidate_sha):
        raise ValueError("LOAD_PROOF_CANDIDATE_SHA_INVALID")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", qualification_profile_digest):
        raise ValueError("LOAD_PROOF_PROFILE_DIGEST_INVALID")
    if not all(isinstance(value, str) and value.strip() for value in
               (load_proof_ref, activation_id, runtime_session_id)):
        raise ValueError("LOAD_PROOF_BINDING_REQUIRED")
    if not isinstance(module_names, list) or not module_names:
        raise ValueError("LOAD_PROOF_MODULES_REQUIRED")
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()
    if head != candidate_sha:
        raise ValueError("LOAD_PROOF_CANDIDATE_HEAD_MISMATCH")
    files, identities = [], {}
    for name in module_names:
        module = sys.modules.get(name)
        filename = getattr(module, "__file__", None) if module is not None else None
        if not isinstance(filename, str) or not filename.endswith(".py"):
            raise ValueError("LOAD_PROOF_MODULE_NOT_LOADED")
        path = Path(filename).resolve(strict=True)
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError("LOAD_PROOF_MODULE_OUTSIDE_SOURCE_ROOT") from exc
        disk = _source_sha256(path)
        blob = subprocess.run(["git", "-C", str(root), "show", f"{candidate_sha}:{relative}"],
                              check=True, capture_output=True).stdout
        committed = hashlib.sha256(blob).hexdigest()
        if disk != committed:
            raise ValueError("LOAD_PROOF_SOURCE_DRIFT")
        identities[relative] = "sha256:" + disk
        files.append({"path": relative, "disk_sha256": disk, "head_sha256": committed,
                      "committed_module_sha256": committed, "match": True})
    return {"proof_type": "NATIVE_LOAD_PROOF", "load_proof_ref": load_proof_ref,
            "activation_id": activation_id, "source_root": str(root),
            "runtime_session_id": runtime_session_id, "runtime_process_id": str(os.getpid()),
            "loaded_at_ns": time.time_ns(), "head_sha": head,
            "candidate_sha": candidate_sha, "loaded_source_sha": head,
            "loaded_profile_digest": qualification_profile_digest,
            "committed_module_sha256": files[0]["committed_module_sha256"],
            "files": files, "loaded_module_identities": identities}


def verify_native_load_proof(evidence: Mapping[str, Any], *, candidate_sha: str,
                             qualification_profile_digest: str, load_proof_ref: str) -> bool:
    """Verify live-process, worktree, Git-blob, profile and reference bindings."""
    if not isinstance(evidence, Mapping) or evidence.get("proof_type") != "NATIVE_LOAD_PROOF":
        return False
    if (evidence.get("load_proof_ref") != load_proof_ref
            or evidence.get("runtime_process_id") != str(os.getpid())
            or evidence.get("candidate_sha") != candidate_sha
            or evidence.get("loaded_source_sha") != candidate_sha
            or evidence.get("head_sha") != candidate_sha
            or evidence.get("loaded_profile_digest") != qualification_profile_digest):
        return False
    root_value, files = evidence.get("source_root"), evidence.get("files")
    identities = evidence.get("loaded_module_identities")
    if not isinstance(root_value, str) or not isinstance(files, list) or not files or not isinstance(identities, Mapping):
        return False
    try:
        root = Path(root_value).resolve(strict=True)
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()
        if head != candidate_sha:
            return False
        seen = set()
        for item in files:
            if not isinstance(item, Mapping):
                return False
            relative = item.get("path")
            if not isinstance(relative, str) or relative in seen or Path(relative).is_absolute() or ".." in Path(relative).parts:
                return False
            seen.add(relative)
            path = (root / relative).resolve(strict=True)
            path.relative_to(root)
            loaded = False
            for module in tuple(sys.modules.values()):
                filename = getattr(module, "__file__", None) if module is not None else None
                if isinstance(filename, str) and Path(filename).resolve() == path:
                    loaded = True
                    break
            disk = _source_sha256(path)
            blob = subprocess.run(["git", "-C", str(root), "show", f"{candidate_sha}:{relative}"],
                                  check=True, capture_output=True).stdout
            committed = __import__("hashlib").sha256(blob).hexdigest()
            if (not loaded or disk != committed or item.get("disk_sha256") != disk
                    or item.get("head_sha256") != committed
                    or item.get("committed_module_sha256") != committed
                    or item.get("match") is not True
                    or identities.get(relative) != "sha256:" + disk):
                return False
        return (evidence.get("committed_module_sha256") == files[0].get("committed_module_sha256")
                and bool(evidence.get("activation_id")) and bool(evidence.get("runtime_session_id")))
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


PYTHON_ENV_VAR = 'Q0_PYTHON'
CANONICAL_VENV = Path.home() / '.hermes/cache/scratch/q0-langgraph-venv'
SITE_PACKAGES_RE = re.compile(r'[/\\]lib[/\\]python(\d+)\.(\d+)[/\\]site-packages[/\\]?$')


def _canonical_venv() -> Path:
    return Path.home() / '.hermes/cache/scratch/q0-langgraph-venv'


def interpreter_version() -> tuple[int, int]:
    return sys.version_info.major, sys.version_info.minor


def _foreign_site_packages(entry: str) -> bool:
    match = SITE_PACKAGES_RE.search(entry)
    return bool(match and (int(match.group(1)), int(match.group(2))) != interpreter_version())


def foreign_pythonpath_entries(env=None) -> list[str]:
    source = os.environ if env is None else env
    return [entry for entry in source.get('PYTHONPATH', '').split(os.pathsep)
            if entry and _foreign_site_packages(entry)]


def sanitize_python_path(env=None) -> list[str]:
    source = os.environ if env is None else env
    foreign = foreign_pythonpath_entries(source)
    sys.path[:] = [entry for entry in sys.path if not _foreign_site_packages(entry)]
    kept = [entry for entry in source.get('PYTHONPATH', '').split(os.pathsep)
            if entry and not _foreign_site_packages(entry)]
    if kept:
        source['PYTHONPATH'] = os.pathsep.join(kept)
    else:
        source.pop('PYTHONPATH', None)
    return foreign


def canonical_python() -> Path:
    override = os.environ.get(PYTHON_ENV_VAR)
    if override:
        path = Path(override).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path
    venv = _canonical_venv()
    # CPython venv layout is platform-specific: Scripts/python.exe on Windows,
    # bin/python on POSIX. Check both in deterministic host-native-first order.
    candidates = ((venv / 'Scripts/python.exe', venv / 'bin/python')
                  if os.name == 'nt' else (venv / 'bin/python', venv / 'Scripts/python.exe'))
    for candidate in candidates:
        if candidate.exists() and candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return Path(sys.executable)


def clean_env(base=None) -> dict:
    result = dict(os.environ if base is None else base)
    kept = [entry for entry in result.get('PYTHONPATH', '').split(os.pathsep)
            if entry and not _foreign_site_packages(entry)]
    if kept:
        result['PYTHONPATH'] = os.pathsep.join(kept)
    else:
        result.pop('PYTHONPATH', None)
    prefix = str(canonical_python().parent)
    existing = [part for part in result.get('PATH', '').split(os.pathsep)
                if part and part != prefix]
    result['PATH'] = os.pathsep.join([prefix, *existing])
    return result


def describe() -> dict:
    python = canonical_python()
    if os.environ.get(PYTHON_ENV_VAR) and python == Path(os.environ[PYTHON_ENV_VAR]).expanduser():
        source = 'Q0_PYTHON'
    elif python in {_canonical_venv() / 'bin/python', _canonical_venv() / 'Scripts/python.exe'}:
        source = 'CANONICAL_VENV'
    else:
        source = 'sys.executable'
    major, minor = interpreter_version()
    return {'python': str(python), 'version': f'{major}.{minor}',
            'removed_pythonpath': foreign_pythonpath_entries(), 'source': source}
