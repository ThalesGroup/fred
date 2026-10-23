"""Offline release preparation tests with a small tagged repository."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from libs_version import (  # noqa: E402
    candidates,
    package_dir,
    patch_after,
    prepare,
    rewrite,
    verify_locks,
)
import validate_python_release as release_validator  # noqa: E402


def run_git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def build_artifacts(package: Path) -> None:
    data = tomllib.loads((package / "pyproject.toml").read_text())["project"]
    name, version = data["name"], data["version"]
    stem = name.replace("-", "_")
    metadata = f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n"
    for requirement in data.get("dependencies", []):
        metadata += f"Requires-Dist: {requirement}\n"
    dist = package / "target" / "dist"
    dist.mkdir(parents=True)
    with zipfile.ZipFile(dist / f"{stem}-{version}-py3-none-any.whl", "w") as archive:
        archive.writestr(f"{stem}-{version}.dist-info/METADATA", metadata)
    payload = metadata.encode()
    with tarfile.open(dist / f"{stem}-{version}.tar.gz", "w:gz") as archive:
        info = tarfile.TarInfo(f"{stem}-{version}/PKG-INFO")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


class ReleaseFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        run_git(root, "init", "-q")
        run_git(root, "config", "user.email", "test@example.com")
        run_git(root, "config", "user.name", "Release Test")
        for name in ("fred-pod", "fred-core", "fred-sdk", "fred-runtime"):
            self.write(
                f"libs/{name}/pyproject.toml",
                f'[project]\nname = "{name}"\nversion = "4.5.0"\n',
            )
        self.write(
            "libs/fred-sdk/pyproject.toml",
            '[project]\nname = "fred-sdk"\nversion = "4.5.0"\n'
            'dependencies = ["fred-core>=4.5.0"]\n',
        )
        self.write(
            "libs/fred-runtime/pyproject.toml",
            '[project]\nname = "fred-runtime"\nversion = "4.5.0"\n'
            'dependencies = ["fred-core>=4.5.0", "fred-sdk[agents]>=4.5.0"]\n',
        )
        for name in ("documents", "other", "mcp"):
            self.write(
                f"libs/capabilities/fred-capability-{name}/pyproject.toml",
                f'[project]\nname = "fred-capability-{name}"\nversion = "4.5.0"\n'
                'dependencies = ["fred-sdk[agents]>=4.5.0"]\n',
            )
        self.manifest_a = Path(
            "libs/capabilities/fred-capability-documents/a/capability.py"
        )
        self.manifest_b = Path(
            "libs/capabilities/fred-capability-documents/b/capability.py"
        )
        for name, path in (("a", self.manifest_a), ("b", self.manifest_b)):
            self.write(
                path,
                f"from fred_sdk import CapabilityManifest\n{name} = "
                f'CapabilityManifest(id="{name}", version="0.1.0")\n',
            )
        for chart in ("agent-pod", "knowledge-base"):
            self.write(f"deploy/charts/{chart}/Chart.yaml", 'appVersion: "4.5.0"\n')
        self.write(
            "apps/consumer/uv.lock",
            """[[package]]
name = "fred-core"
version = "4.5.0"
source = { editable = "../../libs/fred-core" }
[[package]]
name = "fred-sdk"
version = "4.5.0"
source = { editable = "../../libs/fred-sdk" }
[[package]]
name = "fred-runtime"
version = "4.5.0"
source = { editable = "../../libs/fred-runtime" }
[[package]]
name = "fred-capability-documents"
version = "4.5.0"
source = { editable = "../../libs/capabilities/fred-capability-documents" }
""",
        )
        run_git(root, "add", ".")
        run_git(root, "commit", "-qm", "baseline")
        run_git(root, "tag", "code/v1.0.0")

    def write(self, path: str | Path, content: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def change_documents(self) -> None:
        self.write(
            "libs/capabilities/fred-capability-documents/feature.py",
            "enabled = True\n",
        )
        path = self.root / self.manifest_a
        path.write_text(path.read_text() + "modified = True\n")


class RewriteTest(unittest.TestCase):
    def test_selected_floors_and_project_version_only(self) -> None:
        source = """[project]
name = "fred-capability-x"
version = "0.1.2"
dependencies = ["fred-sdk[agents]>=4.1.0", "fred-core>=4.1.0", "pydantic>=2.7,<3"]
[tool.other]
version = "9.9.9"
"""
        result = rewrite(source, "0.1.3", {"fred-sdk": "4.5.1"})
        self.assertIn('version = "0.1.3"', result)
        self.assertIn('"fred-sdk[agents]>=4.5.1"', result)
        self.assertIn('"fred-core>=4.1.0"', result)
        self.assertIn('version = "9.9.9"', result)

    def test_rejects_complex_owned_floor(self) -> None:
        source = (
            '[project]\nname = "fred-capability-x"\nversion = "0.1.0"\n'
            'dependencies = ["fred-sdk>=4.5.0,<5"]\n'
        )
        with self.assertRaisesRegex(ValueError, "only a single"):
            rewrite(source, "0.1.1", {"fred-sdk": "4.5.1"})

    def test_rejects_lowering_an_existing_floor(self) -> None:
        source = (
            '[project]\nname = "fred-capability-x"\nversion = "0.1.0"\n'
            'dependencies = ["fred-sdk>=4.6.0"]\n'
        )
        with self.assertRaisesRegex(ValueError, "floor exceeds prepared"):
            rewrite(source, "0.1.1", {"fred-sdk": "4.5.1"})

    def test_patch_requires_stable_semver(self) -> None:
        self.assertEqual(patch_after("4.5.0"), "4.5.1")
        with self.assertRaisesRegex(ValueError, "stable"):
            patch_after("4.5.0-rc1")


class PrepareTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = ReleaseFixture(self.root)

    def test_selected_package_and_manifest_are_idempotent(self) -> None:
        self.fixture.change_documents()
        self.assertIn("fred-capability-documents", candidates(self.root, "code/v1.0.0"))
        self.assertNotIn("fred-capability-other", candidates(self.root, "code/v1.0.0"))

        uv = self.root / "uv"
        uv.write_text(
            "#!/bin/sh\ncat > uv.lock <<'LOCK'\n"
            '[[package]]\nname = "fred-core"\nversion = "4.5.1"\n'
            'source = { editable = "../../libs/fred-core" }\n'
            '[[package]]\nname = "fred-sdk"\nversion = "4.5.1"\n'
            'source = { editable = "../../libs/fred-sdk" }\n'
            '[[package]]\nname = "fred-runtime"\nversion = "4.5.1"\n'
            'source = { editable = "../../libs/fred-runtime" }\n'
            '[[package]]\nname = "fred-capability-documents"\nversion = "4.5.1"\n'
            'source = { editable = "../../libs/capabilities/fred-capability-documents" }\n'
            "LOCK\n"
        )
        uv.chmod(0o755)
        args = (
            self.root,
            "code/v1.0.0",
            {"fred-capability-documents"},
            {self.fixture.manifest_a},
            False,
        )
        with patch.dict(os.environ, {"UV": str(uv)}):
            first = prepare(*args, apply=False)
            self.assertEqual(
                first["selected_packages"]["fred-capability-documents"], "4.5.1"
            )
            self.assertEqual(len(first["manifest_candidates"]), 2)
            self.assertEqual(len(first["selected_manifests"]), 1)
            self.assertEqual(
                first["unchanged_capabilities"]["fred-capability-other"], "4.5.0"
            )
            self.assertEqual(first["lock_projects"], ["apps/consumer"])
            prepare(*args, apply=True)
            prepare(*args, apply=True)

        self.assertIn(
            'version = "4.5.1"',
            (self.root / "libs/fred-core/pyproject.toml").read_text(),
        )
        self.assertIn(
            '"fred-sdk[agents]>=4.5.1"',
            (
                self.root / "libs/capabilities/fred-capability-documents/pyproject.toml"
            ).read_text(),
        )
        self.assertIn(
            'version = "4.5.0"',
            (
                self.root / "libs/capabilities/fred-capability-other/pyproject.toml"
            ).read_text(),
        )
        self.assertIn(
            'version="0.1.1"', (self.root / self.fixture.manifest_a).read_text()
        )
        self.assertIn(
            'version="0.1.0"', (self.root / self.fixture.manifest_b).read_text()
        )
        self.assertIn(
            'appVersion: "4.5.1"',
            (self.root / "deploy/charts/agent-pod/Chart.yaml").read_text(),
        )
        self.assertIn(
            'version = "4.5.0"',
            (self.root / "libs/fred-pod/pyproject.toml").read_text(),
        )
        verify_locks([self.root / "apps/consumer"], first["selected_packages"])
        packages = [
            self.root / "libs" / name
            for name in ("fred-pod", "fred-core", "fred-sdk", "fred-runtime")
        ]
        packages.extend(
            path.parent
            for path in sorted(
                (self.root / "libs/capabilities").glob("*/pyproject.toml")
            )
        )
        pending = {package_dir(self.root, name) for name in first["selected_packages"]}
        for package in pending:
            build_artifacts(package)
        self.assertEqual(
            release_validator.validate(
                packages, prepared=set(first["selected_packages"]), pending=pending
            ),
            [],
        )

    def test_manifest_free_package_can_advance(self) -> None:
        self.fixture.write(
            "libs/capabilities/fred-capability-mcp/code.py", "enabled = True\n"
        )
        report = prepare(
            self.root,
            "code/v1.0.0",
            {"fred-capability-mcp"},
            set(),
            False,
            apply=False,
        )
        self.assertEqual(report["selected_packages"]["fred-capability-mcp"], "4.5.1")
        self.assertEqual(report["selected_manifests"], {})

    def test_shared_libraries_keep_independent_patch_lines(self) -> None:
        versions = {"fred-core": "2.0.4", "fred-sdk": "5.6.7", "fred-runtime": "9.8.3"}
        for name, version in versions.items():
            path = self.root / "libs" / name / "pyproject.toml"
            path.write_text(
                path.read_text().replace('version = "4.5.0"', f'version = "{version}"')
            )
        sdk = self.root / "libs/fred-sdk/pyproject.toml"
        sdk.write_text(sdk.read_text().replace("fred-core>=4.5.0", "fred-core>=2.0.4"))
        runtime = self.root / "libs/fred-runtime/pyproject.toml"
        runtime.write_text(
            runtime.read_text()
            .replace("fred-core>=4.5.0", "fred-core>=2.0.4")
            .replace("fred-sdk[agents]>=4.5.0", "fred-sdk[agents]>=5.6.7")
        )
        run_git(self.root, "add", ".")
        run_git(self.root, "commit", "-qm", "independent baselines")
        run_git(self.root, "tag", "-f", "code/v1.0.0")

        report = prepare(self.root, "code/v1.0.0", set(), set(), False, apply=False)

        self.assertEqual(report["selected_packages"]["fred-core"], "2.0.5")
        self.assertEqual(report["selected_packages"]["fred-sdk"], "5.6.8")
        self.assertEqual(report["selected_packages"]["fred-runtime"], "9.8.4")

    def test_changed_pod_is_selected_independently(self) -> None:
        self.fixture.write("libs/fred-pod/README.md", "New config guidance.\n")
        report = prepare(self.root, "code/v1.0.0", set(), set(), True, apply=False)
        self.assertEqual(report["selected_packages"]["fred-pod"], "4.5.1")
        self.assertEqual(report["selected_packages"]["fred-runtime"], "4.5.1")

    def test_omitted_changed_package_stops_apply(self) -> None:
        self.fixture.change_documents()
        with self.assertRaisesRegex(ValueError, "need explicit selection"):
            prepare(self.root, "code/v1.0.0", set(), set(), False, apply=True)

    def test_unexpected_current_version_stops(self) -> None:
        self.fixture.write(
            "libs/fred-core/pyproject.toml",
            '[project]\nname = "fred-core"\nversion = "4.7.0"\n',
        )
        with self.assertRaisesRegex(ValueError, "independent publication"):
            prepare(self.root, "code/v1.0.0", set(), set(), False, apply=False)

    def test_rejects_unmodified_selected_capability(self) -> None:
        with self.assertRaisesRegex(ValueError, "no source change"):
            prepare(
                self.root,
                "code/v1.0.0",
                {"fred-capability-other"},
                set(),
                False,
                apply=False,
            )

    def test_dependency_floor_only_change_selects_capability(self) -> None:
        path = self.root / "libs/capabilities/fred-capability-other/pyproject.toml"
        path.write_text(
            path.read_text().replace(
                "fred-sdk[agents]>=4.5.0", "fred-sdk[agents]>=4.6.0"
            )
        )

        self.assertIn("fred-capability-other", candidates(self.root, "code/v1.0.0"))

    def test_lock_check_rejects_removed_local_package(self) -> None:
        lock_project = self.root / "apps/consumer"
        lock = lock_project / "uv.lock"
        lock.write_text(
            '[[package]]\nname = "fred-core"\nversion = "4.5.1"\n'
            'source = { editable = "../../libs/fred-core" }\n'
        )
        with self.assertRaisesRegex(ValueError, "missing local fred-sdk"):
            verify_locks(
                [lock_project],
                {"fred-core": "4.5.1", "fred-sdk": "4.5.1"},
                {lock_project: {"fred-core", "fred-sdk"}},
            )


if __name__ == "__main__":
    unittest.main()
