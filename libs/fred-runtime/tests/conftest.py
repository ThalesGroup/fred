# Copyright Thales 2025
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
"""Shared offline fixtures for fred-runtime tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fred_runtime.app.config import AgentPodConfig
from fred_sdk.contracts.ui_part_union import rebuild_ui_part_union
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage


def migrate_test_config(config: AgentPodConfig) -> AgentPodConfig:
    """
    Create the Alembic-owned runtime schema on a test config's SQLite file and
    return the config unchanged (so builders can `return migrate_test_config(...)`).

    Why this exists:
    - since #2290 no store creates its own tables: `session_history` DDL lives
      only in fred-runtime's Alembic tree, and `initialize_sql()` refuses to
      finish startup when the table is missing
    - a test that boots the pod therefore must do what a deployment's migration
      job (`python -m fred_runtime migrate`) does first

    It runs the real Alembic tree (`fred_runtime.migrations.upgrade_sqlite_database`,
    also used by the fred-agents suite), not hand-rolled DDL: a second definition
    of the schema in test code is the duplication #2290 just removed from
    production, and running the tree proves the migrations actually produce a
    bootable schema.
    """
    from fred_runtime.migrations import upgrade_sqlite_database

    sqlite_path = config.storage.postgres.sqlite_path
    if not sqlite_path:  # a Postgres-backed config needs the real migration job
        return config
    upgrade_sqlite_database(sqlite_path)
    return config


@pytest.fixture(autouse=True)
def _restore_base_ui_part_union() -> Iterator[None]:
    """
    Registry validation extends the process-wide `UiPart` union (#1977);
    every test must leave the process on the frozen base union so union
    membership never leaks between tests. No-op when nothing was registered.
    """

    yield
    rebuild_ui_part_union(())


class ToolFriendlyFakeChatModel(FakeMessagesListChatModel):
    """FakeMessagesListChatModel that silently accepts tool binding."""

    def bind_tools(
        self,
        tools: object,
        *,
        tool_choice: object = None,
        **kwargs: object,
    ) -> "ToolFriendlyFakeChatModel":
        return self


class StaticChatModelFactory:
    """Always returns the same pre-built model regardless of definition."""

    def __init__(self, model: ToolFriendlyFakeChatModel) -> None:
        self._model = model

    def build(self, definition: object, binding: object) -> ToolFriendlyFakeChatModel:
        return self._model

    def build_for_operation(
        self,
        *,
        definition: object,
        binding: object,
        purpose: object,
        operation: object = None,
    ) -> ToolFriendlyFakeChatModel:
        return self._model


@pytest.fixture
def minimal_config() -> AgentPodConfig:
    """Minimal offline AgentPodConfig with security disabled."""
    return AgentPodConfig.model_validate(
        {
            "security": {
                "m2m": {
                    "enabled": False,
                    "realm_url": "http://localhost/r",
                    "client_id": "test-m2m",
                },
                "user": {
                    "enabled": False,
                    "realm_url": "http://localhost/r",
                    "client_id": "test-user",
                },
                "authorized_origins": [],
            },
            "observability": {
                "kpi": {
                    "log": {"enabled": True},
                    "prometheus": {"enabled": False},
                    "opensearch": {"enabled": False},
                }
            },
        }
    )


@pytest.fixture
def fake_model() -> ToolFriendlyFakeChatModel:
    return ToolFriendlyFakeChatModel(responses=[AIMessage(content="done")])


@pytest.fixture
def static_factory(
    fake_model: ToolFriendlyFakeChatModel,
) -> StaticChatModelFactory:
    return StaticChatModelFactory(fake_model)
