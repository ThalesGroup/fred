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
    }

    config = Config()
    config.set_main_option("script_location", str(RUNTIME_ALEMBIC_DIR))
    revisions = list(ScriptDirectory.from_config(config).walk_revisions(base="base"))

    assert [(revision.revision, revision.down_revision) for revision in revisions] == [
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
    assert revision == ("c3d4b5a6f7e8",)  # pragma: allowlist secret


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
