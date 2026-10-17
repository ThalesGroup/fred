"""Detect accidental direct and transitive reintroduction into the default graph."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "pdf_dependencies",
    Path(__file__).resolve().parents[1] / "check_pdf_dependencies.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DependencyProfileTest(unittest.TestCase):
    def test_extra_is_the_only_path_into_the_family(self):
        packages = {
            "knowledge-flow-backend": {
                "requires": ['pymupdf4llm; extra == "pymupdf"', "pypdf", "shared"]
            },
            "pymupdf4llm": {"requires": ["pymupdf", "pymupdf-layout", "shared"]},
        }
        self.assertFalse(module.FAMILY & module.runtime_closure(packages))
        self.assertEqual(
            module.FAMILY & module.runtime_closure(packages, ("pymupdf",)),
            module.FAMILY,
        )
        self.assertIn("shared", module.runtime_closure(packages))
        packages["shared"] = {"requires": ["pymupdf"]}
        self.assertEqual(module.FAMILY & module.runtime_closure(packages), {"pymupdf"})
        with self.assertRaisesRegex(RuntimeError, "reachability"):
            module.check(packages, False)
