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

"""Registry boot invariants for the `platform_postgres` capability (spec §7.1).

fred-runtime is a dev-group (test-only) dependency here: the capability's own
runtime seam is the fred-sdk `PlatformSqlPort` contract, but the boot
invariant — entry-point discovery into a fresh `CapabilityRegistry` plus
`.validate()` — is a fred-runtime concern, mirrored from
`test_capability_document_access_1906.py`.
"""

from __future__ import annotations

from importlib.metadata import EntryPoint

from fred_capability_platform_ops.postgres.capability import (
    PlatformPostgresCapability,
)
from fred_runtime.capabilities import CapabilityRegistry
from fred_runtime.capabilities.registry import FRED_CAPABILITIES_ENTRY_POINT_GROUP

# Must match the [project.entry-points."fred.capabilities"] declaration in
# pyproject.toml — installing the package IS the registration.
_ENTRY_POINT_VALUE = (
    "fred_capability_platform_ops.postgres.capability:PlatformPostgresCapability"
)


def test_capability_registers_via_entry_point_and_boots() -> None:
    registry = CapabilityRegistry()
    entry = EntryPoint(
        name="platform_postgres",
        value=_ENTRY_POINT_VALUE,
        group=FRED_CAPABILITIES_ENTRY_POINT_GROUP,
    )
    registered = registry.discover(entry_points=[entry])

    assert registered == ["platform_postgres"]
    assert isinstance(
        registry.capability("platform_postgres"), PlatformPostgresCapability
    )
    # Boot validation must pass (admin-gated, no required env, no owned
    # tables, no chat-part collisions) — the boot invariant.
    registry.validate(env={})


def test_manifest_declares_the_minimal_tool_surface() -> None:
    manifest = PlatformPostgresCapability.manifest
    assert manifest.id == "platform_postgres"
    assert manifest.kind == "tool"
    # tools()-only capability: runs on both execution models (defaults kept).
    assert manifest.execution_models == ("react", "graph")
    # No chat parts, side panels, router, or owned tables (spec §1).
    assert manifest.chat_parts == []
    assert manifest.side_panels == []
    assert manifest.router is None
    assert manifest.tables == []
    # One config knob only.
    assert [f.key for f in manifest.config_fields] == ["statement_timeout_s"]
