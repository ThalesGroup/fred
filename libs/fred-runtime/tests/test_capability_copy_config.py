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
`POST /agents/capabilities/{id}/copy-config`: a copied agent keeps the public
settings, loses the scope-private ones when the scope changes, and gets its
configuration files re-submitted to the capability's save in the target.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated

import pytest
from _tracer_capability import TracerEchoCapability
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.capabilities.copy import (
    CapabilityCopyRejectedError,
    prepare_capability_copy,
)
from fred_sdk.contracts.capability import (
    AgentCapability,
    AssetKey,
    AssetSlot,
    CapabilityConfigCopyRequest,
    CapabilityIdentity,
    CapabilityManifest,
    EmptyModel,
    SaveContext,
    ScopePrivate,
    StoredCapabilityConfig,
    UploadedFile,
)
from fred_sdk.contracts.runtime import AgentAssetPort, RuntimeServices
from pydantic import BaseModel
from test_capability_endpoints_1974 import _app_with_capabilities


class _MemoryAssets(AgentAssetPort):
    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files = dict(files or {})

    async def store(self, key, content, *, content_type=None, filename=None) -> str:
        self.files[key] = content
        return key

    async def fetch(self, key: str) -> bytes:
        return self.files[key]

    async def delete(self, key: str) -> None:
        self.files.pop(key, None)


class _DeckConfig(BaseModel):
    title: str = "untitled"
    library_tag_ids: ScopePrivate[list[str]] = []
    template_key: Annotated[str, AssetKey("template")] = "deck.pptx"


# (team the save ran in, uploads it received)
VALIDATE_CALLS: list[tuple[str | None, dict[str, list[UploadedFile]]]] = []


class _DeckCapability(AgentCapability[_DeckConfig, _DeckConfig, EmptyModel]):
    manifest = CapabilityManifest(
        id="deck_copy",
        version="1.0.0",
        name="capability.deck_copy.name",
        description="capability.deck_copy.description",
        icon="slideshow",
        assets=[AssetSlot(key="template", accepted_types=[".pptx"], max_count=1)],
    )
    ConfigModel = _DeckConfig

    async def validate_config(
        self,
        config: _DeckConfig,
        uploads: Mapping[str, list[UploadedFile]],
        ctx: SaveContext,
    ) -> _DeckConfig:
        VALIDATE_CALLS.append((ctx.identity.team_id, dict(uploads)))
        if ctx.copied_from_another_scope:
            ctx.notices.append(f"copied to {ctx.identity.team_id}")
        if uploads.get("template"):
            if uploads["template"][0].content == b"broken":
                raise ValueError("unreadable template")
            assert ctx.services.agent_assets is not None
            await ctx.services.agent_assets.store(
                config.template_key, uploads["template"][0].content
            )
        return config


def _request(target_team: str) -> CapabilityConfigCopyRequest:
    return CapabilityConfigCopyRequest(
        config=StoredCapabilityConfig(
            schema_version="1.0.0",
            config={"title": "Weekly", "library_tag_ids": ["lib-a"]},
        ),
        source_team_id="team-a",
        source_agent_instance_id="agent-1",
        target_team_id=target_team,
        target_agent_instance_id="agent-2",
    )


def _ctx(team: str, assets: _MemoryAssets) -> SaveContext:
    return SaveContext(
        identity=CapabilityIdentity(user_id="u1", team_id=team),
        services=RuntimeServices(agent_assets=assets),
    )


@pytest.fixture(autouse=True)
def _reset_calls():
    VALIDATE_CALLS.clear()


@pytest.mark.asyncio
async def test_other_scope_resets_scope_private_and_recreates_files() -> None:
    source = _MemoryAssets({"deck.pptx": b"pptx-bytes"})
    target = _MemoryAssets()

    stored = await prepare_capability_copy(
        _DeckCapability(),
        _request("team-b"),
        source_ctx=_ctx("team-a", source),
        target_ctx=_ctx("team-b", target),
    )

    assert stored.config == {
        "title": "Weekly",
        "library_tag_ids": [],
        "template_key": "deck.pptx",
    }
    assert stored.notices == ["copied to team-b"]
    assert target.files == {"deck.pptx": b"pptx-bytes"}
    team, uploads = VALIDATE_CALLS[0]
    assert team == "team-b"
    upload = uploads["template"][0]
    assert upload.filename == "deck.pptx"


@pytest.mark.asyncio
async def test_same_scope_keeps_scope_private_settings() -> None:
    source = _MemoryAssets({"deck.pptx": b"pptx-bytes"})

    stored = await prepare_capability_copy(
        _DeckCapability(),
        _request("team-a"),
        source_ctx=_ctx("team-a", source),
        target_ctx=_ctx("team-a", _MemoryAssets()),
    )

    assert stored.config["library_tag_ids"] == ["lib-a"]
    assert stored.notices == []


@pytest.mark.asyncio
async def test_missing_configuration_file_rejects_the_capability() -> None:
    with pytest.raises(CapabilityCopyRejectedError, match="deck.pptx"):
        await prepare_capability_copy(
            _DeckCapability(),
            _request("team-b"),
            source_ctx=_ctx("team-a", _MemoryAssets()),
            target_ctx=_ctx("team-b", _MemoryAssets()),
        )


@pytest.mark.asyncio
async def test_capability_rejection_in_target_is_typed() -> None:
    with pytest.raises(CapabilityCopyRejectedError, match="unreadable template"):
        await prepare_capability_copy(
            _DeckCapability(),
            _request("team-b"),
            source_ctx=_ctx("team-a", _MemoryAssets({"deck.pptx": b"broken"})),
            target_ctx=_ctx("team-b", _MemoryAssets()),
        )


def _post(client, capability_id: str, request: CapabilityConfigCopyRequest):
    return client.post(
        f"/pod/v1/agents/capabilities/{capability_id}/copy-config",
        json=request.model_dump(mode="json"),
    )


def test_endpoint_returns_the_target_envelope(tmp_path, monkeypatch) -> None:
    files = {
        "team-a": _MemoryAssets({"deck.pptx": b"pptx-bytes"}),
        "team-b": _MemoryAssets(),
    }
    monkeypatch.setattr(
        agent_app_module,
        "_build_capability_save_services",
        lambda **kwargs: RuntimeServices(agent_assets=files[kwargs["team_id"]]),
    )
    client = _app_with_capabilities(tmp_path, monkeypatch, _DeckCapability())
    try:
        response = _post(client, "deck_copy", _request("team-b"))
        assert response.status_code == 200
        assert response.json() == {
            "schema_version": "1.0.0",
            "config": {
                "title": "Weekly",
                "library_tag_ids": [],
                "template_key": "deck.pptx",
            },
            "notices": ["copied to team-b"],
        }
        assert files["team-b"].files == {"deck.pptx": b"pptx-bytes"}
    finally:
        client.__exit__(None, None, None)


def test_endpoint_unknown_capability_is_404(tmp_path, monkeypatch) -> None:
    client = _app_with_capabilities(tmp_path, monkeypatch, TracerEchoCapability())
    try:
        assert _post(client, "ghost", _request("team-b")).status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_endpoint_rejection_is_422(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        agent_app_module,
        "_build_capability_save_services",
        lambda **kwargs: RuntimeServices(agent_assets=_MemoryAssets()),
    )
    client = _app_with_capabilities(tmp_path, monkeypatch, _DeckCapability())
    try:
        response = _post(client, "deck_copy", _request("team-b"))
        assert response.status_code == 422
        assert "deck.pptx" in response.json()["detail"]
    finally:
        client.__exit__(None, None, None)
