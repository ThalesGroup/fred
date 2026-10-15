"""Exercise the real release Makefile with local fake packages and no network."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_python_release as release_validator  # noqa: E402
from validate_python_release import check_floors, validate  # noqa: E402


class PublishLibsTest(unittest.TestCase):
    def test_directory_announcements_never_become_package_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            _ = shutil.copyfile(ROOT / "Makefile", project / "Makefile")
            _ = shutil.copytree(
                ROOT / "scripts/makefiles", project / "scripts/makefiles"
            )
            trace = project / "trace"
            for name in ("first", "second"):
                package = project / name
                package.mkdir()
                _ = (package / "pyproject.toml").write_text(
                    f'[project]\nname = "{name}"\nversion = "1.0.0"\n'
                )
                _ = (package / "Makefile").write_text(
                    "publish-dry-run:\n"
                    + '\t@test "$(UV)" = "$$PUBLISH_TEST_UV"\n'
                    + f'\t@echo build:{name} >> "$$PUBLISH_TEST_TRACE"\n'
                    + "publish:\n"
                    + '\t@test "$(UV)" = "$$PUBLISH_TEST_UV"\n'
                    + f'\t@echo publish:{name} >> "$$PUBLISH_TEST_TRACE"\n'
                )

            bin_dir = project / "bin"
            bin_dir.mkdir()
            curl = bin_dir / "curl"
            _ = curl.write_text('#!/bin/sh\nprintf "%s" "$PUBLISH_TEST_STATUS"\n')
            curl.chmod(0o755)
            uv = bin_dir / "uv"
            _ = uv.write_text("#!/bin/sh\nexit 0\n")
            uv.chmod(0o755)
            env = {
                key: value
                for key, value in os.environ.items()
                if key not in {"MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES"}
            }
            env.update(
                PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                PYPI_TOKEN="offline-test-only",  # pragma: allowlist secret
                PUBLISH_TEST_TRACE=str(trace),
                PUBLISH_TEST_UV=str(uv),
            )

            for status in ("404", "200"):
                for options, cwd in (
                    ([], project),
                    (["-C", str(project)], Path(temporary)),
                    (["--print-directory"], project),
                ):
                    with self.subTest(status=status, options=options):
                        trace.unlink(missing_ok=True)
                        common = [
                            "PYPI_PACKAGES=first second",
                            "PYPI_RELEASE_CHECK=true",
                            "BASE_TAG=code/v1.0.0",
                        ]
                        built = subprocess.run(
                            ["make", *options, "publish-libs-dry-run", *common],
                            cwd=cwd,
                            env={**env, "PUBLISH_TEST_STATUS": status},
                            text=True,
                            capture_output=True,
                            timeout=10,
                        )
                        self.assertEqual(
                            built.returncode,
                            0,
                            built.stdout + built.stderr,
                        )
                        completed = subprocess.run(
                            [
                                "make",
                                *options,
                                "publish-libs",
                                *common,
                            ],
                            cwd=cwd,
                            env={**env, "PUBLISH_TEST_STATUS": status},
                            text=True,
                            capture_output=True,
                            timeout=10,
                        )
                        self.assertEqual(
                            completed.returncode,
                            0,
                            completed.stdout + completed.stderr,
                        )
                        expected = ["build:first", "build:second"]
                        if status == "404":
                            expected += ["publish:first", "publish:second"]
                        self.assertEqual(trace.read_text().splitlines(), expected)

    def test_validation_failure_stops_before_any_upload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            _ = shutil.copyfile(ROOT / "Makefile", project / "Makefile")
            package = project / "first"
            package.mkdir()
            _ = (package / "pyproject.toml").write_text(
                '[project]\nname = "first"\nversion = "1.0.0"\n'
            )
            trace = project / "trace"
            _ = (package / "Makefile").write_text(
                'publish:\n\t@echo publish:first >> "$$PUBLISH_TEST_TRACE"\n'
            )
            bin_dir = project / "bin"
            bin_dir.mkdir()
            uv = bin_dir / "uv"
            _ = uv.write_text("#!/bin/sh\nexit 0\n")
            uv.chmod(0o755)
            completed = subprocess.run(
                [
                    "make",
                    "publish-libs",
                    "PYPI_PACKAGES=first",
                    "PYPI_RELEASE_CHECK=false",
                    "BASE_TAG=code/v1.0.0",
                ],
                cwd=project,
                env={
                    **os.environ,
                    "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                    "PYPI_TOKEN": "offline-test-only",  # pragma: allowlist secret
                    "PUBLISH_TEST_TRACE": str(trace),
                },
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(trace.exists())

    def test_real_shared_publish_target_uploads_without_building(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "package"
            project.mkdir()
            target = project / "target" / "dist"
            target.mkdir(parents=True)
            _ = (target / "artifact.whl").write_text("wheel")
            _ = (target / "artifact.tar.gz").write_text("sdist")
            _ = (project / "pyproject.toml").write_text(
                '[project]\nname = "example"\nversion = "1.0.0"\n'
            )
            _ = (project / "Makefile").write_text(
                "PROJECT_NAME=example\n"
                "PYTHON=python3\n"
                f"include {ROOT / 'scripts/makefiles/python-publish.mk'}\n"
            )
            trace = project / "trace"
            uv = project / "uv"
            _ = uv.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$*" >> "$PUBLISH_TEST_TRACE"\n'
            )
            uv.chmod(0o755)
            validator = project / "validator.py"
            _ = validator.write_text("")

            completed = subprocess.run(
                [
                    "make",
                    "publish",
                    f"UV={uv}",
                    f"RELEASE_VALIDATOR={validator}",
                ],
                cwd=project,
                env={
                    **os.environ,
                    "PYPI_TOKEN": "offline-test-only",  # pragma: allowlist secret
                    "PUBLISH_TEST_TRACE": str(trace),
                },
                text=True,
                capture_output=True,
                timeout=10,
            )

            self.assertEqual(
                completed.returncode, 0, completed.stdout + completed.stderr
            )
            self.assertEqual(len(trace.read_text().splitlines()), 1)
            self.assertTrue(trace.read_text().startswith("publish "))


class ValidatePythonReleaseTest(unittest.TestCase):
    @staticmethod
    def _package(
        root: Path,
        name: str,
        *,
        version: str = "4.5.0",
        project_requirement: str | None = None,
        wheel_requirement: str | None = None,
        sdist_requirement: str | None = None,
    ) -> Path:
        package = root / name
        package.mkdir()
        dependencies = (
            f'dependencies = ["{project_requirement}"]\n' if project_requirement else ""
        )
        _ = (package / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "{version}"\n{dependencies}'
        )
        dist = package / "target" / "dist"
        dist.mkdir(parents=True)
        stem = name.replace("-", "_")

        wheel_metadata = f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n"
        if wheel_requirement:
            wheel_metadata += f"Requires-Dist: {wheel_requirement}\n"
        with zipfile.ZipFile(
            dist / f"{stem}-{version}-py3-none-any.whl", "w"
        ) as archive:
            archive.writestr(f"{stem}-{version}.dist-info/METADATA", wheel_metadata)

        sdist_metadata = f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n"
        if sdist_requirement:
            sdist_metadata += f"Requires-Dist: {sdist_requirement}\n"
        payload = sdist_metadata.encode()
        with tarfile.open(dist / f"{stem}-{version}.tar.gz", "w:gz") as archive:
            info = tarfile.TarInfo(f"{stem}-{version}/PKG-INFO")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        return package

    def test_rejects_a_stale_internal_floor(self) -> None:
        errors = check_floors(
            ["fred-core>=4.4.3", "fred-sdk[agents]>=4.5.0"],
            owner="fred-runtime",
            versions={
                "fred-core": "4.5.1",
                "fred-sdk": "4.5.1",
                "fred-runtime": "4.5.1",
            },
            prepared={"fred-core", "fred-sdk", "fred-runtime"},
        )

        self.assertEqual(len(errors), 2)
        self.assertIn("fred-core", errors[0])

    def test_accepts_mixed_project_versions_and_skips_unchanged_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            core = self._package(root, "fred-core", version="4.5.1")
            capability = self._package(root, "fred-capability-x", version="4.5.0")
            for artifact in (capability / "target" / "dist").iterdir():
                artifact.unlink()
            errors = validate([core, capability], pending={core})

        self.assertEqual(errors, [])

    def test_rejects_a_stale_sdist_floor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self._package(
                root,
                "fred-first",
                project_requirement="fred-second>=4.5.0",
                wheel_requirement="fred-second>=4.5.0",
                sdist_requirement="fred-second>=4.4.3",
            )
            second = self._package(root, "fred-second")

            errors = validate([first, second])

        self.assertEqual(len(errors), 1)
        self.assertIn("sdist internal requirements differ", errors[0])

    def test_tagged_package_map_rejects_omitted_changes_and_stale_floors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Release Test"], cwd=root, check=True
            )
            core = root / "libs/fred-core"
            capability = root / "libs/capabilities/fred-capability-x"
            core.mkdir(parents=True)
            capability.mkdir(parents=True)
            core_project = core / "pyproject.toml"
            cap_project = capability / "pyproject.toml"
            core_project.write_text(
                '[project]\nname = "fred-core"\nversion = "4.5.0"\n'
            )
            cap_project.write_text(
                '[project]\nname = "fred-capability-x"\nversion = "4.5.0"\n'
                'dependencies = ["fred-core>=4.5.0"]\n'
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "baseline"], cwd=root, check=True)
            subprocess.run(["git", "tag", "code/v1.0.0"], cwd=root, check=True)
            core_project.write_text(core_project.read_text().replace("4.5.0", "4.5.1"))
            (capability / "feature.py").write_text("enabled = True\n")
            with patch.object(release_validator, "ROOT", root):
                errors = validate([core, capability], base="code/v1.0.0", pending=set())
                self.assertTrue(any("version was not prepared" in e for e in errors))
                cap_project.write_text(
                    cap_project.read_text().replace(
                        'version = "4.5.0"', 'version = "4.5.1"'
                    )
                )
                errors = validate([core, capability], base="code/v1.0.0", pending=set())
                self.assertTrue(any("prepared fred-core floor" in e for e in errors))
                cap_project.write_text(
                    cap_project.read_text().replace(
                        "fred-core>=4.5.0", "fred-core>=4.5.1"
                    )
                )
                self.assertEqual(
                    validate([core, capability], base="code/v1.0.0", pending=set()),
                    [],
                )


if __name__ == "__main__":
    _ = unittest.main()
