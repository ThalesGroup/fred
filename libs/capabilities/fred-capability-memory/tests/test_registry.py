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

"""Registry boot invariants for the `memory` capability (#3698)."""

from __future__ import annotations

from importlib.metadata import EntryPoint
from typing import Any

from fred_capability_memory.capability import (
    MemoryCapability,
    MemoryConfig,
    MemoryNotePart,
)
from fred_runtime.capabilities import CapabilityRegistry
from fred_runtime.capabilities.registry import FRED_CAPABILITIES_ENTRY_POINT_GROUP
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.capability.base import ToolCarrierMiddleware
from fred_sdk.contracts.runtime import RuntimeServices

# Must match the [project.entry-points."fred.capabilities"] declaration in
# pyproject.toml — installing the package IS the registration.
_ENTRY_POINT_VALUE = "fred_capability_memory.capability:MemoryCapability"


def test_capability_registers_via_entry_point_and_boots() -> None:
    registry = CapabilityRegistry()
    entry = EntryPoint(
        name="memory",
        value=_ENTRY_POINT_VALUE,
        group=FRED_CAPABILITIES_ENTRY_POINT_GROUP,
    )
    registered = registry.discover(entry_points=[entry])

    assert registered == ["memory"]
    assert isinstance(registry.capability("memory"), MemoryCapability)
    registry.validate(env={})


def test_manifest_declares_the_contract_shape() -> None:
    manifest = MemoryCapability.manifest

    assert manifest.execution_models == ("react",)
    assert manifest.available_to_subagents is False
    assert manifest.chat_parts == [MemoryNotePart]
    assert [field.key for field in manifest.config_fields] == [
        "confirm_after_external_content"
    ]
    assert manifest.config_fields[0].default is True


def test_middleware_does_not_re_register_the_tools() -> None:
    ctx: Any = CapabilityContext(
        identity=CapabilityIdentity(user_id="u", session_id="s"),
        config=MemoryConfig(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    stack = MemoryCapability().middleware(ctx)

    assert len(stack) == 1
    assert not any(isinstance(m, ToolCarrierMiddleware) for m in stack)
