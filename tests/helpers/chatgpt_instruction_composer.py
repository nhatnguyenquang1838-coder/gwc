#!/usr/bin/env python3
"""Compose the effective ChatGPT agent instructions for tests.

Background
----------
The ChatGPT agent instruction surface was refactored into a *Composed
Entrypoint*: ``agents/chatgpt-agent/agent-instructions.md`` is now a thin
loader that delegates the complete instruction set to
``agents/chatgpt-agent/gwc-governed-base.md`` (the canonical base content).

Tests that assert on the *effective* ChatGPT instructions must validate the
**composed** content, not the bare composer file. Reading only the composer
file is a rot condition introduced by the refactor, not a real instruction
defect (see SCRUM-404 / GitHub issue #441).

This helper is intentionally *loader-invariant*: it resolves the entrypoint,
follows the single documented ``gwc-governed-base.md`` composition edge
declared by the entrypoint, and returns the concatenation. It does not hard
code a fixed list of phrases and does not duplicate instruction content.

It also validates the composition invariant so the helper itself fails closed
if the entrypoint ever stops declaring the base edge (defense-in-depth against
future drift).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

# Repository root containing the agents/ directory.
DEFAULT_ROOT = Path(__file__).resolve().parents[2]

ENTRYPOINT_REL = "agents/chatgpt-agent/agent-instructions.md"
BASE_REL = "agents/chatgpt-agent/gwc-governed-base.md"

# The entrypoint declares the composition edge with a line of the form:
#   `agents/chatgpt-agent/gwc-governed-base.md` — the complete GWC ChatGPT base ...
_BASE_EDGE_RE = re.compile(
    r"`?(agents/chatgpt-agent/gwc-governed-base\.md)`?",
    re.IGNORECASE,
)


class ChatGPTInstructionCompositionError(RuntimeError):
    """Raised when the composed ChatGPT instructions cannot be resolved."""


def _read(path: Path) -> str:
    if not path.is_file():
        raise ChatGPTInstructionCompositionError(
            f"missing ChatGPT instruction file: {path}"
        )
    return path.read_text(encoding="utf-8")


def resolve_base_edge(entrypoint_text: str) -> str:
    """Return the base content path referenced by the entrypoint composer.

    The Composed Entrypoint declares a single composition edge to the
    canonical base content. If that edge is absent, the composition invariant
    is broken and we fail closed.
    """
    match = _BASE_EDGE_RE.search(entrypoint_text)
    if not match:
        raise ChatGPTInstructionCompositionError(
            "entrypoint does not declare the gwc-governed-base.md composition "
            "edge; Composed Entrypoint invariant broken"
        )
    return match.group(1)


def compose_chatgpt_instructions(root: Path | None = None) -> str:
    """Return the composed effective ChatGPT instructions as a single string.

    The composed content is the entrypoint loader followed by the canonical
    base content it references. The normalized (whitespace-collapsed) form is
    useful for phrase assertions that ignore markdown/newline layout.
    """
    root = Path(root) if root is not None else DEFAULT_ROOT
    entrypoint = _read(root / ENTRYPOINT_REL)
    base_rel = resolve_base_edge(entrypoint)
    base = _read(root / base_rel)
    return f"{entrypoint}\n{base}"


def compose_chatgpt_instructions_normalized(root: Path | None = None) -> str:
    """Whitespace-normalized composed ChatGPT instructions for phrase asserts."""
    text = compose_chatgpt_instructions(root)
    return " ".join(text.split())


def chatgpt_instruction_fragments(root: Path | None = None) -> List[str]:
    """Return the individual composition fragments (entrypoint, base)."""
    root = Path(root) if root is not None else DEFAULT_ROOT
    entrypoint = _read(root / ENTRYPOINT_REL)
    base_rel = resolve_base_edge(entrypoint)
    base = _read(root / base_rel)
    return [entrypoint, base]
