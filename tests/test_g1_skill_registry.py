from pathlib import Path
import hashlib, subprocess, sys, yaml
ROOT = Path(__file__).resolve().parents[1]
def test_registry_hashes_match_local_files():
    registry = yaml.safe_load((ROOT / "skills" / "registry.yaml").read_text(encoding="utf-8"))
    for skill in registry["skills"]:
        local = skill.get("local_path") or skill.get("local_fallback")
        assert hashlib.sha256((ROOT / local).read_bytes()).hexdigest() == skill["sha256"]
def test_validator_passes():
    r = subprocess.run([sys.executable, "tools/validate_skill_registry.py"], cwd=ROOT, text=True, capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr
