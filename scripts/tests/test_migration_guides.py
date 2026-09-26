"""Policy regressions against real, temporary Git histories; no network or secrets."""

import importlib.util
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "migration_guides.py"
spec = importlib.util.spec_from_file_location("migration_guides", SCRIPT)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

NOTES = "docs/swift/ops/migrations"
RELEASES = "docs/swift/ops/releases"


def note(impact="none", **fields):
    meta = {
        "schema": 1,
        "title": "Synthetic migration declaration",
        "impact": impact,
        "configuration": "none",
        "configuration_reason": "No production configuration changes in this contribution.",
    }
    if impact == "none":
        meta["no_action_reason"] = (
            "Only internal documentation changes; ordinary deployment suffices."
        )
    meta.update(fields)
    body = "\n\n".join(
        f"## {s}\n\nNo additional operations are needed for this synthetic example."
        for s in m.SECTIONS
    )
    return "---\n" + m.yaml.safe_dump(meta, sort_keys=False) + "---\n" + body + "\n"


class ParserTests(unittest.TestCase):
    def test_all_impacts(self):
        for impact in m.IMPACTS:
            self.assertEqual(m.parse_note("x.md", note(impact)).impact, impact)

    def test_invalid_metadata_and_empty_content(self):
        bad = [
            note().replace("impact: none", "impact: patch"),
            note().replace("impact: none", "impact: []"),
            note().replace("schema: 1", "schema: true"),
            note().replace("title:", "impact: minor\ntitle:"),
            note().replace("## Rollback", "## Unknown"),
            note().replace(
                "## Upgrade\n\nNo additional operations are needed for this synthetic example.",
                "## Upgrade\n\n",
            ),
            note(no_action_reason=""),
            note(no_action_reason="TODO replace me later"),
            note(configuration_reason="TBD fill in later"),
            note(unknown="value"),
        ]
        for text in bad:
            with self.subTest(text=text), self.assertRaises(m.Invalid):
                m.parse_note("x.md", text)

    def test_versions_and_minimum(self):
        self.assertEqual(m.minimum("2.2.3", "none"), "2.2.4")
        self.assertEqual(m.minimum("2.2.3", "minor"), "2.3.0")
        self.assertEqual(m.minimum("2.2.3", "major"), "3.0.0")
        for v in ["2.3.0-rc.1", "2.3.0-rc1", "2.3.0"]:
            self.assertEqual(m.version(v), (2, 3, 0))
        for v in ["02.3.0", "2.3", "2.3.0-01", "-v2.3.0", "$(id)"]:
            with self.subTest(v=v), self.assertRaises(m.Invalid):
                m.version(v)

    def test_order_and_exported_links(self):
        a = m.parse_note(f"{NOTES}/a.md", note("minor", after=["b"]))
        b = m.parse_note(f"{NOTES}/b.md", note("minor"))
        self.assertEqual([Path(n.path).stem for n in m.ordered([a, b])], ["b", "a"])
        b.meta["after"] = ["a"]
        with self.assertRaises(m.Invalid):
            m.ordered([a, b])
        a.body += "\n[rotation](../WORKLOAD_SECRET_ROTATION.md#procedure)\n[here](#upgrade)\n[ref]: ../../platform/REBAC.md\n"
        text = m.exported_body(a, "https://github.com/org/repo", "2.3.0")
        self.assertIn(
            "blob/code/v2.3.0/docs/swift/ops/WORKLOAD_SECRET_ROTATION.md#procedure",
            text,
        )
        self.assertIn("blob/code/v2.3.0/docs/swift/ops/migrations/a.md#upgrade", text)
        self.assertIn("blob/code/v2.3.0/docs/swift/platform/REBAC.md", text)


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-b", "swift")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Migration Tests")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "tag.gpgsign", "false")
        self.write("deploy/charts/fred/values.yaml", "enabled: false\n")
        self.commit("initial")
        self.git("tag", "-a", "code/v1.2.3", "-m", "previous release")
        self.base = self.git("rev-parse", "HEAD")
        self.policy = {
            "schema": 1,
            "notes_dir": NOTES,
            "releases_dir": RELEASES,
            "activation_base": self.base,
            "repository": "https://github.com/org/repo",
        }
        self.write(m.POLICY, json.dumps(self.policy))
        self.add_note("bootstrap")
        self.commit("install policy")
        self.installed = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.check_output(
            ["git", *args], cwd=self.root, text=True, stderr=subprocess.DEVNULL
        ).strip()

    def write(self, name, contents):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contents)

    def add_note(self, name, impact="none", **fields):
        self.write(f"{NOTES}/{name}.md", note(impact, **fields))

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "-m", message)

    def repo(self, **kwargs):
        return m.Repo(self.root, **kwargs)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=self.root,
            text=True,
            capture_output=True,
        )

    def test_pr_requires_new_note_for_docs_too(self):
        self.write("README.md", "documentation only\n")
        self.commit("docs without note")
        with self.assertRaisesRegex(m.Invalid, "Every PR"):
            self.repo().check_pr(self.installed)
        self.add_note("docs")
        self.assertEqual(len(self.repo(worktree=True).check_pr(self.installed)), 1)

    def test_base_advance_cannot_satisfy_pr(self):
        self.git("checkout", "-b", "topic")
        self.write("feature.txt", "some work\n")
        self.commit("feature")
        topic = self.git("rev-parse", "HEAD")
        self.git("checkout", "swift")
        self.add_note("someone-else")
        self.commit("advance base")
        base = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(m.Invalid, "Every PR"):
            self.repo(head=topic).check_pr(base)

    def test_alembic_none_rejected(self):
        self.write(
            "apps/service/migrations/versions/new_revision.py", "revision = 'x'\n"
        )
        self.add_note("migration")
        with self.assertRaisesRegex(m.Invalid, "Alembic"):
            self.repo(worktree=True).check_pr(self.installed)
        self.add_note("migration", "minor")
        self.repo(worktree=True).check_pr(self.installed)

    def test_configuration_evidence(self):
        self.write("apps/service/config/configuration_prod.yaml", "new: true\n")
        self.add_note("config")
        with self.assertRaisesRegex(m.Invalid, "Configuration changes"):
            self.repo(worktree=True).check_pr(self.installed)
        self.add_note("config", "minor", configuration="production")
        with self.assertRaisesRegex(m.Invalid, "values.yaml"):
            self.repo(worktree=True).check_pr(self.installed)
        self.write("deploy/charts/fred/values.yaml", "enabled: false\n# comment\n")
        with self.assertRaisesRegex(m.Invalid, "Comment-only"):
            self.repo(worktree=True).check_pr(self.installed)
        self.write("deploy/charts/fred/values.yaml", "enabled: false\nnew: true\n")
        self.repo(worktree=True).check_pr(self.installed)
        self.add_note(
            "config",
            configuration="local",
            configuration_reason="Only the developer Docker Compose sample changes; production schema is unchanged.",
        )
        self.repo(worktree=True).check_pr(self.installed)

    def test_commented_option_removal_requires_chart_schema_evidence(self):
        chart = "deploy/charts/fred/values.yaml"
        schema_path = "deploy/charts/fred/values.schema.json"
        schema = {
            "properties": {
                "frontend": {
                    "anyOf": [
                        {"type": "null"},
                        {"properties": {"info_banner": {"type": "string"}}},
                    ]
                }
            }
        }
        self.write(chart, "enabled: false\n# info_banner: message\n")
        self.write(schema_path, json.dumps(schema))
        self.commit("document optional banner")
        base = self.git("rev-parse", "HEAD")
        self.add_note("remove-banner", "minor", configuration="production")
        removed = copy.deepcopy(schema)
        removed["properties"]["frontend"]["anyOf"][1]["properties"].clear()
        self.write(schema_path, json.dumps(removed))
        with self.assertRaisesRegex(m.Invalid, "values.yaml"):
            self.repo(worktree=True).check_pr(base)
        self.write(
            chart, "enabled: false\n# Announcements are now managed in the UI.\n"
        )
        self.repo(worktree=True).check_pr(base)
        self.commit("remove optional banner")
        self.repo().check_pr(base)

    def test_cosmetic_chart_schema_changes_do_not_prove_option_removal(self):
        schema_path = "deploy/charts/fred/values.schema.json"
        schema = {
            "description": "Old description",
            "examples": [{"properties": {"example_only": {}}}],
            "properties": {
                "frontend": {
                    "anyOf": [{"type": "null"}, {"properties": {"info_banner": {}}}]
                }
            },
        }
        self.write(schema_path, json.dumps(schema))
        self.commit("add chart schema")
        base = self.git("rev-parse", "HEAD")
        self.write("deploy/charts/fred/values.yaml", "enabled: false\n# comment\n")
        self.add_note("config", "minor", configuration="production")
        changed = copy.deepcopy(schema)
        changed["description"] = "New description"
        changed["examples"] = []
        reordered = copy.deepcopy(schema)
        reordered["properties"]["frontend"]["anyOf"].reverse()
        for candidate in (schema, changed, reordered):
            with self.subTest(schema=candidate):
                self.write(schema_path, json.dumps(candidate, indent=2))
                with self.assertRaisesRegex(m.Invalid, "Comment-only"):
                    self.repo(worktree=True).check_pr(base)
        (self.root / schema_path).unlink()
        with self.assertRaisesRegex(m.Invalid, "Comment-only"):
            self.repo(worktree=True).check_pr(base)

    def test_unrelated_tag_and_missing_history(self):
        self.git("checkout", "-b", "other", self.base)
        self.write("other", "different branch")
        self.commit("other")
        self.git("tag", "code/v99.0.0")
        self.git("checkout", "swift")
        self.assertEqual(self.repo().baseline(), "code/v1.2.3")
        with self.assertRaisesRegex(m.Invalid, "ancestor"):
            self.repo().baseline("code/v99.0.0")
        self.git("tag", "-d", "code/v1.2.3")
        with self.assertRaisesRegex(m.Invalid, "No stable"):
            self.repo().baseline()

    def test_major_dominates_and_rc_promotion(self):
        self.add_note("minor", "minor")
        self.add_note("major", "major")
        self.commit("changes")
        with self.assertRaisesRegex(m.Invalid, "insufficient"):
            m.release_plan(self.repo(), target="1.3.0")
        plan, _ = m.release_plan(self.repo(), target="2.0.0-rc.1")
        self.assertEqual(plan["minimum"], "2.0.0")
        self.git("tag", "code/v2.0.0-rc.1")
        plan, _ = m.release_plan(self.repo(), target="2.0.0")
        self.assertEqual(plan["base"], "code/v1.2.3")

    def test_legacy_audit_is_explicit(self):
        self.policy["activation_base"] = self.installed
        self.write(m.POLICY, json.dumps(self.policy))
        self.add_note("adoption")
        self.commit("activate later")
        plan, _ = m.release_plan(self.repo())
        self.assertIn("Legacy audit", plan["blockers"][0])
        self.add_note(
            "audit",
            "minor",
            legacy_range={"base": "code/v1.2.3", "through": self.installed},
        )
        plan, _ = m.release_plan(self.repo(worktree=True))
        self.assertEqual(plan["blockers"], [])

    def test_direct_uncovered_commit_and_explicit_followup(self):
        self.write("uncovered", "important change")
        self.commit("missing declaration")
        sha = self.git("rev-parse", "HEAD")
        plan, _ = m.release_plan(self.repo())
        self.assertIn(sha, plan["blockers"][0])
        self.add_note("followup", covers=[sha])
        plan, _ = m.release_plan(self.repo(worktree=True))
        self.assertEqual(plan["blockers"], [])

    def test_merge_contribution_does_not_require_note_per_commit(self):
        self.git("checkout", "-b", "topic")
        self.write("feature", "step 1")
        self.commit("development commit")
        self.add_note("feature", "minor")
        self.commit("complete PR declaration")
        self.git("checkout", "swift")
        self.git("merge", "--no-ff", "topic", "-m", "merge reviewed PR")
        plan, _ = m.release_plan(self.repo())
        self.assertEqual(plan["blockers"], [])
        self.assertIn(f"{NOTES}/feature.md", plan["notes"])

    def test_squash_note_must_not_cover_internal_pr_commits(self):
        self.git("checkout", "-b", "topic")
        self.write("feature", "step 1")
        self.commit("development commit")
        internal = self.git("rev-parse", "HEAD")
        self.add_note("feature", "minor", covers=[internal])
        self.commit("complete PR declaration")
        self.git("checkout", "swift")
        self.git("merge", "--squash", "topic")
        self.commit("squash reviewed PR")
        with self.assertRaisesRegex(m.Invalid, "Covered commit is not an ancestor"):
            m.release_plan(self.repo())
        self.add_note("feature", "minor")
        self.git("add", ".")
        self.git("commit", "--amend", "--no-edit")
        self.add_note("prepare")
        result = self.run_cli("generate", "--worktree", "--version", "1.3.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.git("add", ".")
        self.commit("prepare release")
        result = self.run_cli("verify", "--version", "1.3.0")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_published_note_is_immutable(self):
        self.git("tag", "code/v1.2.4")
        self.add_note("bootstrap", "minor")
        self.add_note("correction", "minor")
        with self.assertRaisesRegex(m.Invalid, "immutable"):
            m.release_plan(self.repo(worktree=True))
        (self.root / NOTES / "bootstrap.md").unlink()
        with self.assertRaisesRegex(m.Invalid, "immutable"):
            m.release_plan(self.repo(worktree=True))

    def test_generation_verification_and_stale_guide(self):
        self.add_note("prepare")
        result = self.run_cli("generate", "--worktree", "--version", "1.2.4")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.root / RELEASES / "v1.2.4/migration.md"
        before = output.read_bytes()
        self.assertEqual(
            self.run_cli("generate", "--worktree", "--version", "1.2.4").returncode, 0
        )
        self.assertEqual(before, output.read_bytes())
        self.commit("prepare release")
        self.git("tag", "-a", "code/v1.2.4", "-m", "release")
        self.git("tag", "-a", "chart/v1.2.4", "-m", "chart")
        result = self.run_cli("verify", "--version", "1.2.4", "--require-tags")
        self.assertEqual(result.returncode, 0, result.stderr)
        output.write_text(output.read_text() + "modified\n")
        self.add_note("edit-guide")
        self.commit("stale guide")
        self.assertNotEqual(
            self.run_cli(
                "verify", "--version", "1.2.4", "--base", "code/v1.2.3"
            ).returncode,
            0,
        )

    def test_deleted_unreleased_note_blocks_pr_and_release(self):
        self.add_note("feature", "major")
        self.commit("feature")
        prior = self.git("rev-parse", "HEAD")
        (self.root / NOTES / "feature.md").unlink()
        self.add_note("cleanup")
        self.commit("remove note")
        with self.assertRaisesRegex(m.Invalid, "Retain"):
            self.repo().check_pr(prior)
        plan, _ = m.release_plan(self.repo())
        self.assertTrue(any(prior in b for b in plan["blockers"]))

    def test_reviewed_explicit_baseline_survives_publication(self):
        self.git("tag", "code/v1.2.2", self.base)
        self.add_note("prepare")
        result = self.run_cli(
            "generate", "--worktree", "--version", "1.2.4", "--base", "code/v1.2.3"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.commit("release preparation")
        self.git("tag", "code/v1.2.4")
        self.git("tag", "chart/v1.2.4")
        result = self.run_cli("verify", "--version", "1.2.4", "--require-tags")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_prerelease_cannot_go_backwards(self):
        self.add_note("feature", "minor")
        self.commit("candidate")
        self.git("tag", "code/v1.3.0-rc.2")
        with self.assertRaisesRegex(m.Invalid, "advance"):
            m.release_plan(self.repo(), target="1.3.0-rc.1")
        plan, _ = m.release_plan(self.repo(), target="1.3.0")
        self.assertEqual(plan["version"], "1.3.0")

    def test_tag_pair_missing_mismatched_and_retry(self):
        self.git("tag", "code/v1.2.4")
        with self.assertRaisesRegex(m.Invalid, "Both"):
            m.verify_pair(self.repo(), "1.2.4")
        self.git("tag", "chart/v1.2.4", self.base)
        with self.assertRaisesRegex(m.Invalid, "same commit"):
            m.verify_pair(self.repo(), "1.2.4")
        self.git("tag", "-d", "chart/v1.2.4")
        self.git("remote", "add", "origin", str(self.root))
        with patch.object(
            m.time, "sleep", side_effect=lambda _: self.git("tag", "chart/v1.2.4")
        ) as sleep:
            m.verify_pair(self.repo(), "1.2.4", attempts=2, delay=0)
            sleep.assert_called_once()

    def test_empty_or_uncovered_release_cannot_generate(self):
        self.git("tag", "code/v1.2.4")
        result = self.run_cli("generate", "--version", "1.2.5")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No migration notes", result.stderr)


class WorkflowTests(unittest.TestCase):
    def test_publication_gates_and_attachments(self):
        root = SCRIPT.parents[1]
        for file, publish in [
            ("Build-and-push-docker.yml", "build-and-push"),
            ("Package-and-push-charts.yml", "package-and-push"),
        ]:
            data = m.yaml.safe_load((root / ".github/workflows" / file).read_text())
            self.assertEqual(data["jobs"][publish]["needs"], "migration-guide")
            self.assertIn(
                "Validate-release-migration.yml",
                data["jobs"]["migration-guide"]["uses"],
            )
            release = data["jobs"]["create-release"]
            upload = next(
                s
                for s in release["steps"]
                if s.get("uses", "").startswith("softprops/")
            )
            self.assertTrue(upload["with"]["fail_on_unmatched_files"])
            self.assertTrue(upload["with"]["files"].endswith("/migration.md"))

    def test_pr_check_runs_without_path_filters_or_secrets(self):
        root = SCRIPT.parents[1]
        data = m.yaml.load(
            (root / ".github/workflows/Check-migration-notes.yml").read_text(),
            Loader=m.yaml.BaseLoader,
        )
        self.assertIn("pull_request", data["on"])
        self.assertIn("merge_group", data["on"])
        self.assertNotIn("pull_request_target", data["on"])
        self.assertNotIn("paths", data["on"]["pull_request"])
        self.assertEqual(data["permissions"], {"contents": "read"})
        self.assertEqual(data["jobs"]["migration-notes"]["name"], "Migration notes")


if __name__ == "__main__":
    unittest.main()
