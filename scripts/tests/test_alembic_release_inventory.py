"""Release head inventory coverage for real and synthetic Alembic trees."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "alembic_release_inventory.py"
spec = importlib.util.spec_from_file_location("alembic_release_inventory", SCRIPT)
inventory = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = inventory
spec.loader.exec_module(inventory)
REPOSITORY = SCRIPT.parent.parent
COMMIT = "a" * 40


def write_revision(tree: Path, identifier: str, parents=None, description="Add a table") -> None:
    versions = tree / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    (tree / "env.py").write_text("", encoding="utf-8")
    (versions / f"{identifier}.py").write_text(
        f'"""{description}"""\nrevision = {identifier!r}\ndown_revision = {parents!r}\n',
        encoding="utf-8",
    )


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tree = self.root / "apps" / "example-backend" / "alembic"

    def test_discovers_all_current_migration_owners(self):
        trees = inventory.discover_trees(REPOSITORY)
        owners = {tree.owner for tree in trees}
        self.assertEqual(
            owners,
            {
                "control-plane-backend",
                "knowledge-flow-backend",
                "fred-runtime",
                "fred-capability-ppt-filler",
                "fred-capability-writable-document",
            },
        )
        for tree in trees:
            self.assertIn(tree.head, {revision.identifier for revision in tree.revisions})
            self.assertEqual(
                len(tree.revisions),
                len(list((REPOSITORY / tree.path / "versions").glob("*.py")))
                - int((REPOSITORY / tree.path / "versions" / "__init__.py").exists()),
            )

    def test_new_component_is_discovered_and_output_is_stable(self):
        write_revision(self.tree, "root", description="Create records")
        write_revision(self.tree, "latest", "root", "Add records")
        capability = (
            self.root / "libs" / "capabilities" / "new-capability" / "pkg" / "custom_migrations"
        )
        write_revision(capability, "cap_root")
        first = inventory.render_inventory(self.root, "3.12.0", COMMIT)
        second = inventory.render_inventory(self.root, "3.12.0", COMMIT)
        self.assertEqual(first, second)
        self.assertIn("| new-capability |", first)
        self.assertIn("| example-backend | `apps/example-backend/alembic` | `latest` |", first)
        self.assertIn("| new-capability | `libs/capabilities/new-capability/pkg/custom_migrations` | `cap_root` |", first)
        self.assertNotIn("`root`", first)
        self.assertNotIn("Create records", first)
        self.assertEqual(len([line for line in first.splitlines() if line.startswith("| ")]), 4)

    def test_rejects_broken_graphs(self):
        cases = {
            "missing parent": [("only", "absent")],
            "expected one head": [("first", None), ("second", None)],
            "cycle": [("first", "second"), ("second", "first"), ("head", None)],
            "duplicate revision": [("first", None), ("first", None)],
        }
        for error, revisions in cases.items():
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                tree = root / "apps" / "example-backend" / "alembic"
                for index, (identifier, parent) in enumerate(revisions):
                    write_revision(tree, f"file{index}", parent)
                    source = tree / "versions" / f"file{index}.py"
                    source.write_text(
                        source.read_text(encoding="utf-8").replace(
                            f"revision = 'file{index}'", f"revision = {identifier!r}"
                        ),
                        encoding="utf-8",
                    )
                with self.assertRaisesRegex(ValueError, error):
                    inventory.discover_trees(root)

    def test_rejects_non_literal_revision_metadata(self):
        write_revision(self.tree, "root")
        source = self.tree / "versions" / "root.py"
        source.write_text(
            source.read_text(encoding="utf-8").replace(
                "revision = 'root'", "revision = make_revision()"
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "must be a literal"):
            inventory.discover_trees(self.root)

    def test_configured_tree_cannot_be_silently_omitted(self):
        write_revision(self.tree, "root")
        project = self.root / "apps" / "example-backend" / "pyproject.toml"
        project.write_text(
            '[tool.alembic]\nscript_location = "%(here)s/another_migrations"\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "was not discovered"):
            inventory.discover_trees(self.root)
        project.write_text(
            '[tool.alembic]\nscript_location = "%(here)s/alembic"\n'
            'version_locations = ["%(here)s/extra_versions"]\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "unsupported Alembic version locations"):
            inventory.discover_trees(self.root)


if __name__ == "__main__":
    unittest.main()
