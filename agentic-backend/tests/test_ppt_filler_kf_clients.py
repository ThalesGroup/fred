# Copyright Thales 2025
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

"""Offline unit tests for the PPT-filler KF client additions:

- KfTagClient.resolve_folder / list_document_tags (folder -> DOCUMENT tag id)
- KfDocumentClient.fetch_raw_content (original raw bytes by uid)

The HTTP layer is faked the same way as test_kf_vector_search_tools.py:
KfBaseClient.__init__ is bypassed (no live ApplicationContext) and
_request_with_token_refresh is monkeypatched to return fake httpx responses.
"""

import httpx
import pytest
from fred_core.common import OwnerFilter

from agentic_backend.common.kf_base_client import KfBaseClient
from agentic_backend.common.kf_document_client import KfDocumentClient, RawContentBlob
from agentic_backend.common.kf_tag_client import KfTagClient, _normalize_folder


@pytest.fixture(autouse=True)
def _bypass_real_client_construction(monkeypatch):
    """KfBaseClient.__init__ needs a live ApplicationContext (HTTP client, KPI
    writer, timeouts). These unit tests only need the auth-mode wiring, so we
    replace __init__ with a minimal stand-in that still honors the
    `agent` / `access_token` construction contract (mirroring production:
    one of the two must be provided)."""

    def fake_init(
        self,
        allowed_methods=frozenset(),
        *,
        agent=None,
        access_token=None,
        refresh_user_access_token=None,
    ):
        if not agent and not access_token:
            raise ValueError("KfBaseClient requires either `agent` or `access_token`.")
        self._agent = agent
        self._static_access_token = access_token
        self._refresh_cb = refresh_user_access_token
        self._connect_timeout = 5.0
        self._read_timeout = 15.0
        self._summarize_read_timeout = 120.0
        self._summarize_max_chars_default = None

    monkeypatch.setattr(KfBaseClient, "__init__", fake_init)


def _json_response(payload: object) -> httpx.Response:
    return httpx.Response(
        200, json=payload, request=httpx.Request("GET", "http://example.test/")
    )


def _bytes_response(
    content: bytes, *, content_type: str, content_disposition: str | None = None
) -> httpx.Response:
    headers = {"Content-Type": content_type}
    if content_disposition is not None:
        headers["Content-Disposition"] = content_disposition
    return httpx.Response(
        200,
        content=content,
        headers=headers,
        request=httpx.Request("GET", "http://example.test/"),
    )


# ---------------------------------------------------------------------------
# Construction: agent= and access_token= both supported (token-only is needed
# by the analyze endpoint and save processor downstream).
# ---------------------------------------------------------------------------


def test_kf_tag_client_constructs_from_access_token_only():
    client = KfTagClient(access_token="tok-123")
    assert client._static_access_token == "tok-123"
    assert client._agent is None


def test_kf_tag_client_constructs_from_agent():
    sentinel_agent = object()
    client = KfTagClient(agent=sentinel_agent)  # type: ignore[arg-type]
    assert client._agent is sentinel_agent
    assert client._static_access_token is None


def test_kf_tag_client_requires_agent_or_token():
    with pytest.raises(ValueError):
        KfTagClient()


# ---------------------------------------------------------------------------
# Folder normalization (pure helper)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("images/flags", "images/flags"),
        ("images/flags/", "images/flags"),
        ("/images/flags", "images/flags"),
        (" images/flags ", "images/flags"),
        ("images//flags", "images/flags"),
        ("images\\flags", "images/flags"),
        (" images / flags ", "images/flags"),
        ("", ""),
        ("/", ""),
    ],
)
def test_normalize_folder(raw, expected):
    assert _normalize_folder(raw) == expected


# ---------------------------------------------------------------------------
# resolve_folder / list_document_tags
# ---------------------------------------------------------------------------


def _tags_payload():
    return [
        {"id": "tag-flags", "name": "flags", "path": "images"},
        {"id": "tag-logos", "name": "logos", "path": "images"},
        {"id": "tag-root", "name": "shared", "path": None},
    ]


@pytest.mark.asyncio
async def test_resolve_folder_returns_matching_tag_id(monkeypatch):
    async def fake_request(self, *, method, path, phase_name, **kwargs):
        return _json_response(_tags_payload())

    monkeypatch.setattr(KfTagClient, "_request_with_token_refresh", fake_request)

    client = KfTagClient(access_token="tok")
    tag_id = await client.resolve_folder(
        "images/flags", owner_filter=OwnerFilter.PERSONAL
    )
    assert tag_id == "tag-flags"


@pytest.mark.asyncio
async def test_resolve_folder_root_level_tag(monkeypatch):
    async def fake_request(self, *, method, path, phase_name, **kwargs):
        return _json_response(_tags_payload())

    monkeypatch.setattr(KfTagClient, "_request_with_token_refresh", fake_request)

    client = KfTagClient(access_token="tok")
    tag_id = await client.resolve_folder("shared", owner_filter=OwnerFilter.PERSONAL)
    assert tag_id == "tag-root"


@pytest.mark.asyncio
async def test_resolve_folder_returns_none_when_absent(monkeypatch):
    async def fake_request(self, *, method, path, phase_name, **kwargs):
        return _json_response(_tags_payload())

    monkeypatch.setattr(KfTagClient, "_request_with_token_refresh", fake_request)

    client = KfTagClient(access_token="tok")
    tag_id = await client.resolve_folder(
        "images/missing", owner_filter=OwnerFilter.PERSONAL
    )
    assert tag_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "folder", ["images/flags/", " images/flags ", "/images/flags", "images\\flags"]
)
async def test_resolve_folder_normalizes_input(monkeypatch, folder):
    async def fake_request(self, *, method, path, phase_name, **kwargs):
        return _json_response(_tags_payload())

    monkeypatch.setattr(KfTagClient, "_request_with_token_refresh", fake_request)

    client = KfTagClient(access_token="tok")
    tag_id = await client.resolve_folder(folder, owner_filter=OwnerFilter.PERSONAL)
    assert tag_id == "tag-flags"


@pytest.mark.asyncio
async def test_resolve_folder_is_case_sensitive(monkeypatch):
    async def fake_request(self, *, method, path, phase_name, **kwargs):
        return _json_response(_tags_payload())

    monkeypatch.setattr(KfTagClient, "_request_with_token_refresh", fake_request)

    client = KfTagClient(access_token="tok")
    tag_id = await client.resolve_folder(
        "Images/Flags", owner_filter=OwnerFilter.PERSONAL
    )
    assert tag_id is None


@pytest.mark.asyncio
async def test_list_document_tags_forwards_query_params(monkeypatch):
    seen_params: dict = {}

    async def fake_request(self, *, method, path, phase_name, **kwargs):
        seen_params.update(kwargs.get("params", {}))
        assert path == "/tags"
        assert method == "GET"
        return _json_response(_tags_payload())

    monkeypatch.setattr(KfTagClient, "_request_with_token_refresh", fake_request)

    client = KfTagClient(access_token="tok")
    await client.list_document_tags(
        owner_filter=OwnerFilter.TEAM, team_id="team-7", path_prefix="images"
    )

    assert seen_params["type"] == "document"
    assert seen_params["owner_filter"] == "team"
    assert seen_params["team_id"] == "team-7"
    assert seen_params["path_prefix"] == "images"


@pytest.mark.asyncio
async def test_resolve_folder_forwards_owner_filter_and_team_id(monkeypatch):
    seen_params: dict = {}

    async def fake_request(self, *, method, path, phase_name, **kwargs):
        seen_params.update(kwargs.get("params", {}))
        return _json_response(_tags_payload())

    monkeypatch.setattr(KfTagClient, "_request_with_token_refresh", fake_request)

    client = KfTagClient(access_token="tok")
    await client.resolve_folder(
        "images/flags", owner_filter=OwnerFilter.TEAM, team_id="team-9"
    )

    assert seen_params["owner_filter"] == "team"
    assert seen_params["team_id"] == "team-9"
    # No path_prefix forwarded by resolve_folder (it lists then matches locally).
    assert "path_prefix" not in seen_params


@pytest.mark.asyncio
async def test_resolve_folder_empty_input_returns_none_without_listing(monkeypatch):
    called = False

    async def fake_request(self, *, method, path, phase_name, **kwargs):
        nonlocal called
        called = True
        return _json_response(_tags_payload())

    monkeypatch.setattr(KfTagClient, "_request_with_token_refresh", fake_request)

    client = KfTagClient(access_token="tok")
    assert (
        await client.resolve_folder("  /  ", owner_filter=OwnerFilter.PERSONAL) is None
    )
    assert called is False


@pytest.mark.asyncio
async def test_list_document_tags_skips_malformed_entries(monkeypatch):
    async def fake_request(self, *, method, path, phase_name, **kwargs):
        return _json_response(
            [
                {"id": "ok", "name": "flags", "path": "images"},
                {"name": "no-id", "path": "images"},  # missing id
                {"id": "no-name", "path": "images"},  # missing name
            ]
        )

    monkeypatch.setattr(KfTagClient, "_request_with_token_refresh", fake_request)

    client = KfTagClient(access_token="tok")
    tags = await client.list_document_tags(owner_filter=OwnerFilter.PERSONAL)
    assert [t.tag_id for t in tags] == ["ok"]
    assert tags[0].full_path == "images/flags"


# ---------------------------------------------------------------------------
# fetch_raw_content (KfDocumentClient)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_raw_content_returns_bytes_and_type(monkeypatch):
    async def fake_request(self, *, method, path, phase_name, **kwargs):
        assert path == "/raw_content/doc-1"
        assert method == "GET"
        return _bytes_response(
            b"\x89PNG-data",
            content_type="image/png",
            content_disposition='attachment; filename="flag.png"',
        )

    monkeypatch.setattr(KfDocumentClient, "_request_with_token_refresh", fake_request)

    client = KfDocumentClient(agent=object())  # type: ignore[arg-type]
    blob = await client.fetch_raw_content(document_uid="doc-1")

    assert isinstance(blob, RawContentBlob)
    assert blob.bytes == b"\x89PNG-data"
    assert blob.content_type == "image/png"
    assert blob.filename == "flag.png"
    assert blob.size == len(b"\x89PNG-data")


@pytest.mark.asyncio
async def test_fetch_raw_content_falls_back_to_uid_filename(monkeypatch):
    async def fake_request(self, *, method, path, phase_name, **kwargs):
        # No Content-Disposition header at all, default content type.
        return _bytes_response(b"data", content_type="application/octet-stream")

    monkeypatch.setattr(KfDocumentClient, "_request_with_token_refresh", fake_request)

    client = KfDocumentClient(agent=object())  # type: ignore[arg-type]
    blob = await client.fetch_raw_content(document_uid="doc-xyz")

    assert blob.filename == "doc-xyz"
    assert blob.content_type == "application/octet-stream"
    assert blob.bytes == b"data"
