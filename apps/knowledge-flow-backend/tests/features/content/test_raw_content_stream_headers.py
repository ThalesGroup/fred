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

"""The inline raw-content stream must never let an uploaded SVG or HTML run on
the application origin, while the PDF viewer keeps loading it inline."""

from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import KeycloakUser, get_current_user

from knowledge_flow_backend.core.stores.content.base_content_store import FileMetadata
from knowledge_flow_backend.features.content.content_controller import ContentController
from knowledge_flow_backend.features.content.content_service import ContentService

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(2)</script></svg>'
PDF = b"%PDF-1.5 fake body"


class _FakeContentStore:
    def __init__(self, body: bytes, content_type: str) -> None:
        self._body = body
        self._content_type = content_type

    def get_file_metadata(self, document_uid: str) -> FileMetadata:
        return FileMetadata(size=len(self._body), file_name="stored", content_type=self._content_type)

    def get_content(self, document_uid: str) -> BytesIO:
        return BytesIO(self._body)

    def get_content_range(self, document_uid: str, *, start: int, length: int) -> BytesIO:
        return BytesIO(self._body[start : start + length])


async def _allow(*args, **kwargs) -> None:
    return None


def _client(body: bytes, content_type: str, document_name: str) -> TestClient:
    service = ContentService.__new__(ContentService)
    service.content_store = _FakeContentStore(body, content_type)

    async def get_metadata_by_uid(document_uid: str):
        return SimpleNamespace(document_name=document_name)

    service.metadata_store = SimpleNamespace(get_metadata_by_uid=get_metadata_by_uid)
    service.rebac = SimpleNamespace(check_user_permission_or_raise=_allow)

    controller = ContentController.__new__(ContentController)
    controller.service = service
    router = APIRouter()
    controller._register_routes(router)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="alice", username="alice", email=None, roles=[])
    return TestClient(app)


def _assert_sandboxed_inline(response, content_type: str) -> None:
    assert response.headers["content-security-policy"] == "sandbox"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-type"].startswith(content_type)
    assert response.headers["content-disposition"].startswith("inline;")


def test_full_svg_stream_is_sandboxed() -> None:
    response = _client(SVG, "image/svg+xml", "probe.svg").get("/raw_content/stream/doc-1")

    assert response.status_code == 200
    assert response.content == SVG
    _assert_sandboxed_inline(response, "image/svg+xml")


@pytest.mark.parametrize("range_header", ["bytes=0-9", "bytes=10-", "bytes=-5"])
def test_ranged_svg_stream_is_sandboxed(range_header: str) -> None:
    response = _client(SVG, "image/svg+xml", "probe.svg").get("/raw_content/stream/doc-1", headers={"Range": range_header})

    assert response.status_code == 206
    start, end = (int(bound) for bound in response.headers["content-range"].removeprefix("bytes ").split("/")[0].split("-"))
    assert response.content == SVG[start : end + 1]
    _assert_sandboxed_inline(response, "image/svg+xml")


def test_pdf_preview_stream_still_serves_inline() -> None:
    response = _client(PDF, "application/pdf", "rapport.pdf").get("/raw_content/stream/doc-1")

    assert response.status_code == 200
    assert response.content == PDF
    _assert_sandboxed_inline(response, "application/pdf")
