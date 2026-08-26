#!/usr/bin/env python3
"""Trusted validation-command execution boundary for Agent provider results.

The semantic Agent bridge may accept a provider's proposed/result state only
after the configured validation commands are executed by a trusted host-side
runner. Commands are tokenized with ``shlex`` and run with ``shell=False`` so
shell metacharacters cannot create an implicit secondary authority surface.
"""
from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping, Protocol


class TrustedValidationRunner(Protocol):
    name: str

    def run(self, command: str, *, cwd: str | Path | None = None) -> Mapping[str, Any]:
        ...


class SubprocessValidationRunner:
    """Host-side validation runner using argv execution with no shell."""

    name = "subprocess-no-shell-v1"

    def __init__(self, *, timeout_seconds: int = 300) -> None:
        self.timeout_seconds = timeout_seconds

    def run(self, command: str, *, cwd: str | Path | None = None) -> Mapping[str, Any]:
        argv = shlex.split(command)
        if not argv:
            return {
                "exit_code": 2,
                "stdout": "",
                "stderr": "empty validation command",
                "duration_ms": 0,
            }
        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                cwd=None if cwd is None else str(cwd),
                capture_output=True,
                text=True,
                shell=False,
                timeout=self.timeout_seconds,
                check=False,
            )
            return {
                "exit_code": int(completed.returncode),
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "exit_code": 124,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "validation command timed out",
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        except OSError as exc:
            return {
                "exit_code": 127,
                "stdout": "",
                "stderr": f"{type(exc).__name__}: {exc}",
                "duration_ms": int((time.monotonic() - started) * 1000),
            }


__all__ = ["SubprocessValidationRunner", "TrustedValidationRunner"]
