"""Deterministic, side-effect-free GWC gate workflow simulator.

The simulator deliberately models external systems as injected stubs. It is
intended for unit tests of gate sequencing, not for real repository actions.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Protocol


class Gate(str, Enum):
    G0_CONTEXT = "G0_CONTEXT"
    G1_ALIGNMENT = "G1_ALIGNMENT"
    G2_EXECUTION = "G2_EXECUTION"
    G3_PR = "G3_PR"
    G4_MERGE = "G4_MERGE"


class GateError(RuntimeError):
    """Raised when the simulated workflow attempts an unauthorized transition."""


class ContextSource(Protocol):
    def read_context(self) -> bool: ...


class G1Validator(Protocol):
    def validate(self) -> bool: ...


class ApprovalSource(Protocol):
    def approved(self, gate: Gate) -> bool: ...


@dataclass
class MockContextSource:
    ready: bool = True

    def read_context(self) -> bool:
        return self.ready


@dataclass
class MockG1Validator:
    passed: bool = True

    def validate(self) -> bool:
        return self.passed


@dataclass
class MockApprovalSource:
    approvals: List[Gate] = field(default_factory=list)

    def approved(self, gate: Gate) -> bool:
        return gate in self.approvals


@dataclass
class WorkflowResult:
    gate: Gate
    events: List[str]


class GwcWorkflowSimulator:
    """Simulate G0 through G4 without touching Git, DS Admin, or the filesystem."""

    def __init__(
        self,
        context: ContextSource,
        validator: G1Validator,
        approvals: ApprovalSource,
    ) -> None:
        self.context = context
        self.validator = validator
        self.approvals = approvals
        self.gate: Optional[Gate] = None
        self.events: List[str] = []

    def run(self) -> WorkflowResult:
        self._enter(Gate.G0_CONTEXT)
        if not self.context.read_context():
            raise GateError("G0_CONTEXT blocked: context is not ready")
        self._enter(Gate.G1_ALIGNMENT)
        if not self.validator.validate():
            raise GateError("G1_ALIGNMENT blocked: validator returned FAIL")
        self._enter(Gate.G2_EXECUTION)
        self._enter(Gate.G3_PR)
        self._enter(Gate.G4_MERGE)
        if not self.approvals.approved(Gate.G4_MERGE):
            self.events.append("G4_MERGE awaiting human approval")
            return WorkflowResult(self.gate, list(self.events))
        self.events.append("G4_MERGE approved")
        return WorkflowResult(self.gate, list(self.events))

    def _enter(self, gate: Gate) -> None:
        self.gate = gate
        self.events.append(f"{gate.value} entered")

