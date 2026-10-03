"""GWC v1 runtime quarantine sentinel.

The original implementation is preserved as evidence under
``legacy/gwc-v1/sources`` and is not executable on the Universal v2 lane.
"""
from __future__ import annotations


class LegacyRuntimeQuarantined(RuntimeError):
    """Raised whenever an implicit GWC v1 runtime load is attempted."""

    code = "GWC_RUNTIME_DEFECT"


def load_legacy_runtime(*_args, **_kwargs):
    raise LegacyRuntimeQuarantined(
        "GWC_RUNTIME_DEFECT: GWC v1 is quarantined; select an explicit historical profile or use Universal V2."
    )


__all__ = ["LegacyRuntimeQuarantined", "load_legacy_runtime"]
