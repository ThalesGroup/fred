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

"""Save-time tests for ``PptFillerCapability.validate_config``.

Port of Kea's ``tests/test_ppt_filler_processor.py`` re-seated on the capability
save seam: the three-state machine now runs on
``PptFillerCapability().validate_config(config, uploads, SaveContext(...))``, the
template blob is stored through the ``agent_assets`` port fake, and image folders
resolve through the ``document_folders`` port fake. The template BYTES are never
persisted in the returned config (RFC §3.8) — only the recomputed schema and the
fixed storage key.
"""

from __future__ import annotations

import pytest
from deck_builders import IMAGE_NOTES, build_deck
from fred_capability_ppt_filler.capability import (
    PPT_FILLER_TEMPLATE_KEY,
    TEMPLATE_SLOT,
    PptFillerCapability,
    PptFillerConfig,
)
from fred_capability_ppt_filler.parser import KeyField, SlideSchema
from fred_sdk.contracts.capability import (
    CapabilityIdentity,
    SaveContext,
    UploadedFile,
)
from fred_sdk.contracts.runtime import RuntimeServices
from port_fakes import FakeAssets, FakeFolders


def _save_ctx(*, assets=None, folders=None) -> SaveContext:
    return SaveContext(
        identity=CapabilityIdentity(user_id="u-1", session_id="s-1", team_id="team-42"),
        services=RuntimeServices(agent_assets=assets, document_folders=folders),
    )


def _uploads(content: bytes):
    return {TEMPLATE_SLOT: [UploadedFile(filename="template.pptx", content=content)]}


# --- State 1: upload present -------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_valid_stores_blob_recomputes_schema_and_keeps_no_bytes():
    deck = build_deck(
        [
            ("Hello {{name}} and {{role}}", "{{name}}:\nThe name\n{{role}}:\nThe role"),
            ("City: {{city}}", "{{city}}:\nThe city"),
        ]
    )
    assets = FakeAssets()
    # Seed a stale schema to prove the SERVER recomputes from the actual bytes.
    config = PptFillerConfig(
        schema_slides=[SlideSchema(slide=99, keys=[KeyField(key="stale")])]
    )

    result = await PptFillerCapability().validate_config(
        config, _uploads(deck), _save_ctx(assets=assets)
    )

    # Blob stored once, under the fixed per-instance key, with the deck bytes.
    assert len(assets.store_calls) == 1
    call = assets.store_calls[0]
    assert call["key"] == PPT_FILLER_TEMPLATE_KEY
    assert call["content"] == deck

    # Schema recomputed from the ACTUAL bytes (not the stale seed).
    assert [s.slide for s in result.schema_slides] == [1, 2]
    assert result.schema_slides[0].keys[0].key == "name"
    assert result.schema_slides[1].keys[0].key == "city"

    # The template key is carried; the BYTES never appear in the config anywhere.
    assert result.template_key == PPT_FILLER_TEMPLATE_KEY
    dumped = result.model_dump()
    assert set(dumped.keys()) == {"template_key", "schema_slides"}


@pytest.mark.asyncio
async def test_upload_with_template_errors_raises_valueerror_with_messages():
    # {{age}} appears on slide 1 but is not described -> key_without_description.
    deck = build_deck([("Hi {{name}} aged {{age}}", "{{name}}:\nThe name")])
    assets = FakeAssets()

    with pytest.raises(ValueError) as excinfo:
        await PptFillerCapability().validate_config(
            PptFillerConfig(), _uploads(deck), _save_ctx(assets=assets)
        )

    message = str(excinfo.value)
    assert "misconfigured" in message
    assert "age" in message  # the offending key surfaces in the human message
    # Invalid template -> nothing stored (no half-written blob).
    assert assets.store_calls == []


@pytest.mark.asyncio
async def test_unreadable_pptx_raises_valueerror_without_storing():
    assets = FakeAssets()

    with pytest.raises(ValueError) as excinfo:
        await PptFillerCapability().validate_config(
            PptFillerConfig(), _uploads(b"this is not a pptx"), _save_ctx(assets=assets)
        )

    assert "could not be read as a .pptx" in str(excinfo.value)
    assert assets.store_calls == []


# --- State 2: no upload, schema present -------------------------------------------


@pytest.mark.asyncio
async def test_no_upload_with_schema_passes_through_unchanged():
    config = PptFillerConfig(
        schema_slides=[
            SlideSchema(slide=1, keys=[KeyField(key="name", description="n")])
        ]
    )
    assets = FakeAssets()

    result = await PptFillerCapability().validate_config(
        config, {}, _save_ctx(assets=assets)
    )

    assert result is config
    assert assets.store_calls == []
    assert [s.slide for s in result.schema_slides] == [1]


# --- State 3: no upload, no schema ------------------------------------------------


@pytest.mark.asyncio
async def test_no_upload_no_schema_rejects_as_asset_required():
    assets = FakeAssets()

    with pytest.raises(ValueError) as excinfo:
        await PptFillerCapability().validate_config(
            PptFillerConfig(), {}, _save_ctx(assets=assets)
        )

    assert "requires a PowerPoint template" in str(excinfo.value)
    assert assets.store_calls == []


# --- Image folder resolution at save time -----------------------------------------


@pytest.mark.asyncio
async def test_image_template_known_folder_persists_tag_id():
    deck = build_deck([("{{logo}}", IMAGE_NOTES)])
    assets = FakeAssets()
    folders = FakeFolders(folder_to_tag={"Brand/Logos": "tag-123"})

    result = await PptFillerCapability().validate_config(
        PptFillerConfig(), _uploads(deck), _save_ctx(assets=assets, folders=folders)
    )

    assert folders.resolve_calls == ["Brand/Logos"]
    assert len(assets.store_calls) == 1
    logo = result.schema_slides[0].keys[0]
    assert logo.key == "logo"
    assert logo.type == "image"
    assert logo.folder == "Brand/Logos"
    assert logo.folder_tag_id == "tag-123"


@pytest.mark.asyncio
async def test_image_template_unknown_folder_rejects_and_stores_nothing():
    deck = build_deck([("{{logo}}", IMAGE_NOTES)])
    assets = FakeAssets()
    folders = FakeFolders(folder_to_tag={"Other/Dir": "tag-999"})  # different folder

    with pytest.raises(ValueError) as excinfo:
        await PptFillerCapability().validate_config(
            PptFillerConfig(), _uploads(deck), _save_ctx(assets=assets, folders=folders)
        )

    assert "does not exist" in str(excinfo.value)  # folder_not_found message
    assert assets.store_calls == []


@pytest.mark.asyncio
async def test_image_template_without_folders_port_fails_loud():
    """No ``document_folders`` port but the template declares image folders -> a save
    path that would silently skip folder validation must fail LOUD (RFC §3.9)."""
    deck = build_deck([("{{logo}}", IMAGE_NOTES)])
    assets = FakeAssets()

    with pytest.raises(RuntimeError) as excinfo:
        await PptFillerCapability().validate_config(
            PptFillerConfig(), _uploads(deck), _save_ctx(assets=assets, folders=None)
        )

    assert "document_folders" in str(excinfo.value)
    assert assets.store_calls == []


@pytest.mark.asyncio
async def test_text_only_template_without_folders_port_succeeds():
    """A text-only template needs no folder resolution, so a missing ``document_folders``
    port is fine — the blob is stored and the schema persisted."""
    deck = build_deck([("Hello {{name}}", "{{name}}:\nThe name")])
    assets = FakeAssets()

    result = await PptFillerCapability().validate_config(
        PptFillerConfig(), _uploads(deck), _save_ctx(assets=assets, folders=None)
    )

    assert len(assets.store_calls) == 1
    assert result.schema_slides[0].keys[0].key == "name"


@pytest.mark.asyncio
async def test_missing_agent_assets_port_fails_loud():
    """A valid template but no ``agent_assets`` port -> cannot store the blob, fail loud."""
    deck = build_deck([("Hello {{name}}", "{{name}}:\nThe name")])

    with pytest.raises(RuntimeError) as excinfo:
        await PptFillerCapability().validate_config(
            PptFillerConfig(), _uploads(deck), _save_ctx(assets=None)
        )

    assert "agent_assets" in str(excinfo.value)
