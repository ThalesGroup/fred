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

"""Deprecated, inert `AgentDefinition` reasoning fields still load."""

from __future__ import annotations

import fred_sdk.contracts.models as sdk_models
import pytest
from fred_sdk.authoring import ReActAgent


class _Plain(ReActAgent):
    agent_id: str = "test.plain"
    role: str = "r"
    description: str = "d"
    system_prompt_template: str = "x"


class _Legacy(_Plain):
    agent_id: str = "test.legacy"
    reasoning_enabled: bool = True
    reasoning_default_on: bool = True


def test_legacy_reasoning_fields_load_and_warn_once_per_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warned: list[str] = []
    monkeypatch.setattr(
        sdk_models.logger, "warning", lambda msg, *args: warned.append(msg % args)
    )
    monkeypatch.setattr(sdk_models, "_DEPRECATED_REASONING_WARNED", set())
    _Legacy()
    _Legacy()
    _Plain()
    assert len(warned) == 1
    assert "_Legacy" in warned[0]


def test_legacy_reasoning_fields_are_accepted_as_constructor_arguments() -> None:
    definition = _Plain(reasoning_enabled=True)
    # Inert: no surface reads it; the inspection payload does not carry it.
    assert "reasoning" not in definition.inspect().model_dump_json()
