from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import zipfile

import yaml


def write_fixture(root: Path) -> None:
    (root / "tools").mkdir(parents=True)
    (root / "projects" / "alpha").mkdir(parents=True)
    (root / "projects" / "beta").mkdir(parents=True)
    source = Path(__file__).resolve().parents[1] / "tools" / "build_all_packages.py"
    (root / "tools" / "build_all_packages.py").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (root / "catalog.yaml").write_text(
        "projects:\n  alpha:\n    package: projects/alpha/package.yaml\n  beta:\n    package: projects/beta/package.yaml\n",
        encoding="utf-8",
    )
    (root / "bundle.yaml").write_text(
        "schema_version: '1.0'\nbundle_id: test-all\nbundle_version: 2.3.4\nprojects: [alpha, beta]\narchive:\n  prefix: test-all\n  timestamp_format: '%Y%m%d-%H%M%SZ'\n  manifest_name: bundle-manifest.yaml\n",
        encoding="utf-8",
    )
    for project in ("alpha", "beta"):
        (root / "projects" / project / "package.yaml").write_text("package_version: 1.0.0\n", encoding="utf-8")
    (root / "tools" / "build_project_package.py").write_text(
        """from pathlib import Path\nimport argparse, yaml\np=argparse.ArgumentParser(); p.add_argument('project_id'); p.add_argument('--root'); p.add_argument('--output'); p.add_argument('--clean', action='store_true'); a=p.parse_args()\nr=Path(a.root); out=Path(a.output)/a.project_id/'1.0.0'; out.mkdir(parents=True, exist_ok=True)\n(out/'payload.txt').write_text(a.project_id, encoding='utf-8')\n(out/'package-manifest.yaml').write_text(yaml.safe_dump({'project_id': a.project_id, 'package_version': '1.0.0'}), encoding='utf-8')\n""",
        encoding="utf-8",
    )


def test_builds_versioned_timestamped_aggregate_zip(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    output = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, str(tmp_path / "tools" / "build_all_packages.py"), "--root", str(tmp_path), "--output", str(output), "--timestamp", "20260712-120000Z"],
        check=True,
        text=True,
        capture_output=True,
    )
    archive = output / "test-all-v2.3.4-20260712-120000Z.zip"
    assert archive.is_file()
    assert "AGGREGATE BUNDLE BUILD COMPLETE" in result.stdout
    with zipfile.ZipFile(archive) as handle:
        names = set(handle.namelist())
        assert "bundle-manifest.yaml" in names
        assert "projects/alpha/1.0.0/package-manifest.yaml" in names
        assert "projects/beta/1.0.0/package-manifest.yaml" in names
        manifest = yaml.safe_load(handle.read("bundle-manifest.yaml"))
    assert manifest["bundle_version"] == "2.3.4"
    assert manifest["generated_at"] == "2026-07-12T12:00:00Z"
    assert [item["project_id"] for item in manifest["projects"]] == ["alpha", "beta"]
    assert all(item["package_manifest_sha256"] for item in manifest["projects"])
    assert all(item["sha256"] for item in manifest["files"])
