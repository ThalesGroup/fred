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
Multipart capability-asset relay (#1903, RFC AGENT-CAPABILITY §3.4).

Covers the two seams that carry an uploaded asset binary from the browser to
the pod's `validate-config` endpoint:

- `service._validate_capability_config_via_pod`: the save's `asset_files` for a
  capability are forwarded as multipart `files` entries keyed by slot key,
  alongside the `config` form field — control-plane never opens the bytes
- `api._parse_capability_asset_uploads`: pairs the parallel `asset_slots` /
  `asset_files` multipart arrays by index, groups by capability id from the
  `{capability_id}:{slot_key}` ref, and rejects length mismatch / malformed
  refs with a typed 422
"""

from __future__ import annotations

from typing import Any, cast

import control_plane_backend.product.api as api
import control_plane_backend.product.service as service
import httpx
import pytest
from control_plane_backend.product.service import CapabilityAssetFile
from fastapi import HTTPException, UploadFile
from fred_core.common import TeamId


class _FakeUploadFile:
    """Duck-typed stand-in for Starlette's `UploadFile`.

    `_parse_capability_asset_uploads` only touches `.filename`, `.content_type`
    and `await .read()`, so a lightweight fake keeps the test off the full
    multipart-request machinery (the parsing helper is module-level async).
    """

    def __init__(
        self, content: bytes, *, filename: str | None, content_type: str | None
    ) -> None:
        self._content = content
        self.filename = filename
        self.content_type = content_type

    async def read(self) -> bytes:
        return self._content


# ---------------------------------------------------------------------------
# service._validate_capability_config_via_pod — multipart forwarding
# ---------------------------------------------------------------------------


def _capture_pod_post(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch httpx so the outbound validate-config request is captured, not sent."""

    captured: dict[str, Any] = {}

    async def _fake_post(self, url, *args, **kwargs):  # noqa: ANN001
        captured["url"] = str(url)
        captured["data"] = kwargs.get("data")
        captured["files"] = kwargs.get("files")
        captured["headers"] = kwargs.get("headers")
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={"schema_version": "0.1.0", "config": {"ok": True}},
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    return captured


@pytest.mark.asyncio
async def test_validate_forwards_asset_files_as_multipart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_pod_post(monkeypatch)

    envelope = await service._validate_capability_config_via_pod(
        base_url="http://runtime-a/pod/v1",
        capability_id="ppt_filler",
        config_values={"foo": "bar"},
        team_id=cast(TeamId, "personal"),
        agent_instance_id="instance-1",
        authorization="Bearer user-token",
        asset_files=[
            CapabilityAssetFile(
                slot_key="template",
                filename="deck.pptx",
                content=b"PK\x03\x04payload",
                content_type=(
                    "application/vnd.openxmlformats-officedocument."
                    "presentationml.presentation"
                ),
            )
        ],
    )

    # The pod's stored-config envelope is returned verbatim.
    assert envelope == {"schema_version": "0.1.0", "config": {"ok": True}}
    # `config` and `team_id` travel as form fields; config is JSON-encoded.
    assert captured["data"]["config"] == '{"foo": "bar"}'
    assert captured["data"]["team_id"] == "personal"
    assert captured["data"]["agent_instance_id"] == "instance-1"
    # The asset binary is a multipart `files` entry KEYED BY SLOT KEY.
    files = captured["files"]
    assert len(files) == 1
    slot_key, (filename, content, content_type) = files[0]
    assert slot_key == "template"
    assert filename == "deck.pptx"
    assert content == b"PK\x03\x04payload"
    assert "presentationml" in content_type
    assert captured["headers"] == {"Authorization": "Bearer user-token"}
    assert captured["url"].endswith("/agents/capabilities/ppt_filler/validate-config")


@pytest.mark.asyncio
async def test_validate_without_assets_sends_no_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_pod_post(monkeypatch)

    await service._validate_capability_config_via_pod(
        base_url="http://runtime-a/pod/v1",
        capability_id="demo_echo",
        config_values={},
        team_id=cast(TeamId, "personal"),
        agent_instance_id=None,
        authorization=None,
    )

    # No uploads: `files` is passed as None (httpx then sends a plain form),
    # and an absent instance id is not added as a form field.
    assert captured["files"] is None
    assert "agent_instance_id" not in captured["data"]
    assert captured["headers"] is None


@pytest.mark.asyncio
async def test_validate_content_type_defaults_to_octet_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_pod_post(monkeypatch)

    await service._validate_capability_config_via_pod(
        base_url="http://runtime-a/pod/v1",
        capability_id="ppt_filler",
        config_values={},
        team_id=cast(TeamId, "personal"),
        agent_instance_id=None,
        authorization=None,
        asset_files=[
            CapabilityAssetFile(
                slot_key="template",
                filename="deck.pptx",
                content=b"x",
                content_type=None,
            )
        ],
    )

    _slot_key, (_filename, _content, content_type) = captured["files"][0]
    assert content_type == "application/octet-stream"


# ---------------------------------------------------------------------------
# api._parse_capability_asset_uploads — pairing & validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_groups_uploads_by_capability_id() -> None:
    uploads = await api._parse_capability_asset_uploads(
        asset_slots=[
            "ppt_filler:template",
            "ppt_filler:logo",
            "other_cap:asset",
        ],
        asset_files=cast(
            "list[UploadFile]",
            [
                _FakeUploadFile(
                    b"deck", filename="deck.pptx", content_type="application/x"
                ),
                _FakeUploadFile(b"logo", filename="logo.png", content_type="image/png"),
                _FakeUploadFile(b"a", filename="a.bin", content_type=None),
            ],
        ),
    )

    assert set(uploads) == {"ppt_filler", "other_cap"}
    ppt = uploads["ppt_filler"]
    assert [(f.slot_key, f.filename, f.content) for f in ppt] == [
        ("template", "deck.pptx", b"deck"),
        ("logo", "logo.png", b"logo"),
    ]
    assert ppt[1].content_type == "image/png"
    other = uploads["other_cap"]
    assert [(f.slot_key, f.content) for f in other] == [("asset", b"a")]


@pytest.mark.asyncio
async def test_parse_missing_filename_falls_back_to_slot_key() -> None:
    uploads = await api._parse_capability_asset_uploads(
        asset_slots=["ppt_filler:template"],
        asset_files=cast(
            "list[UploadFile]",
            [_FakeUploadFile(b"x", filename=None, content_type=None)],
        ),
    )

    # An upload without a client filename is named after its slot key so the
    # pod still receives a stable multipart filename.
    assert uploads["ppt_filler"][0].filename == "template"


@pytest.mark.asyncio
async def test_parse_length_mismatch_is_422() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await api._parse_capability_asset_uploads(
            asset_slots=["ppt_filler:template", "ppt_filler:logo"],
            asset_files=cast(
                "list[UploadFile]",
                [_FakeUploadFile(b"x", filename="x", content_type=None)],
            ),
        )

    assert exc_info.value.status_code == 422
    assert "same length" in exc_info.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_ref",
    [
        "ppt_filler",  # no separator
        ":template",  # empty capability id
        "ppt_filler:",  # empty slot key
        "",  # empty ref
    ],
)
async def test_parse_malformed_ref_is_422(bad_ref: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await api._parse_capability_asset_uploads(
            asset_slots=[bad_ref],
            asset_files=cast(
                "list[UploadFile]",
                [_FakeUploadFile(b"x", filename="x", content_type=None)],
            ),
        )

    assert exc_info.value.status_code == 422
    assert "Invalid asset slot reference" in exc_info.value.detail


@pytest.mark.asyncio
async def test_parse_empty_arrays_returns_empty_mapping() -> None:
    uploads = await api._parse_capability_asset_uploads(asset_slots=[], asset_files=[])

    # The common no-upload save: equal (zero) lengths, nothing to relay.
    assert uploads == {}
