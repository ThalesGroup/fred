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

    def trigger(
        self, name="identity", comment="assertion: immutability - stable identity", **values
    ):
        return {
            "table": "document",
            "trigger": name,
            "function": "protect_document",
            "when": "BEFORE UPDATE / ROW",
            "comment": comment,
            **values,
        }

    def test_trigger_catalogue_renders_families_sorted_then_tables_and_escapes_prose(self):
        self.write(
            "triggers.json",
            json.dumps([
                self.trigger("quota", "effect: update budgets"),
                self.trigger("scope", "assertion: consistency - same space"),
                self.trigger("z", table="z"),
                self.trigger("identity", "assertion: immutability - bytes | identity"),
            ]),
        )
        rendered = docs.render("triggers triggers.json")
        self.assertLess(rendered.index("`identity`"), rendered.index("`z`"))
        self.assertLess(rendered.index("`z`"), rendered.index("2. Cross-row consistency"))
        self.assertLess(
            rendered.index("2. Cross-row consistency"), rendered.index("3. Effects")
        )
        self.assertIn(r"bytes \| identity", rendered)
        self.assertIn("BEFORE UPDATE / ROW", rendered)
        self.assertIn("`protect_document`", rendered)

    def test_trigger_catalogue_rejects_missing_or_malformed_comments(self):
        for comment in [
            None, "", "undocumented", "effect:", "assertion: ",
            "assertion: unknown - identity", "effect: writes\nmore",
        ]:
            with self.subTest(comment=comment):
                self.write("triggers.json", json.dumps([self.trigger(comment=comment)]))
                with self.assertRaisesRegex(ValueError, "document.identity"):
                    docs.render("triggers triggers.json")
        entry = self.trigger()
        del entry["comment"]
        self.write("triggers.json", json.dumps([entry]))
        with self.assertRaises(ValueError):
            docs.tidy_triggers("triggers.json")

    def test_trigger_catalogue_drift_fails_check_without_rewriting(self):
        self.write("triggers.json", json.dumps([self.trigger()]))
        chapter = self.write(
            "reference.md",
            "<!-- generated: triggers triggers.json -->\n<!-- end generated -->\n",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            docs.generate(["reference.md"])
        original = chapter.read_bytes()
        self.assertEqual(docs.check(["reference.md"]), 0)
        self.write(
            "triggers.json",
            json.dumps([self.trigger(), self.trigger("quota", "effect: update budgets")]),
        )
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(docs.check(["reference.md"]), 1)
        self.assertEqual(chapter.read_bytes(), original)

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

    def test_api_inventory_covers_methods_without_parameters_or_schema_prose(self):
        operations = {
            method: {
                "operationId": f"{method}_prompt",
                "responses": {"200": {"description": "OK"}},
            }
            for method in [
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "head",
                "options",
                "trace",
            ]
        }
        self.write(
            "api.json",
            json.dumps(
                {
                    "paths": {"/api/prompts": {"parameters": [], **operations}},
                    "components": {"schemas": {"Prompt": {"type": "string"}}},
                }
            ),
        )
        result = docs.openapi("api.json", inventory=True)
        self.assertIn("Paths are relative to `/api`.", result)
        for method in operations:
            self.assertEqual(result.count(f"| {method.upper()} | `/prompts` |"), 1)
        self.assertNotIn("Schemas", result)
        self.assertNotIn("### Prompt", result)
        self.assertIn("### Prompt", docs.openapi("api.json"))

    def test_api_inventory_distinguishes_inherited_public_and_optional_security(self):
        self.write(
            "api.json",
            json.dumps(
                {
                    "security": [{"bearer": []}],
                    "paths": {
                        f"/api/{name}": {"get": {"operationId": name, **override}}
                        for name, override in {
                            "private": {},
                            "public": {"security": []},
                            "anonymous": {"security": [{}]},
                            "optional": {"security": [{}, {"bearer": []}]},
                        }.items()
                    },
                }
            ),
        )
        result = docs.openapi("api.json", inventory=True)
        for name, status in [
            ("private", "Required"),
            ("public", "Public"),
            ("anonymous", "Public"),
            ("optional", "Optional"),
        ]:
            self.assertIn(f"| GET | `/{name}` | `{name}` | {status} |", result)

    def test_api_inventory_detects_removed_routes_without_rewriting(self):
        self.write(
            "api.json",
            json.dumps(
                {
                    "paths": {
                        "/api/prompts": {"get": {"operationId": "list"}},
                        "/api/prompts/{id}": {"get": {"operationId": "read"}},
                    }
                }
            ),
        )
        chapter = self.write(
            "reference.md",
            "<!-- generated: openapi-index api.json -->\n<!-- end generated -->\n",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            docs.generate(["reference.md"])
        original = chapter.read_bytes()
        self.assertEqual(docs.check(["reference.md"]), 0)
        self.write(
            "api.json",
            json.dumps(
                {
                    "paths": {
                        "/api/prompts": {"get": {"operationId": "list"}},
                    }
                }
            ),
        )
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(docs.check(["reference.md"]), 1)
        self.assertEqual(chapter.read_bytes(), original)

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

    def test_source_map_resolves_symbol_comment_and_relative_line_link(self):
        self.write(
            "src/prompts.rs",
            "// Copyright\n/// Own the definition.\n/// Keep A | B distinct.\n"
            "pub(super) async fn create<'e>() {}\n",
        )
        result = docs.source_map(
            ["src/prompts.rs::create"], self.root / "docs" / "reference.md"
        )
        self.assertIn("(../src/prompts.rs#L4)", result)
        self.assertIn("Own the definition. Keep A \\| B distinct.", result)

    def test_source_map_refuses_lost_ambiguous_or_undocumented_anchors(self):
        for source in [
            "/// Renamed.\nfn renamed() {}\n",
            "fn create() {}\n",
            "/// Detached.\n\nfn create() {}\n",
            "/// A.\nfn create() {}\n/// B.\nfn create() {}\n",
            "/// Attributes are outside this pilot.\n#[test]\nfn create() {}\n",
        ]:
            with self.subTest(source=source):
                self.write("src/prompts.rs", source)
                with self.assertRaises(ValueError):
                    docs.source_map(
                        ["src/prompts.rs::create"], self.root / "reference.md"
                    )

    def test_source_map_comment_drift_fails_check_without_rewriting(self):
        self.write("src/prompts.rs", "/// Original.\nfn create() {}\n")
        chapter = self.write(
            "docs/reference.md",
            "<!-- generated: source-map src/prompts.rs::create -->\n"
            "<!-- end generated -->\n",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            docs.generate(["docs/reference.md"])
        original = chapter.read_bytes()
        self.assertEqual(docs.check(["docs/reference.md"]), 0)
        self.assertEqual(docs.links(["docs/reference.md"]), 0)
        self.write("src/prompts.rs", "/// Changed.\nfn create() {}\n")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(docs.check(["docs/reference.md"]), 1)
        self.assertEqual(chapter.read_bytes(), original)

    def test_source_map_does_not_claim_to_detect_behavior_drift(self):
        self.write("src/prompts.rs", "/// Same claim.\nfn create() { old(); }\n")
        reference = ["src/prompts.rs::create"]
        chapter = self.root / "reference.md"
        original = docs.source_map(reference, chapter)
        self.write("src/prompts.rs", "/// Same claim.\nfn create() { changed(); }\n")
        self.assertEqual(docs.source_map(reference, chapter), original)


if __name__ == "__main__":
    unittest.main()
