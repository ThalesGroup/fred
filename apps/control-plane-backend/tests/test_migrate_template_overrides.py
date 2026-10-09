# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Per-template team overrides become instance recommendations on upgrade."""

import importlib.util
import json
from pathlib import Path

import pytest
import sqlalchemy as sa

_PATH = (
    Path(__file__).parents[1]
    / "alembic/versions/e9026d8e4db6_team_model_settings_and_instance_recommendation.py"
)
_spec = importlib.util.spec_from_file_location("migrate_template_overrides", _PATH)
assert _spec is not None and _spec.loader is not None
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


def _tuning(**extra: object) -> str:
    return json.dumps({"role": "r", "description": "d", **extra})


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE team_routing_policy (team_id TEXT PRIMARY KEY, "
                "agent_profile_overrides_json TEXT)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE agent_instance (agent_instance_id TEXT PRIMARY KEY, "
                "team_id TEXT, source_agent_id TEXT, tuning_json TEXT)"
            )
        )
        yield connection
    engine.dispose()


def _insert_instance(conn, agent_instance_id, team_id, source_agent_id, tuning):
    conn.execute(
        sa.text("INSERT INTO agent_instance VALUES (:id, :team, :agent, :tuning)"),
        {
            "id": agent_instance_id,
            "team": team_id,
            "agent": source_agent_id,
            "tuning": tuning,
        },
    )


def _recommendations(conn) -> dict[str, object]:
    rows = conn.execute(
        sa.text("SELECT agent_instance_id, tuning_json FROM agent_instance")
    ).fetchall()
    return {
        row[0]: (
            json.loads(row[1]).get("recommended_chat_profile_id") if row[1] else "-"
        )
        for row in rows
    }


def test_override_fills_empty_keeps_existing_and_ignores_other_scopes(conn) -> None:
    conn.execute(
        sa.text("INSERT INTO team_routing_policy VALUES ('team-1', :overrides)"),
        {"overrides": json.dumps({"tmpl-t": "chat.p"})},
    )
    _insert_instance(conn, "i1", "team-1", "tmpl-t", _tuning(values={"k": 1}))
    _insert_instance(
        conn, "i2", "team-1", "tmpl-t", _tuning(recommended_chat_profile_id="chat.q")
    )
    _insert_instance(conn, "other-team", "team-2", "tmpl-t", _tuning())
    _insert_instance(conn, "other-template", "team-1", "tmpl-u", _tuning())
    _insert_instance(conn, "no-tuning", "team-1", "tmpl-t", None)

    copied = migration._copy_overrides_to_instances(conn)

    assert copied == 1
    assert _recommendations(conn) == {
        "i1": "chat.p",
        "i2": "chat.q",
        "other-team": None,
        "other-template": None,
        "no-tuning": "-",
    }
    # Unknown keys of the stored tuning survive the copy.
    tuning = conn.execute(
        sa.text("SELECT tuning_json FROM agent_instance WHERE agent_instance_id='i1'")
    ).scalar_one()
    assert json.loads(tuning)["values"] == {"k": 1}


def test_malformed_overrides_are_skipped(conn) -> None:
    conn.execute(
        sa.text("INSERT INTO team_routing_policy VALUES ('team-1', 'not json')")
    )
    _insert_instance(conn, "i1", "team-1", "tmpl-t", _tuning())

    assert migration._copy_overrides_to_instances(conn) == 0
    assert _recommendations(conn) == {"i1": None}
