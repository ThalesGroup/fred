# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import fnmatch
import sqlite3
from pathlib import Path

import fred_runtime
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fred_runtime import migrations
from fred_runtime.__main__ import main
from fred_runtime.migrations import RUNTIME_ALEMBIC_DIR, upgrade_sqlite_database


def test_runtime_migration_tree_is_packaged_and_linear() -> None:
    """Verify discovery uses the package tree and preserves its revision chain."""
    package_dir = Path(fred_runtime.__file__).resolve().parent
    project_dir = Path(__file__).resolve().parents[1]
    assert RUNTIME_ALEMBIC_DIR == package_dir / "migrations"
    assert RUNTIME_ALEMBIC_DIR.is_dir()
    assert (RUNTIME_ALEMBIC_DIR / "env.py").is_file()
    assert (RUNTIME_ALEMBIC_DIR / "script.py.mako").is_file()
    assert {path.name for path in (RUNTIME_ALEMBIC_DIR / "versions").glob("*.py")} == {
        "__init__.py",
        "a1e2f3c4d5b6_create_session_history.py",  # pragma: allowlist secret
        "b2f3a4e5c6d7_add_exchange_id.py",  # pragma: allowlist secret
        "c3d4b5a6f7e8_add_team_and_instance.py",  # pragma: allowlist secret
        "e5f6a7b8c9d0_web_research_activity.py",  # pragma: allowlist secret
        "d4e5c6b7a8f9_drop_demo_echo_tables.py",  # pragma: allowlist secret
    }

    config = Config()
    config.set_main_option("script_location", str(RUNTIME_ALEMBIC_DIR))
    revisions = list(ScriptDirectory.from_config(config).walk_revisions(base="base"))

    assert [(revision.revision, revision.down_revision) for revision in revisions] == [
        ("e5f6a7b8c9d0", "d4e5c6b7a8f9"),  # pragma: allowlist secret
        ("d4e5c6b7a8f9", "c3d4b5a6f7e8"),  # pragma: allowlist secret
        ("c3d4b5a6f7e8", "b2f3a4e5c6d7"),  # pragma: allowlist secret
        ("b2f3a4e5c6d7", "a1e2f3c4d5b6"),  # pragma: allowlist secret
        ("a1e2f3c4d5b6", None),  # pragma: allowlist secret
    ]
    assert not (project_dir / "alembic").exists()


def test_upgrade_sqlite_database_applies_packaged_migrations(tmp_path: Path) -> None:
    """Run the packaged tree against SQLite and verify its schema reaches head."""
    database_path = tmp_path / "runtime.db"

    upgrade_sqlite_database(database_path)

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(session_history)")
        }
        assert connection.execute(
            "PRAGMA table_info(runtime_web_research_activity)"
        ).fetchall()
        revision = connection.execute(
            "SELECT version_num FROM alembic_version_runtime"
        ).fetchone()

    assert columns == {
        "session_id",
        "user_id",
        "rank",
        "timestamp",
        "role",
        "channel",
        "parts_json",
        "metadata_json",
        "exchange_id",
        "team_id",
        "agent_instance_id",
    }
    assert revision == ("e5f6a7b8c9d0",)  # pragma: allowlist secret


@pytest.mark.parametrize(
    ("locations", "expected"),
    [
        (
            (("alpha", "/alpha"), ("beta", "/beta")),
            ["/beta", "/alpha", str(RUNTIME_ALEMBIC_DIR)],
        ),
        ((), [str(RUNTIME_ALEMBIC_DIR)]),
    ],
)
def test_combined_downgrade_reverses_upgrade_order(
    monkeypatch: pytest.MonkeyPatch,
    locations: tuple[tuple[str, str], ...],
    expected: list[str],
) -> None:
    class Registry:
        def discover(self) -> None:
            pass

        def migration_locations(self) -> tuple[tuple[str, str], ...]:
            return locations

    calls: list[str] = []
    monkeypatch.setattr(migrations, "CapabilityRegistry", Registry)
    monkeypatch.setattr(
        migrations, "_downgrade", lambda location, *, label: calls.append(location)
    )

    result = migrations.run_all_downgrades()

    assert calls == expected
    assert result == [cap_id for cap_id, _ in reversed(locations)] + ["fred-runtime"]


def test_combined_downgrade_stops_after_a_tree_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Registry:
        def discover(self) -> None:
            pass

        def migration_locations(self) -> tuple[tuple[str, str], ...]:
            return (("alpha", "/alpha"), ("beta", "/beta"))

    calls: list[str] = []

    def fail_on_alpha(location: str, *, label: str) -> None:
        calls.append(location)
        if location == "/alpha":
            raise RuntimeError("downgrade failed")

    monkeypatch.setattr(migrations, "CapabilityRegistry", Registry)
    monkeypatch.setattr(migrations, "_downgrade", fail_on_alpha)

    with pytest.raises(RuntimeError, match="downgrade failed"):
        migrations.run_all_downgrades()

    assert calls == ["/beta", "/alpha"]


def test_downgrade_cli_accepts_only_one_revision(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        migrations,
        "run_all_downgrades",
        lambda: calls.append("called") or ["fred-runtime"],
    )

    for argv in (["downgrade"], ["downgrade", "base"]):
        with pytest.raises(SystemExit) as error:
            main(argv)
        assert error.value.code == 2
    assert calls == []

    assert main(["downgrade", "-1"]) == 0
    assert calls == ["called"]
    assert "downgraded: fred-runtime" in capsys.readouterr().out


def test_packaged_tree_is_not_excluded_from_the_docker_build_context() -> None:
    """
    Being packaged is not enough: the prod image installs fred-runtime from the
    source tree it COPYs, so a `.dockerignore` rule that drops a directory name
    also drops the migration tree - and `python -m fred_runtime migrate` then
    fails with ModuleNotFoundError in the pod while every test here still passes.

    This is not a full Docker matcher: it covers whole-name exclusions, the class
    of rule that can silently swallow the tree.
    """

    # Anchored on the test file, not the package: an editable install can resolve
    # fred_runtime into a different checkout than the one under test.
    dockerignore = Path(__file__).resolve().parents[3] / ".dockerignore"
    if not dockerignore.is_file():
        pytest.skip("fred-runtime consumed outside the monorepo build context")

    segments = {"fred_runtime", RUNTIME_ALEMBIC_DIR.name, "versions"}
    offenders = []
    for raw in dockerignore.read_text().splitlines():
        rule = raw.strip()
        if not rule or rule.startswith(("#", "!")):
            continue
        name = rule.removeprefix("**/").rstrip("/")
        if any(fnmatch.fnmatch(segment, name) for segment in segments):
            offenders.append(rule)

    assert offenders == [], (
        f"{dockerignore} excludes the packaged Alembic tree: {offenders}"
    )
