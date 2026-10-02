# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Protect stored agent tuning when retiring search and GitHub MCP entries."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.sql.elements import TextClause

_PATH = (
    Path(__file__).parents[1]
    / "alembic/versions/ba2c3c7fd0c1_retire_legacy_mcp_document_search.py"
)
_spec = importlib.util.spec_from_file_location("retire_mcp_document_search", _PATH)
assert _spec is not None and _spec.loader is not None
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)

SEARCH = "mcp-knowledge-flow-mcp-text"
PREFIXED_SEARCH = f"mcp:{SEARCH}"
GITHUB = "mcp-web-github-readonly"
PREFIXED_GITHUB = f"mcp:{GITHUB}"


def test_removes_only_retired_selection_and_config() -> None:
    original = {
        "selected_capability_ids": [
            "other",
            SEARCH,
            PREFIXED_SEARCH,
            GITHUB,
            PREFIXED_GITHUB,
            "document_access",
            SEARCH,
        ],
        "capability_config": {
            SEARCH: {"config": {"library_ids": ["old"]}},
            PREFIXED_SEARCH: {"config": {}},
            GITHUB: {"config": {}},
            PREFIXED_GITHUB: {"config": {}},
            "other": {"config": {"secret": "keep"}},  # pragma: allowlist secret
        },
        "fields": {"prompts.system": "keep"},
    }
    before = json.dumps(original)
    updated = migration._remove_retired_mcp(original)
    assert updated == {
        "selected_capability_ids": ["other", "document_access"],
        "capability_config": {
            "other": {"config": {"secret": "keep"}},  # pragma: allowlist secret
        },
        "fields": {"prompts.system": "keep"},
    }
    assert json.dumps(original) == before
    assert migration._remove_retired_mcp(updated) == updated


@pytest.mark.parametrize(
    "selection",
    [{}, {"selected_capability_ids": None}, {"selected_capability_ids": []}],
)
def test_preserves_inheritance_and_explicit_empty_selection(
    selection: dict[str, object],
) -> None:
    original = {
        **selection,
        "capability_config": {
            SEARCH: {"config": {}},
            PREFIXED_GITHUB: {"config": {}},
        },
    }
    assert migration._remove_retired_mcp(original) == {
        **selection,
        "capability_config": {},
    }


@pytest.mark.parametrize("retired_id", [SEARCH, GITHUB])
def test_retired_only_selection_becomes_explicitly_empty(retired_id: str) -> None:
    assert migration._remove_retired_mcp({"selected_capability_ids": [retired_id]}) == {
        "selected_capability_ids": []
    }


def test_upgrade_preserves_other_columns_and_unchanged_payload_bytes(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE agent_instance (agent_instance_id TEXT PRIMARY KEY, "
                "tuning_json TEXT, enabled BOOLEAN, suspension_reason TEXT, updated_at TEXT)"
            )
        )
        payloads = {
            "retired": json.dumps(
                {"selected_capability_ids": [SEARCH, GITHUB], "fields": {"x": 1}}
            ),
            "config_only": json.dumps(
                {"capability_config": {PREFIXED_GITHUB: {"config": {}}}}
            ),
            "unchanged": '{ "selected_capability_ids": ["other"], "capability_config": null }',
            "null": None,
            "invalid": "private malformed value",
            "array": "[]",
            "json_null": "null",
        }
        for row_id, payload in payloads.items():
            conn.execute(
                sa.text(
                    "INSERT INTO agent_instance VALUES (:id, :tuning, false, 'keep suspension', 'original time')"
                ),
                {"id": row_id, "tuning": payload},
            )
        monkeypatch.setattr(migration.op, "get_bind", lambda: conn)
        migration.upgrade()
        rows = conn.execute(
            sa.text("SELECT * FROM agent_instance ORDER BY agent_instance_id")
        ).fetchall()
        actual = {row[0]: row[1] for row in rows}
        assert json.loads(actual["retired"]) == {
            "selected_capability_ids": [],
            "fields": {"x": 1},
        }
        assert json.loads(actual["config_only"]) == {"capability_config": {}}
        for row_id in payloads.keys() - {"retired", "config_only"}:
            assert actual[row_id] == payloads[row_id]
        assert all(
            tuple(row[2:]) == (0, "keep suspension", "original time") for row in rows
        )
        assert "Skipping agent_instance invalid" in caplog.text
        assert "private malformed value" not in caplog.text
        migration.upgrade()
        migration.downgrade()
        assert (
            conn.execute(
                sa.text("SELECT * FROM agent_instance ORDER BY agent_instance_id")
            ).fetchall()
            == rows
        )
    engine.dispose()


def test_concurrent_edit_aborts_instead_of_overwriting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ConcurrentConnection:
        def execute(
            self,
            statement: TextClause,
            parameters: dict[str, str] | None = None,
        ) -> SimpleNamespace:
            if parameters is None:
                return SimpleNamespace(
                    fetchall=lambda: [
                        (
                            "edited-agent",
                            json.dumps({"selected_capability_ids": [GITHUB]}),
                        )
                    ]
                )
            assert "tuning_json = :original" in str(statement)
            return SimpleNamespace(rowcount=0)

    monkeypatch.setattr(migration.op, "get_bind", ConcurrentConnection)
    with pytest.raises(RuntimeError, match="Concurrent edit.*edited-agent"):
        migration.upgrade()
