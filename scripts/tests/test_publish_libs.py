"""Exercise the real release Makefile with local fake packages and no network."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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
                    f'publish-dry-run:\n\t@echo build:{name} >> "$$PUBLISH_TEST_TRACE"\n'
                    + f'publish:\n\t@echo publish:{name} >> "$$PUBLISH_TEST_TRACE"\n'
                )

            bin_dir = project / "bin"
            bin_dir.mkdir()
            curl = bin_dir / "curl"
            _ = curl.write_text('#!/bin/sh\nprintf "%s" "$PUBLISH_TEST_STATUS"\n')
            curl.chmod(0o755)
            env = {
                key: value
                for key, value in os.environ.items()
                if key not in {"MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES"}
            }
            env.update(
                PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                PYPI_TOKEN="offline-test-only",  # pragma: allowlist secret
                PUBLISH_TEST_TRACE=str(trace),
            )

            for status in ("404", "200"):
                for options, cwd in (
                    ([], project),
                    (["-C", str(project)], Path(temporary)),
                    (["--print-directory"], project),
                ):
                    with self.subTest(status=status, options=options):
                        trace.unlink(missing_ok=True)
                        completed = subprocess.run(
                            [
                                "make",
                                *options,
                                "publish-libs",
                                "PYPI_PACKAGES=first second",
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


if __name__ == "__main__":
    _ = unittest.main()
