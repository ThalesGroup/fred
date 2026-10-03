"""Pull-request image selection against the real manifest and temporary Git histories."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "select_docker_images.py"
spec = importlib.util.spec_from_file_location("select_docker_images", SCRIPT)
s = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = s
spec.loader.exec_module(s)

MANIFEST = json.loads((ROOT / ".github" / "docker-images.json").read_text())
ALL = {image["name"] for image in MANIFEST["images"]}
KF = "knowledge-flow-backend"
KF_INPUTS = next(image for image in MANIFEST["images"] if image["name"] == KF)["pr_inputs"]


def built(*changed: str) -> set[str]:
    return {name for name, paths in s.select(MANIFEST, list(changed)).items() if paths}


class SelectionTest(unittest.TestCase):
    def test_documentation_builds_nothing(self):
        self.assertEqual(built("docs/swift/rfc/X.md", "openspec/changes/a/tasks.md", "CLAUDE.md"), set())

    def test_markdown_under_apps_is_code(self):
        # The fred-agents pyproject builds with its README, so it is not documentation.
        self.assertEqual(built("apps/fred-agents/README.md"), ALL - {KF})

    def test_frontend_application_builds_only_frontend(self):
        self.assertEqual(built("apps/frontend/src/App.tsx", "apps/frontend/package-lock.json"), {"frontend"})

    def test_npm_package_producer_builds_nothing(self):
        self.assertEqual(built("libs/frontend/ui/src/index.tsx"), set())

    def test_library_outside_knowledge_flow_skips_it(self):
        for path in (
            "libs/fred-sdk/fred_sdk/x.py",
            "libs/fred-runtime/pyproject.toml",
            "libs/capabilities/fred-capability-documents/a.py",
            "apps/control-plane-backend/control_plane_backend/a.py",
            "apps/fred-agents/dockerfiles/Dockerfile-prod",
        ):
            self.assertEqual(built(path), ALL - {KF}, path)

    def test_knowledge_flow_inputs_build_everything(self):
        for path in (
            "apps/knowledge-flow-backend/app/main.py",
            "libs/fred-core/fred_core/a.py",
            "libs/fred-pod/pyproject.toml",
            "scripts/download_models.py",
            "alembic.ini",
            ".dockerignore",
            ".github/docker-images.json",
        ):
            self.assertEqual(built(path), ALL, path)

    def test_missing_copy_regression_still_rebuilds(self):
        # Declaring a new local dependency edits a pyproject already in the inputs,
        # so the image builds and an absent COPY fails the check.
        self.assertIn(KF, built("apps/knowledge-flow-backend/pyproject.toml"))
        self.assertIn(KF, built("libs/fred-core/pyproject.toml"))

    def test_unknown_path_falls_back_to_general(self):
        self.assertEqual(built("new-top-level/thing.py"), ALL - {KF})

    def test_selection_is_a_union(self):
        self.assertEqual(built("docs/a.md", "apps/frontend/src/a.ts"), {"frontend"})
        self.assertEqual(built("apps/frontend/src/a.ts", "libs/fred-core/a.py"), ALL)

    def test_rule_naming_an_unknown_image_is_rejected(self):
        broken = json.loads(json.dumps(MANIFEST))
        broken["pr_selection"]["rules"][0]["images"] = ["ghost"]
        with self.assertRaises(ValueError):
            s.validate(broken)

    def test_pattern_depth(self):
        self.assertTrue(s.matches("README.md", "*.md"))
        self.assertFalse(s.matches("apps/x/README.md", "*.md"))
        self.assertTrue(s.matches("docs/a/b/c.md", "docs/**"))
        self.assertFalse(s.matches("docsx/a.md", "docs/**"))


class KnowledgeFlowInputsTest(unittest.TestCase):
    """The static list must cover what the image really consumes."""

    def covered(self, path: str) -> bool:
        return any(s.matches(path, p) or s.matches(path + "/x", p) for p in KF_INPUTS)

    def test_every_copy_source_is_an_input(self):
        dockerfile = ROOT / "apps/knowledge-flow-backend/dockerfiles/Dockerfile-prod"
        self.assertTrue(self.covered("apps/knowledge-flow-backend/dockerfiles/Dockerfile-prod"))
        for line in dockerfile.read_text().splitlines():
            if not line.startswith("COPY") or "--from=" in line:
                continue
            sources = [t for t in line.split()[1:-1] if not t.startswith("--")]
            for source in sources:
                path = source.rstrip("/").removesuffix("/.").removesuffix("*")
                self.assertTrue(self.covered(path), f"COPY {source} is not in pr_inputs")

    def test_every_local_dependency_is_an_input(self):
        pending, seen = [ROOT / "apps/knowledge-flow-backend"], set()
        while pending:
            project = pending.pop()
            if project in seen:
                continue
            seen.add(project)
            rel = project.relative_to(ROOT).as_posix()
            self.assertTrue(self.covered(rel), f"{rel} is a local dependency missing from pr_inputs")
            sources = tomllib.loads((project / "pyproject.toml").read_text())
            for source in sources.get("tool", {}).get("uv", {}).get("sources", {}).values():
                if isinstance(source, dict) and "path" in source:
                    pending.append((project / source["path"]).resolve())
        self.assertGreater(len(seen), 1)


class ChangedPathsTest(unittest.TestCase):
    def test_renames_and_deletions_report_both_sides(self):
        with tempfile.TemporaryDirectory() as tmp:

            def git(*args):
                return subprocess.run(
                    ["git", "-C", tmp, *args], check=True, capture_output=True, text=True
                ).stdout.strip()

            git("init", "-q", "-b", "main")
            git("config", "user.email", "t@example.com")
            git("config", "user.name", "t")
            for name in ("docs/moved.md", "docs/gone.md"):
                (Path(tmp) / name).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp) / name).write_text(name * 50)
            git("add", ".")
            git("commit", "-q", "-m", "base")
            base = git("rev-parse", "HEAD")
            (Path(tmp) / "libs/fred-core").mkdir(parents=True)
            # A non-ASCII name must come back verbatim, not C-quoted, to match pr_inputs.
            git("mv", "docs/moved.md", "libs/fred-core/café.md")
            git("rm", "-q", "docs/gone.md")
            git("commit", "-q", "-m", "head")

            changed = s.changed_paths(base, git("rev-parse", "HEAD"), repo=tmp)

        self.assertEqual(set(changed), {"docs/moved.md", "libs/fred-core/café.md", "docs/gone.md"})
        self.assertIn(KF, built(*changed))


if __name__ == "__main__":
    unittest.main()
