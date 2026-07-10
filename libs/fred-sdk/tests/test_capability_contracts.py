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
from pydantic import BaseModel, ValidationError

from fred_sdk.contracts.capability import (
    AgentCapability,
    AssetSlot,
    CapabilityContext,
    CapabilityIdentity,
    CapabilityManifest,
    ChatControlSpec,
    EmptyModel,
    HitlGateRequest,
    HitlSpec,
    SaveContext,
    SidePanelSpec,
    TeamScopePolicy,
    UploadedFile,
    chat_part_kind,
)
from fred_sdk.contracts.runtime import RuntimeServices

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


def test_manifest_rejects_blank_id() -> None:
    with pytest.raises(ValidationError):
        _manifest(id="")


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
