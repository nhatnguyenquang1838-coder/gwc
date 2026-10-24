"""Canonical Python interpreter and PYTHONPATH hygiene for Q0 workflows."""
from __future__ import annotations

import os
from pathlib import Path
import re
import sys

PYTHON_ENV_VAR = 'Q0_PYTHON'
CANONICAL_VENV = Path.home() / '.hermes/cache/scratch/q0-langgraph-venv'
SITE_PACKAGES_RE = re.compile(r'/lib/python(\d+)\.(\d+)/site-packages/?$')


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
    candidate = _canonical_venv() / 'bin/python'
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
    elif python == _canonical_venv() / 'bin/python':
        source = 'CANONICAL_VENV'
    else:
        source = 'sys.executable'
    major, minor = interpreter_version()
    return {'python': str(python), 'version': f'{major}.{minor}',
            'removed_pythonpath': foreign_pythonpath_entries(), 'source': source}
