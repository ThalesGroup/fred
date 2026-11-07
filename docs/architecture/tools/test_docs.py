# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Failure-path checks for the architecture freshness gate; no services required."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import docs


class ReferenceChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch.object(docs, "ROOT", self.root))

    def write(self, path, contents):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents)
        return target

    def schema(self, definitions):
        self.write("schema.json", json.dumps({"$defs": definitions}))

    def test_schema_closure_includes_nested_and_recursive_references_once(self):
        self.schema(
            {
                "Admission": {
                    "properties": {"connection": {"$ref": "#/$defs/Connection"}}
                },
                "Connection": {
                    "anyOf": [{"$ref": "#/$defs/Admission"}, {"type": "null"}]
                },
                "Unrelated": {"type": "string"},
            }
        )
        result = docs.schemas("schema.json", "Admission")
        self.assertEqual(result.count("### Admission\n"), 1)
        self.assertEqual(result.count("### Connection\n"), 1)
        self.assertNotIn("Unrelated", result)

    def test_missing_or_external_schema_reference_fails_instead_of_silent_omission(
        self,
    ):
        for ref in ["#/$defs/Renamed", "other.json#/$defs/Connection"]:
            with self.subTest(ref=ref):
                self.schema({"Admission": {"$ref": ref}})
                with self.assertRaises(ValueError):
                    docs.schemas("schema.json", "Admission")

    def test_openapi_types_use_the_same_closed_reference_renderer(self):
        self.write(
            "api.json",
            json.dumps(
                {
                    "components": {
                        "schemas": {
                            "Admission": {
                                "properties": {
                                    "connection": {
                                        "$ref": "#/components/schemas/Connection"
                                    }
                                }
                            },
                            "Connection": {"type": "string"},
                        }
                    }
                }
            ),
        )
        self.assertIn("### Connection", docs.schemas("api.json", "Admission"))

    def test_er_view_omits_external_edges_and_rejects_a_renamed_table(self):
        self.write(
            "schema.mmd",
            """erDiagram
"cp.offer" }o--|| "cp.source" : "source_id"
"cp.offer" }o--|| "cp.other" : "other_id"
"cp.offer" {
  text source_id FK
}
"cp.source" {
  text id
}
"cp.other" {
  text id
}
""",
        )
        result = docs.mermaid("schema.mmd", "cp.offer", "cp.source")
        self.assertIn('"source_id"', result)
        self.assertIn("text source_id FK", result)
        self.assertNotIn("cp.other", result)
        with self.assertRaises(ValueError):
            docs.mermaid("schema.mmd", "cp.renamed")

    def test_changed_source_fails_check_without_rewriting_the_reference(self):
        self.schema({"Binding": {"properties": {"api_root": {"type": "string"}}}})
        chapter = self.write(
            "reference.md",
            "<!-- generated: schemas schema.json Binding -->\n<!-- end generated -->\n",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            docs.generate(["reference.md"])
        original = chapter.read_bytes()
        self.assertEqual(docs.check(["reference.md"]), 0)
        self.schema(
            {"Binding": {"properties": {"new_required_field": {"type": "string"}}}}
        )
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(docs.check(["reference.md"]), 1)
        self.assertEqual(chapter.read_bytes(), original)

    def test_navigation_checks_files_headings_and_explicit_anchors(self):
        self.write("target.md", '# Configuration\n\n<a id="contract"></a>\n')
        self.write("source.rs", "// source\n")
        self.write(
            "reference.md",
            "[chapter](target.md#configuration) [alias](target.md#contract) [source](source.rs)\n````\n````\n",
        )
        self.assertEqual(docs.links(["reference.md"]), 0)
        for link in ["missing.rs", "target.md#renamed"]:
            with self.subTest(link=link):
                self.write("reference.md", f"[broken]({link})\n")
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(docs.links(["reference.md"]), 1)

    def test_navigation_ignores_example_links_in_fenced_code(self):
        self.write("reference.md", "```markdown\n[example](missing.md)\n```\n")
        self.assertEqual(docs.links(["reference.md"]), 0)


if __name__ == "__main__":
    unittest.main()
