"""Offline tests for scripts/libs_version.py (no uv, no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from libs_version import rewrite  # noqa: E402

NAMES = ["fred-pod", "fred-sdk", "fred-runtime"]

PYPROJECT = """\
[project]
name = "fred-capability-x"
version = "0.1.2"
dependencies = [
  "fred-sdk[agents]>=4.1.0",
  "fred-sdk-extras>=1.0.0",
  "pydantic>=2.7.0,<3.0.0",
]

[project.optional-dependencies]
dev = [
  "fred-runtime>=4.0.0",
  "fred-sdk[agents]",
]

[tool.other]
version = "9.9.9"

[tool.uv.sources]
fred-pod = { path = "../../fred-pod", editable = true }
"""


class RewriteTest(unittest.TestCase):
    def test_sets_the_project_version_and_every_floor_on_a_package(self) -> None:
        text = rewrite(PYPROJECT, NAMES, "4.4.3")

        self.assertIn('version = "4.4.3"\n', text)
        self.assertIn('"fred-sdk[agents]>=4.4.3"', text)
        self.assertIn('"fred-runtime>=4.4.3"', text)

    def test_leaves_everything_else_alone(self) -> None:
        text = rewrite(PYPROJECT, NAMES, "4.4.3")

        self.assertIn('version = "9.9.9"', text)
        self.assertIn('"fred-sdk-extras>=1.0.0"', text)
        self.assertIn('"pydantic>=2.7.0,<3.0.0"', text)
        self.assertIn('"fred-sdk[agents]",', text)
        self.assertIn('fred-pod = { path = "../../fred-pod", editable = true }', text)
        self.assertEqual(len(text.splitlines()), len(PYPROJECT.splitlines()))

    def test_refuses_a_specifier_it_does_not_own(self) -> None:
        pinned = PYPROJECT.replace('"fred-runtime>=4.0.0"', '"fred-runtime>=4.0.0,<5"')

        with self.assertRaisesRegex(ValueError, "fred-runtime>=4.0.0,<5"):
            rewrite(pinned, NAMES, "4.4.3")

    def test_refuses_a_pyproject_without_a_project_version(self) -> None:
        with self.assertRaisesRegex(ValueError, r"\[project\]"):
            rewrite('[project]\nname = "x"\n', NAMES, "4.4.3")


if __name__ == "__main__":
    unittest.main()
