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

import pytest
from fred_runtime.app.config import AgentPodConfig
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage


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
