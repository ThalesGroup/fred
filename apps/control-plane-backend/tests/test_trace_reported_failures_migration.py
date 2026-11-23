# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def test_sqlite_migration_backfills_only_active_incident_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Upgrade real legacy grants and verify their report boundaries survive."""
    app_dir = Path(__file__).resolve().parents[1]
    config = Config()
    config.set_main_option("script_location", str(app_dir / "alembic"))
    database = str(tmp_path / "control_plane.sqlite3")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database}")
    command.upgrade(config, "83adb40b71f5")  # pragma: allowlist secret

    boundary = {
        "exchange_id": "failed-turn",
        "first_rank": 3,
        "last_rank": 5,
        "turn_number": 2,
        "started_at": "2026-11-19T00:15:00.999999+01:00",
    }
    report = {
        "support_error_ref": "active-error",
        "cutoff": boundary,
        "failure_category": "http_400",
    }
    uncategorized = {
        "support_error_ref": "unknown-error",
        "cutoff": {**boundary, "started_at": "2026-11-19T01:00:00Z"},
        "failure_category": None,
    }
    grants = [
        ("active", "active", report, False),
        ("revoked", "active", {**report, "support_error_ref": "old-error"}, True),
        ("uncategorized", "uncategorized", uncategorized, False),
        ("absent", "absent", sa.null(), False),
        ("json-null", "json-null", sa.JSON.NULL, False),
    ]
    grant_time = datetime(2026, 11, 20)
    metadata = sa.MetaData()
    engine = sa.create_engine(sa.URL.create("sqlite", database=database))
    try:
        sessions = sa.Table("session_metadata", metadata, autoload_with=engine)
        consent = sa.Table("conversation_trace_consent", metadata, autoload_with=engine)
        with engine.begin() as connection:
            connection.execute(
                sessions.insert(),
                [
                    {
                        "session_id": session,
                        "team_id": "team",
                        "created_at": grant_time,
                        "updated_at": grant_time,
                    }
                    for session in sorted({session for _, session, _, _ in grants})
                ],
            )
            connection.execute(
                consent.insert(),
                [
                    {
                        "grant_id": grant_id,
                        "session_id": session,
                        "actor_id": "owner",
                        "source": "owner",
                        "exchange_id": "consent-cutoff",
                        "first_rank": 20,
                        "last_rank": 22,
                        "turn_number": 7,
                        "started_at": grant_time,
                        "granted_at": grant_time,
                        "revoked_at": grant_time if revoked else None,
                        "incident": incident,
                    }
                    for grant_id, session, incident, revoked in grants
                ],
            )

        command.upgrade(config, "4eea63270bc1")  # pragma: allowlist secret

        incidents = sa.Table(
            "conversation_trace_incident", metadata, autoload_with=engine
        )
        with engine.connect() as connection:
            rows = connection.execute(
                sa.select(incidents).order_by(incidents.c.started_at)
            )
            assert rows.all() == [
                (
                    "active",
                    "active-error",
                    "failed-turn",
                    3,
                    5,
                    2,
                    datetime(2026, 11, 18, 23, 15, 0, 999999),
                    "http_400",
                ),
                (
                    "uncategorized",
                    "unknown-error",
                    "failed-turn",
                    3,
                    5,
                    2,
                    datetime(2026, 11, 19, 1),
                    None,
                ),
            ]
            assert (
                connection.scalar(
                    sa.select(consent.c.incident).where(consent.c.grant_id == "active")
                )
                == report
            )
    finally:
        engine.dispose()
