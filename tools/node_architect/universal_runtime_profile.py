"""Load and validate the machine-readable Universal Runtime v2 default profile."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class UniversalRuntimeProfileError(ValueError):
    """A missing or invalid canonical runtime profile is a runtime defect."""

    code = "GWC_RUNTIME_DEFECT"


def _canonical_digest(value: Mapping[str, Any]) -> str:
    subject = {key: item for key, item in value.items() if key != "profile_digest"}
    encoded = json.dumps(
        subject,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def load_universal_v2_default_profile(root: Path | str | None = None) -> dict[str, Any]:
    """Load the one canonical V2 profile; never fall back to a GWC v1 profile."""
    repository_root = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[2]
    profile_path = repository_root / "core/node-architect/universal-runtime-default-profile.json"
    schema_path = repository_root / "schemas/node-architect/universal-runtime-default-profile.schema.json"
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        import jsonschema

        jsonschema.validate(profile, schema)
    except Exception as exc:  # noqa: BLE001 - any missing/broken V2 component fails closed
        raise UniversalRuntimeProfileError(
            f"GWC_RUNTIME_DEFECT: Universal V2 default profile/schema unavailable or invalid: {type(exc).__name__}"
        ) from exc

    if not isinstance(profile, Mapping) or profile.get("runtime_family") != "UNIVERSAL_V2":
        raise UniversalRuntimeProfileError("GWC_RUNTIME_DEFECT: default runtime family is not UNIVERSAL_V2")
    if profile.get("legacy_gwc_v1", {}).get("load_by_default") is not False:
        raise UniversalRuntimeProfileError("GWC_RUNTIME_DEFECT: GWC v1 must not load by default")
    if profile.get("profile_digest") != _canonical_digest(profile):
        raise UniversalRuntimeProfileError("GWC_RUNTIME_DEFECT: default runtime profile digest mismatch")
    return dict(profile)


__all__ = ["UniversalRuntimeProfileError", "load_universal_v2_default_profile"]
