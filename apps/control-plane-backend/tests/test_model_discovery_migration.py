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

"""Verify fresh and already-stamped schemas both acquire pod defaults."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load(filename: str):
    path = Path(__file__).parents[1] / "alembic/versions" / filename
    spec = importlib.util.spec_from_file_location("model_discovery_revision", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _run(engine, migration, operation: str) -> None:
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(migration, operation)()


def _pod_columns(engine) -> set[str]:
    return {
        column["name"] for column in sa.inspect(engine).get_columns("pod_chat_default")
    }


def test_model_discovery_revision_creates_pod_defaults() -> None:
    migration = _load("b42e9f19d4ca_model_display_name_overrides.py")
    repair = _load("7e0d93f21c6a_repair_applied_pod_defaults.py")
    engine = sa.create_engine("sqlite://")
    try:
        _run(engine, migration, "upgrade")
        _run(engine, repair, "upgrade")
        assert _pod_columns(engine) == {
            "runtime_id",
            "profile_id",
            "fallback_profile_id",
            "updated_by",
            "updated_at",
        }

        _run(engine, repair, "downgrade")
        _run(engine, migration, "downgrade")
        assert "pod_chat_default" not in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_repair_revision_creates_missing_pod_table_and_removes_old_global_fallback() -> (
    None
):
    repair = _load("7e0d93f21c6a_repair_applied_pod_defaults.py")
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "CREATE TABLE platform_model_fallback (model_capability VARCHAR PRIMARY KEY)"
                )
            )
        _run(engine, repair, "upgrade")
        assert "fallback_profile_id" in _pod_columns(engine)
        assert "revision" in {
            column["name"]
            for column in sa.inspect(engine).get_columns("model_discovery_source_state")
        }
        assert "platform_model_fallback" not in sa.inspect(engine).get_table_names()
        _run(engine, repair, "upgrade")
    finally:
        engine.dispose()


def test_repair_revision_adds_missing_fallback_and_discovery_revision_columns() -> None:
    repair = _load("7e0d93f21c6a_repair_applied_pod_defaults.py")
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "CREATE TABLE pod_chat_default (runtime_id VARCHAR(160) PRIMARY KEY, profile_id VARCHAR(256))"
                )
            )
            connection.execute(
                sa.text(
                    "CREATE TABLE model_discovery_source_state (source_id VARCHAR(64) PRIMARY KEY)"
                )
            )
        _run(engine, repair, "upgrade")
        assert "fallback_profile_id" in _pod_columns(engine)
        assert "revision" in {
            column["name"]
            for column in sa.inspect(engine).get_columns("model_discovery_source_state")
        }
    finally:
        engine.dispose()
