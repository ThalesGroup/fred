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

"""Registration and boot invariants for the `subagent` capability (RFC §4, §7).

Installing the package IS the registration, so the entry point must be what a
booting pod actually finds — not a class a test remembered to register by hand.
"""

from __future__ import annotations

from fred_capability_subagent.capability import (
    SUBAGENT_CAPABILITY_ID,
    SubAgentCapability,
)
from fred_runtime.capabilities.registry import CapabilityRegistry


def test_entry_point_discovery_finds_the_capability():
    registry = CapabilityRegistry()
    registry.discover()
    assert SUBAGENT_CAPABILITY_ID in registry.ids()
    assert isinstance(registry.capability(SUBAGENT_CAPABILITY_ID), SubAgentCapability)


def test_capability_registers_and_validates_clean():
    registry = CapabilityRegistry()
    registry.register(SubAgentCapability())
    # No raise = every boot invariant holds (id charset, env, team scope).
    registry.validate()


def test_manifest_is_a_plain_tool_capability():
    manifest = SubAgentCapability.manifest
    assert manifest.id == SUBAGENT_CAPABILITY_ID
    assert manifest.kind == "tool"
    # tools()-only, so it must stay usable on both execution models.
    assert manifest.execution_models == ("react", "graph")
    assert manifest.chat_parts == []
    assert manifest.side_panels == []
    assert manifest.tables == []
    assert manifest.router is None
    assert [f.key for f in manifest.config_fields] == ["max_depth", "prompt_mode"]


def test_no_owned_migrations():
    assert SubAgentCapability.migrations_location() is None
