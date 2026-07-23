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
Tier 0 capability contract tests (#1973, RFC AGENT-CAPABILITY-RFC.md §3).

Covers the SDK half of the capability system: the `AgentCapability` shape with
its four typed models, the manifest, the typed runtime/LLM context split, asset
slot cardinality, HITL declarations, and the chat-part `kind` discriminator
helper the runtime registry validates against.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

import pytest
from fred_sdk.contracts.capability import (
    AgentCapability,
    AssetSlot,
    CapabilityCatalogEntry,
    CapabilityContext,
    CapabilityIdentity,
    CapabilityManifest,
    ChatControlSpec,
    EmptyModel,
    HitlGateRequest,
    HitlSpec,
    SaveContext,
    SidePanelSpec,
    StoredCapabilityConfig,
    TeamScopePolicy,
    ToolCarrierMiddleware,
    UploadedFile,
    chat_part_kind,
)
from fred_sdk.contracts.capability.manifest import (
    TeamScopePolicy as ManifestTeamScopePolicy,
)
from fred_sdk.contracts.models import AgentTuning, FieldSpec, MCPServerConfiguration
from fred_sdk.contracts.runtime import RuntimeServices
from pydantic import BaseModel, ValidationError

# ---------------------------------------------------------------------------
# Fixture capability
# ---------------------------------------------------------------------------


class _Config(BaseModel):
    threshold: int = 3


class _StoredConfig(_Config):
    derived_key: str = "k"


class _TurnOptions(BaseModel):
    verbose: bool = False


def _manifest(**overrides: Any) -> CapabilityManifest:
    kwargs: dict[str, Any] = dict(
        id="test_cap",
        version="1.0.0",
        name="cap.test.name",
        description="cap.test.description",
        icon="TestIcon",
    )
    kwargs.update(overrides)
    return CapabilityManifest(**kwargs)


class _FullCapability(AgentCapability[_Config, _StoredConfig, _TurnOptions]):
    manifest = _manifest()
    ConfigModel = _Config
    StoredConfigModel = _StoredConfig
    TurnOptionsModel = _TurnOptions

    def middleware(
        self, ctx: CapabilityContext[_StoredConfig, _TurnOptions]
    ) -> list[Any]:
        return []


class _MinimalCapability(AgentCapability[_Config, _Config, EmptyModel]):
    """Only ConfigModel declared — the other three models default."""

    manifest = _manifest(id="minimal_cap")
    ConfigModel = _Config

    def middleware(self, ctx: CapabilityContext[_Config, EmptyModel]) -> list[Any]:
        return []


class _ToolsOnlyCapability(AgentCapability[_Config, _Config, EmptyModel]):
    """Implements only `tools()` — relies on the default `middleware()` wrap
    (CAPAB-02: the primary authoring surface, execution-model-agnostic)."""

    manifest = _manifest(id="tools_only_cap")
    ConfigModel = _Config

    def tools(self, ctx: CapabilityContext[_Config, EmptyModel]) -> list[Any]:
        from langchain_core.tools import tool

        @tool
        def echo(text: str) -> str:
            """Echo text back."""
            return text

        return [echo]


def _identity() -> CapabilityIdentity:
    return CapabilityIdentity(user_id="user-1", session_id="session-1")


# ---------------------------------------------------------------------------
# The four typed models and their defaults
# ---------------------------------------------------------------------------


def test_minimal_capability_defaults_the_other_three_models() -> None:
    assert _MinimalCapability.ConfigModel is _Config
    assert _MinimalCapability.StoredConfigModel is _Config
    assert _MinimalCapability.TurnOptionsModel is EmptyModel
    assert _MinimalCapability.TeamSettingsModel is EmptyModel


def test_full_capability_keeps_declared_models() -> None:
    assert _FullCapability.StoredConfigModel is _StoredConfig
    assert _FullCapability.TurnOptionsModel is _TurnOptions
    assert _FullCapability.TeamSettingsModel is EmptyModel


def test_default_validate_config_maps_config_into_stored_model() -> None:
    cap = _FullCapability()
    stored = asyncio.run(
        cap.validate_config(
            _Config(threshold=7),
            uploads={},
            ctx=SaveContext(identity=_identity(), services=RuntimeServices()),
        )
    )
    assert isinstance(stored, _StoredConfig)
    assert stored.threshold == 7
    assert stored.derived_key == "k"


def test_default_upgrade_config_validates_against_stored_model() -> None:
    cap = _FullCapability()
    upgraded = cap.upgrade_config({"threshold": 9}, from_version="0.9.0")
    assert isinstance(upgraded, _StoredConfig)
    assert upgraded.threshold == 9


def test_default_chat_controls_and_hitl_specs_are_empty() -> None:
    cap = _FullCapability()
    assert cap.chat_controls(_StoredConfig()) == []
    assert list(cap.hitl_specs()) == []


def test_default_tools_is_empty() -> None:
    # `tools()` is the primary authoring surface (CAPAB-02); a capability that
    # doesn't implement it (e.g. a middleware()-only, ReAct-specific one) gets
    # the empty default, never an AttributeError.
    cap = _FullCapability()
    ctx = CapabilityContext(
        identity=_identity(),
        config=_StoredConfig(),
        turn_options=_TurnOptions(),
        services=RuntimeServices(),
    )
    assert list(cap.tools(ctx)) == []


def test_default_middleware_wraps_tools_in_tool_carrier_middleware() -> None:
    cap = _ToolsOnlyCapability()
    ctx = CapabilityContext(
        identity=_identity(),
        config=_Config(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    (middleware,) = cap.middleware(ctx)
    assert isinstance(middleware, ToolCarrierMiddleware)
    assert [t.name for t in middleware.tools] == ["echo"]


def test_default_middleware_is_empty_when_tools_is_empty() -> None:
    # A capability implementing neither tools() nor middleware() (both base
    # class defaults) contributes nothing — not a crash.
    class _BareCapability(AgentCapability[_Config, _Config, EmptyModel]):
        manifest = _manifest(id="bare_cap")
        ConfigModel = _Config

    cap = _BareCapability()
    ctx = CapabilityContext(
        identity=_identity(),
        config=_Config(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    assert list(cap.middleware(ctx)) == []


def test_empty_model_forbids_fields() -> None:
    with pytest.raises(ValidationError):
        EmptyModel.model_validate({"unexpected": 1})


# ---------------------------------------------------------------------------
# CapabilityContext — typed runtime/LLM split
# ---------------------------------------------------------------------------


def test_capability_context_carries_typed_slices() -> None:
    ctx = CapabilityContext(
        identity=_identity(),
        config=_StoredConfig(threshold=2),
        turn_options=_TurnOptions(verbose=True),
        services=RuntimeServices(),
    )
    assert ctx.config.threshold == 2
    assert ctx.turn_options.verbose is True
    assert isinstance(ctx.team_settings, EmptyModel)


# ---------------------------------------------------------------------------
# AssetSlot cardinality
# ---------------------------------------------------------------------------


def test_asset_slot_defaults_are_optional_single_file() -> None:
    slot = AssetSlot(key="template", accepted_types=[".pptx"])
    assert slot.min_count == 0
    assert slot.max_count == 1


def test_asset_slot_required_single_file() -> None:
    slot = AssetSlot(key="template", accepted_types=[".pptx"], min_count=1)
    assert slot.min_count == 1


def test_asset_slot_rejects_max_below_min() -> None:
    with pytest.raises(ValidationError):
        AssetSlot(key="docs", accepted_types=[".pdf"], min_count=3, max_count=2)


def test_asset_slot_rejects_negative_min() -> None:
    with pytest.raises(ValidationError):
        AssetSlot(key="docs", accepted_types=[".pdf"], min_count=-1)


def test_asset_slot_unbounded_max() -> None:
    slot = AssetSlot(key="docs", accepted_types=[".pdf"], min_count=1, max_count=None)
    assert slot.max_count is None


# ---------------------------------------------------------------------------
# HitlSpec
# ---------------------------------------------------------------------------


def test_hitl_spec_defaults() -> None:
    spec = HitlSpec(tool="send_demo_message")
    assert spec.require is False
    assert spec.when is None
    assert spec.question is None
    assert spec.allowed_decisions == ("proceed", "cancel")


def test_hitl_spec_rejects_empty_allowed_decisions() -> None:
    with pytest.raises(ValidationError):
        HitlSpec(tool="send_demo_message", allowed_decisions=())


def test_hitl_gate_request_exposes_typed_context() -> None:
    ctx = CapabilityContext(
        identity=_identity(),
        config=_StoredConfig(threshold=5),
        turn_options=_TurnOptions(),
        services=RuntimeServices(),
    )
    request = HitlGateRequest(
        tool_call={"name": "send_demo_message", "args": {"to": "a@x"}},
        tool=None,
        context=ctx,
    )
    assert request.context.config.threshold == 5


# ---------------------------------------------------------------------------
# Manifest and chat-part kinds
# ---------------------------------------------------------------------------


class _LiteralPart(BaseModel):
    type: Literal["demo_card"] = "demo_card"
    payload: str


class _NoDiscriminatorPart(BaseModel):
    payload: str


def test_chat_part_kind_reads_the_literal_discriminator() -> None:
    assert chat_part_kind(_LiteralPart) == "demo_card"


def test_chat_part_kind_rejects_models_without_type_field() -> None:
    with pytest.raises(ValueError, match="type"):
        chat_part_kind(_NoDiscriminatorPart)


def test_manifest_defaults() -> None:
    manifest = _manifest()
    assert manifest.config_fields == []
    assert manifest.assets == []
    assert manifest.chat_parts == []
    assert manifest.side_panels == []
    assert manifest.required_env == []
    assert manifest.state_models == []
    assert manifest.router is None
    assert manifest.team_scope is TeamScopePolicy.ADMIN_GATED
    assert manifest.execution_models == ("react", "graph")


def test_manifest_execution_models_can_be_declared_react_only() -> None:
    # CAPAB-02: a middleware()-only capability (a ReAct-specific hook tools()
    # cannot express) must declare this explicitly — the default claims both.
    manifest = _manifest(execution_models=("react",))
    assert manifest.execution_models == ("react",)


def test_manifest_rejects_empty_execution_models() -> None:
    with pytest.raises(ValidationError):
        _manifest(execution_models=())


def test_manifest_rejects_execution_models_without_react() -> None:
    # No capability runtime need is Graph-only: tools() is the only
    # Graph-visible surface and it feeds the ReAct binding identically —
    # there is no equivalent "ReAct-only" mechanism in reverse.
    with pytest.raises(ValidationError, match="react"):
        _manifest(execution_models=("graph",))


def test_catalog_entry_carries_execution_models() -> None:
    manifest = _manifest(execution_models=("react",))
    entry = CapabilityCatalogEntry.from_manifest(manifest)
    assert entry.execution_models == ("react",)
    assert CapabilityCatalogEntry.model_validate_json(entry.model_dump_json()) == entry


def test_manifest_rejects_blank_id() -> None:
    with pytest.raises(ValidationError):
        _manifest(id="")


def test_manifest_rejects_id_containing_colon() -> None:
    # Capability ids land in OpenFGA object ids (`capability:<id>`) and URL
    # path segments; OpenFGA forbids `:` in object ids, so a colon must be
    # rejected at declaration rather than crashing tuple writes later (#1988).
    with pytest.raises(ValidationError):
        _manifest(id="mcp:x")


def test_manifest_accepts_ids_with_dots_dashes_and_underscores() -> None:
    for candidate in ("mcp-bank-core-demo", "doc.access_v2"):
        manifest = _manifest(id=candidate)
        assert manifest.id == candidate


def test_chat_control_and_side_panel_specs() -> None:
    class _Params(BaseModel):
        library_ids: list[str] = []

    control = ChatControlSpec(widget="document_picker", params=_Params())
    panel = SidePanelSpec(widget="ppt_preview")
    assert control.widget == "document_picker"
    assert panel.params is None


def test_uploaded_file_shape() -> None:
    upload = UploadedFile(filename="deck.pptx", content=b"\x00\x01")
    assert upload.filename.endswith(".pptx")


# ---------------------------------------------------------------------------
# Capability selection wire models (#1974, RFC §3.8)
# ---------------------------------------------------------------------------


def test_catalog_entry_projects_the_serializable_manifest_subset() -> None:
    manifest = _manifest(
        config_fields=[FieldSpec(key="uppercase", type="boolean", title="Uppercase")],
        assets=[AssetSlot(key="template", accepted_types=[".pptx"], min_count=1)],
        team_scope=TeamScopePolicy.DEFAULT_ON,
    )
    entry = CapabilityCatalogEntry.from_manifest(manifest)
    assert entry.id == "test_cap"
    assert entry.version == "1.0.0"
    assert entry.config_fields[0].key == "uppercase"
    assert entry.assets[0].key == "template"
    assert entry.team_scope is TeamScopePolicy.DEFAULT_ON
    # JSON-safe: the projection must serialize without arbitrary types.
    assert CapabilityCatalogEntry.model_validate_json(entry.model_dump_json()) == entry


def test_catalog_entry_carries_team_settings_fields() -> None:
    # Team-settings form (CAPAB-01 / #1980, RFC §8.2) round-trips through the
    # catalog projection so control-plane can render/validate it.
    manifest = _manifest(
        team_settings_fields=[
            FieldSpec(
                key="root_folder", type="string", title="Root folder", required=True
            )
        ],
    )
    entry = CapabilityCatalogEntry.from_manifest(manifest)
    assert entry.team_settings_fields[0].key == "root_folder"
    assert entry.team_settings_fields[0].required is True
    assert CapabilityCatalogEntry.model_validate_json(entry.model_dump_json()) == entry


def test_stored_capability_config_envelope_shape() -> None:
    envelope = StoredCapabilityConfig(
        schema_version="1.0.0", config={"uppercase": True}
    )
    assert envelope.config["uppercase"] is True
    with pytest.raises(ValidationError):
        StoredCapabilityConfig(schema_version="", config={})


def test_agent_tuning_carries_capability_selection_including_mcp_servers() -> None:
    # #1978 retired the MCP tuning trio (mcp_servers/selected_mcp_server_ids/
    # mcp_config_values): MCP servers are now selected and configured as
    # ordinary capabilities alongside any other capability, keyed by the
    # catalog server id directly (#1988 dropped the `mcp:` id prefix).
    tuning = AgentTuning(
        role="r",
        description="d",
        selected_capability_ids=["demo_echo", "tavily"],
        capability_config={
            "demo_echo": StoredCapabilityConfig(
                schema_version="0.1.0", config={"uppercase": True}
            ),
            "tavily": StoredCapabilityConfig(schema_version="1", config={}),
        },
    )
    assert tuning.selected_capability_ids == ["demo_echo", "tavily"]
    assert tuning.capability_config["demo_echo"].schema_version == "0.1.0"
    assert tuning.capability_config["tavily"].schema_version == "1"
    assert not hasattr(tuning, "mcp_servers")
    assert not hasattr(tuning, "selected_mcp_server_ids")
    assert not hasattr(tuning, "mcp_config_values")
    # Default: no selection — None means template default.
    empty = AgentTuning(role="r", description="d")
    assert empty.selected_capability_ids is None
    assert empty.capability_config == {}


# ---------------------------------------------------------------------------
# TeamScopePolicy / MCPServerConfiguration.team_scope (#1988)
# ---------------------------------------------------------------------------


def test_team_scope_policy_importable_from_both_paths() -> None:
    # TeamScopePolicy moved to fred_sdk.contracts.models but must remain
    # importable from its original home (capability.manifest) and from the
    # capability package's public surface — both re-export the same enum.
    assert ManifestTeamScopePolicy is TeamScopePolicy


def test_mcp_server_configuration_team_scope_defaults_to_admin_gated() -> None:
    server = MCPServerConfiguration.model_validate(
        {"id": "tavily", "name": "mcp.tavily.name"}
    )
    assert server.team_scope is TeamScopePolicy.ADMIN_GATED


def test_mcp_server_configuration_team_scope_parses_from_raw_value() -> None:
    # yaml-style raw input: a plain string, not the enum member.
    raw = {
        "id": "tavily",
        "name": "mcp.tavily.name",
        "team_scope": "default_on",
    }
    server = MCPServerConfiguration.model_validate(raw)
    assert server.team_scope is TeamScopePolicy.DEFAULT_ON
