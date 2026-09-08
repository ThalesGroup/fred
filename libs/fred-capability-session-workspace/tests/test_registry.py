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

"""Registration and boot invariants for the `session_workspace` capability.

Installing the package IS the registration, so the entry point must be what a
booting pod actually finds.
"""

from __future__ import annotations

from fred_capability_session_workspace.capability import (
    SESSION_WORKSPACE_CAPABILITY_ID,
    SessionWorkspaceCapability,
)
from fred_runtime.capabilities.registry import CapabilityRegistry


def test_entry_point_discovery_finds_the_capability():
    registry = CapabilityRegistry()
    registry.discover()
    assert SESSION_WORKSPACE_CAPABILITY_ID in registry.ids()
    assert isinstance(
        registry.capability(SESSION_WORKSPACE_CAPABILITY_ID),
        SessionWorkspaceCapability,
    )


def test_capability_registers_and_validates_clean():
    registry = CapabilityRegistry()
    registry.register(SessionWorkspaceCapability())
    # No raise = every boot invariant holds, including the react-only rule a
    # middleware()-without-tools() capability must satisfy.
    registry.validate()


def test_manifest_is_react_only_with_no_owned_surface():
    manifest = SessionWorkspaceCapability.manifest
    assert manifest.id == SESSION_WORKSPACE_CAPABILITY_ID
    assert manifest.execution_models == ("react",)
    assert manifest.chat_parts == []
    assert manifest.side_panels == []
    assert manifest.tables == []
    assert manifest.router is None
    assert manifest.config_fields == []


def test_no_owned_migrations():
    assert SessionWorkspaceCapability.migrations_location() is None
