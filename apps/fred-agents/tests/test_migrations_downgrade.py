from __future__ import annotations

import sqlite3
from pathlib import Path

from fred_runtime.__main__ import main


def _database_state(database_path: Path) -> tuple[set[str], str | None, str | None]:
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        runtime_revision = connection.execute(
            "SELECT version_num FROM alembic_version_runtime"
        ).fetchone()
        capability_revision = connection.execute(
            "SELECT version_num FROM cap_writable_document_alembic_version"
        ).fetchone()
    return (
        tables,
        runtime_revision[0] if runtime_revision else None,
        capability_revision[0] if capability_revision else None,
    )


def test_cli_downgrades_only_selected_tree(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "migrations.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")

    assert main(["migrate"]) == 0
    tables, runtime_revision, capability_revision = _database_state(database_path)
    assert "runtime_web_research_activity" in tables
    assert "runtime_turn_steering" in tables
    assert "cap_writable_document_docs" in tables
    assert runtime_revision == "f6a7b8c9d0e1"  # pragma: allowlist secret
    assert capability_revision == "w1r2i3t4a5b6"  # pragma: allowlist secret

    assert main(["downgrade", "runtime", "-1"]) == 0
    tables, runtime_revision, capability_revision = _database_state(database_path)
    assert "runtime_web_research_activity" in tables
    assert "runtime_turn_steering" not in tables
    assert "cap_writable_document_docs" in tables
    assert runtime_revision == "e5f6a7b8c9d0"  # pragma: allowlist secret
    assert capability_revision == "w1r2i3t4a5b6"  # pragma: allowlist secret

    assert main(["downgrade", "capability:writable_document", "-1"]) == 0
    tables, runtime_revision, capability_revision = _database_state(database_path)
    assert "runtime_web_research_activity" in tables
    assert "runtime_turn_steering" not in tables
    assert "cap_writable_document_docs" not in tables
    assert runtime_revision == "e5f6a7b8c9d0"  # pragma: allowlist secret
    assert capability_revision is None

    assert main(["migrate"]) == 0
    tables, runtime_revision, capability_revision = _database_state(database_path)
    assert "runtime_web_research_activity" in tables
    assert "runtime_turn_steering" in tables
    assert "cap_writable_document_docs" in tables
    assert runtime_revision == "f6a7b8c9d0e1"  # pragma: allowlist secret
    assert capability_revision == "w1r2i3t4a5b6"  # pragma: allowlist secret
