#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def safe_rel(value: str) -> bool:
    p = Path(value)
    return not p.is_absolute() and ".." not in p.parts and "\\" not in value

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None)
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    errors = []
    registry_path = root / "skills" / "registry.yaml"
    schema_path = root / "schemas" / "skill-registry.schema.json"
    if not registry_path.is_file(): errors.append("missing skills/registry.yaml")
    if not schema_path.is_file(): errors.append("missing schemas/skill-registry.schema.json")
    if errors:
        print("\n".join(f"ERROR: {e}" for e in errors)); return 1
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    for error in Draft202012Validator(schema).iter_errors(registry):
        errors.append(f"schema:{'/'.join(map(str,error.path))}: {error.message}")
    seen = set()
    for skill in registry.get("skills", []):
        sid = skill.get("id")
        if sid in seen: errors.append(f"duplicate skill id: {sid}")
        seen.add(sid)
        local = skill.get("local_path") or skill.get("local_fallback")
        if not local or not safe_rel(local):
            errors.append(f"{sid}: unsafe or missing local path")
            continue
        local_path = root / local
        if not local_path.is_file():
            errors.append(f"{sid}: missing local fallback {local}")
        elif sha256(local_path) != skill.get("sha256"):
            errors.append(f"{sid}: sha256 mismatch for {local}")
        if skill.get("source_type") == "external_reference":
            if skill.get("authority") != "reference_only":
                errors.append(f"{sid}: external authority must be reference_only")
            if skill.get("upstream_scripts_allowed") is not False:
                errors.append(f"{sid}: upstream scripts must be blocked")
            meta = skill.get("source_metadata")
            if not meta or not safe_rel(meta) or not (root / meta).is_file():
                errors.append(f"{sid}: missing SOURCE.yaml")
    if errors:
        print("\n".join(f"ERROR: {e}" for e in errors))
        print(f"\nSKILL REGISTRY VALIDATION FAILED: {len(errors)} error(s)")
        return 1
    print("SKILL REGISTRY VALIDATION PASSED")
    print(f"Skills validated: {len(registry.get('skills', []))}")
    return 0
if __name__ == "__main__":
    sys.exit(main())
