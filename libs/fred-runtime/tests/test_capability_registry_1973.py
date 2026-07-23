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
from fred_runtime.capabilities import (
    CapabilityRegistrationError,
    CapabilityRegistry,
    DefaultOnRequiredSettingsError,
    DuplicateCapabilityIdError,
    DuplicateChatPartKindError,
    MissingRequiredEnvError,
    UndeclaredExecutionModelError,
    boot_capability_registry,
)
from fred_runtime.capabilities.demo import DemoEchoCapability
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
    TeamScopePolicy,
)
from pydantic import BaseModel

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
        # This factory always builds a middleware()-only capability (below);
        # declare it explicitly so tests exercising an unrelated boot
        # invariant don't also trip the new `execution_models` one (CAPAB-02)
        # — tests for that invariant itself override this back out.
        execution_models=("react",),
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
    registry.validate(env={"DEMO_API_KEY": "secret"})  # pragma: allowlist secret


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
# execution_models — a middleware()-only capability must declare it
# explicitly, or it silently claims Graph compatibility it doesn't have
# (CAPAB-02, RFC §3.2, §3.9)
# ---------------------------------------------------------------------------


def test_middleware_only_capability_forgetting_execution_models_fails_boot() -> None:
    """
    The trap the third independent review found: a `middleware()`-only
    capability that never mentions `execution_models` at all keeps the class
    default (`("react", "graph")`), which claims Graph compatibility it does
    not have. A capability author forgetting this must fail LOUD at boot,
    not silently ship a Graph no-op. Deliberately NOT using the `_capability`
    factory above — it injects `execution_models=("react",)` by default
    precisely so OTHER tests don't trip this invariant; this test's whole
    point is the case where the field is never mentioned at all.
    """

    class _ForgotCap(AgentCapability[_Config, _Config, EmptyModel]):
        manifest = CapabilityManifest(
            id="cap_forgot",
            version="1.0.0",
            name="cap.cap_forgot.name",
            description="cap.cap_forgot.description",
            icon="TestIcon",
        )
        ConfigModel = _Config

        def middleware(self, ctx: CapabilityContext[_Config, EmptyModel]) -> list[Any]:
            return []

    registry = CapabilityRegistry()
    registry.register(_ForgotCap())
    with pytest.raises(UndeclaredExecutionModelError, match="cap_forgot"):
        registry.validate(env={})


def test_middleware_only_capability_declaring_execution_models_passes_boot() -> None:
    registry = CapabilityRegistry()
    registry.register(_capability("cap_declared", execution_models=("react",)))
    registry.validate(env={})


def test_tools_based_capability_needs_no_execution_models_declaration() -> None:
    """A `tools()`-based capability is execution-model-agnostic by
    construction — it never needs to declare `execution_models` at all."""

    class _ToolsCap(AgentCapability[_Config, _Config, EmptyModel]):
        manifest = CapabilityManifest(
            id="cap_tools_only",
            version="1.0.0",
            name="cap.cap_tools_only.name",
            description="cap.cap_tools_only.description",
            icon="TestIcon",
        )
        ConfigModel = _Config

        def tools(self, ctx: CapabilityContext[_Config, EmptyModel]) -> list[Any]:
            del ctx
            return []

    registry = CapabilityRegistry()
    registry.register(_ToolsCap())
    registry.validate(env={})


def test_mcp_capability_is_exempt_from_execution_models_declaration() -> None:
    """
    `McpCapability` overrides `middleware()` (the instruction-fragment
    prompt) without implementing `tools()`, exactly the shape
    `_validate_execution_models` otherwise flags — but its tools reach every
    execution model through `FredMcpToolProvider`, a path entirely outside
    `tools()`/`middleware()`. It must stay exempt.
    """
    from fred_runtime.capabilities.mcp import build_mcp_capability
    from fred_sdk.contracts.models import MCPServerConfiguration

    server = MCPServerConfiguration.model_validate({"id": "mcp-search", "name": "S"})
    registry = CapabilityRegistry()
    registry.register(build_mcp_capability(server))
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


def test_boot_registry_discovers_installed_demo_capability() -> None:
    # fred-runtime itself declares the demo capability's `fred.capabilities`
    # entry point (#1977): installing the package IS the registration, so a
    # bare boot discovers exactly the in-tree tracer.
    registry = boot_capability_registry(env={})
    assert "demo_echo" in registry


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
