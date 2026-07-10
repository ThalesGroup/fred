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

"""
Capability registry boot validation and entry-point discovery (#1973, RFC §4).

Pins the four named boot failures (each must fail pod startup loudly), the
`fred.capabilities` entry-point discovery path (installing the package IS the
registration — zero code edits), and the checkpointer msgpack allowlist
composition (RFC §5.2 spike rule, #1971).
"""

from __future__ import annotations

from importlib.metadata import EntryPoint
from typing import Any, Literal

import pytest
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
    TeamScopePolicy,
)
from pydantic import BaseModel

from fred_runtime.capabilities import (
    CapabilityRegistrationError,
    CapabilityRegistry,
    DefaultOnRequiredSettingsError,
    DuplicateCapabilityIdError,
    DuplicateChatPartKindError,
    MissingRequiredEnvError,
    boot_capability_registry,
)
from fred_runtime.capabilities.demo import DemoEchoCapability

# ---------------------------------------------------------------------------
# Capability factory
# ---------------------------------------------------------------------------


class _Config(BaseModel):
    threshold: int = 1


def _capability(
    cap_id: str, **manifest_overrides: Any
) -> AgentCapability[Any, Any, Any]:
    team_settings_model = manifest_overrides.pop("team_settings_model", None)

    manifest_kwargs: dict[str, Any] = dict(
        id=cap_id,
        version="1.0.0",
        name=f"cap.{cap_id}.name",
        description=f"cap.{cap_id}.description",
        icon="TestIcon",
    )
    manifest_kwargs.update(manifest_overrides)

    class _Cap(AgentCapability[_Config, _Config, EmptyModel]):
        manifest = CapabilityManifest(**manifest_kwargs)
        ConfigModel = _Config

        def middleware(self, ctx: CapabilityContext[_Config, EmptyModel]) -> list[Any]:
            return []

    if team_settings_model is not None:
        _Cap.TeamSettingsModel = team_settings_model
    return _Cap()


class _DemoCardPart(BaseModel):
    type: Literal["demo_card"] = "demo_card"
    payload: str = ""


class _OtherDemoCardPart(BaseModel):
    type: Literal["demo_card"] = "demo_card"
    body: str = ""


class _LinkCollidingPart(BaseModel):
    type: Literal["link"] = "link"


class _RequiredTeamSettings(BaseModel):
    api_budget: int  # required — no default


class _OptionalTeamSettings(BaseModel):
    api_budget: int = 10


class _TypedStateDoc(BaseModel):
    body: str = ""


# ---------------------------------------------------------------------------
# The four named boot failures (RFC §4 — fail pod startup loudly)
# ---------------------------------------------------------------------------


def test_duplicate_capability_id_fails_boot() -> None:
    registry = CapabilityRegistry()
    registry.register(_capability("cap_a"))
    with pytest.raises(DuplicateCapabilityIdError, match="cap_a"):
        registry.register(_capability("cap_a"))


def test_duplicate_chat_part_kind_across_capabilities_fails_boot() -> None:
    registry = CapabilityRegistry()
    registry.register(_capability("cap_a", chat_parts=[_DemoCardPart]))
    registry.register(_capability("cap_b", chat_parts=[_OtherDemoCardPart]))
    with pytest.raises(DuplicateChatPartKindError, match="demo_card"):
        registry.validate(env={})


def test_chat_part_kind_colliding_with_builtin_uipart_fails_boot() -> None:
    registry = CapabilityRegistry()
    registry.register(_capability("cap_a", chat_parts=[_LinkCollidingPart]))
    with pytest.raises(DuplicateChatPartKindError, match="link"):
        registry.validate(env={})


def test_missing_required_env_fails_boot() -> None:
    registry = CapabilityRegistry()
    registry.register(_capability("cap_env", required_env=["DEMO_API_KEY"]))
    with pytest.raises(MissingRequiredEnvError, match="cap_env.*DEMO_API_KEY"):
        registry.validate(env={})


def test_present_required_env_passes_boot() -> None:
    registry = CapabilityRegistry()
    registry.register(_capability("cap_env", required_env=["DEMO_API_KEY"]))
    registry.validate(env={"DEMO_API_KEY": "secret"})


def test_default_on_with_required_team_settings_fails_boot() -> None:
    registry = CapabilityRegistry()
    registry.register(
        _capability(
            "cap_scope",
            team_scope=TeamScopePolicy.DEFAULT_ON,
            team_settings_model=_RequiredTeamSettings,
        )
    )
    with pytest.raises(DefaultOnRequiredSettingsError, match="cap_scope"):
        registry.validate(env={})


def test_default_on_with_all_default_team_settings_passes_boot() -> None:
    registry = CapabilityRegistry()
    registry.register(
        _capability(
            "cap_scope",
            team_scope=TeamScopePolicy.DEFAULT_ON,
            team_settings_model=_OptionalTeamSettings,
        )
    )
    registry.validate(env={})


# ---------------------------------------------------------------------------
# Entry-point discovery — installing the package IS the registration
# ---------------------------------------------------------------------------


def test_entry_point_discovery_registers_capability_with_zero_code_edits() -> None:
    entry = EntryPoint(
        name="demo_echo",
        value="fred_runtime.capabilities.demo:DemoEchoCapability",
        group="fred.capabilities",
    )
    registry = CapabilityRegistry()
    registered = registry.discover(entry_points=[entry])

    assert registered == ["demo_echo"]
    assert "demo_echo" in registry
    assert isinstance(registry.capability("demo_echo"), DemoEchoCapability)
    registry.validate(env={})


def test_entry_point_rejects_non_capability_target() -> None:
    entry = EntryPoint(
        name="bogus",
        value="fred_runtime.capabilities.demo:DemoEchoConfig",
        group="fred.capabilities",
    )
    registry = CapabilityRegistry()
    with pytest.raises(CapabilityRegistrationError, match="bogus"):
        registry.discover(entry_points=[entry])


def test_boot_registry_with_no_installed_packages_is_empty_and_valid() -> None:
    registry = boot_capability_registry(env={})
    assert len(registry) == 0


# ---------------------------------------------------------------------------
# Checkpointer msgpack allowlist composition (RFC §5.2 spike rule)
# ---------------------------------------------------------------------------


def test_registry_composes_msgpack_allowlist_from_state_models() -> None:
    registry = CapabilityRegistry()
    registry.register(_capability("cap_typed", state_models=[_TypedStateDoc]))
    registry.register(_capability("cap_plain"))

    assert registry.msgpack_allowlist() == (
        (_TypedStateDoc.__module__, "_TypedStateDoc"),
    )


@pytest.mark.asyncio
async def test_checkpointer_extends_allowlist_and_keeps_legacy_entry() -> None:
    from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        checkpointer = FredSqlCheckpointer(
            engine,
            extra_msgpack_allowlist=((_TypedStateDoc.__module__, "_TypedStateDoc"),),
        )
        doc = _TypedStateDoc(body="typed")
        restored = checkpointer.serde.loads_typed(checkpointer.serde.dumps_typed(doc))
        assert isinstance(restored, _TypedStateDoc)
        assert restored.body == "typed"

        # The legacy entry stays composed in (handoff rule, #1972).
        legacy = FredSqlCheckpointer._FRED_MSGPACK_ALLOWLIST
        assert (
            "agentic_backend.core.agents.v2.contracts.context",
            "ToolContentKind",
        ) in legacy
    finally:
        await engine.dispose()
