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

"""A chat image keeps one preview (PNG, or JPEG for a photo): stored at fast ingest, read by its uploader only, gone with the fast delete."""

from __future__ import annotations

import asyncio
import io
import threading
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import KeycloakUser, get_current_user
from fred_core.common import register_exception_handlers
from langchain_community.embeddings import FakeEmbeddings
from PIL import Image, ImageFilter

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.ingestion import attachment_preview
from knowledge_flow_backend.features.ingestion import ingestion_controller as ingestion_module
from knowledge_flow_backend.features.ingestion.attachment_preview import delete_preview, preview_key, read_owned_preview
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController

BASE = "/knowledge-flow/v1"


def _png(size: tuple[int, int] = (3000, 1500)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "blue").save(buffer, format="PNG")
    return buffer.getvalue()


class _Users:
    current = "alice"


@pytest.fixture
def client(app_context, monkeypatch):
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_image_processor.get_configuration",
        lambda: SimpleNamespace(vision_model=None),
    )

    class _NoAdmin:
        async def has_user_permission(self, *_args, **_kwargs) -> bool:
            return False

    monkeypatch.setattr(ingestion_module, "get_rebac_engine", lambda: _NoAdmin())
    monkeypatch.setattr(ApplicationContext, "get_embedder", lambda self: FakeEmbeddings(size=8))
    users = _Users()
    app = FastAPI()
    register_exception_handlers(app)
    router = APIRouter(prefix=BASE)
    IngestionController(router)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid=users.current, username=users.current, email=None, roles=[])
    with TestClient(app) as test_client:
        test_client.users = users  # type: ignore[attr-defined]
        yield test_client


def _photo() -> bytes:
    noise = Image.effect_noise((1200, 800), 60).filter(ImageFilter.GaussianBlur(1))
    buffer = io.BytesIO()
    Image.merge("RGB", (noise, noise, noise.transpose(Image.Transpose.FLIP_LEFT_RIGHT))).save(buffer, format="PNG")
    return buffer.getvalue()


def _ingest(client: TestClient, session_id: str = "s-1", image: bytes | None = None) -> str:
    response = client.post(f"{BASE}/fast/ingest", files={"file": ("plan.png", image or _png(), "image/png")}, data={"session_id": session_id})
    assert response.status_code == 200, response.text
    return response.json()["document_uid"]


def _stored(content_store, uid: str) -> bytes:
    with content_store.get_object_stream(preview_key(uid)) as stream:
        return stream.read()


def _get(client: TestClient, uid: str, **params: str):
    return client.get(f"{BASE}/fast/preview/{uid}", params=params)


@pytest.mark.parametrize(("image", "fmt", "size"), [(_png(), "PNG", (1568, 784)), (_photo(), "JPEG", (1200, 800))])
def test_ingest_stores_a_bounded_preview_its_uploader_can_read(client: TestClient, content_store, image: bytes, fmt: str, size: tuple) -> None:
    uid = _ingest(client, image=image)

    stored = _stored(content_store, uid)
    preview = Image.open(io.BytesIO(stored))
    assert (preview.format, preview.size) == (fmt, size)
    response = _get(client, uid, session_id="s-1")
    assert response.status_code == 200 and response.content == stored
    assert response.headers["content-type"] == f"image/{fmt.lower()}"
    assert response.headers["cache-control"] == "private, no-store"


def test_only_the_uploader_reads_it_from_its_conversation(client: TestClient) -> None:
    uid = _ingest(client)

    assert _get(client, uid).status_code == 422  # the conversation is required
    assert _get(client, uid, session_id="s-other").status_code == 404
    assert _get(client, "bad.uid", session_id="s-1").status_code == 404
    client.users.current = "bob"  # type: ignore[attr-defined]
    assert _get(client, uid, session_id="s-1").status_code == 404


def test_fast_delete_removes_the_preview(client: TestClient, content_store) -> None:
    uid = _ingest(client)

    assert client.delete(f"{BASE}/fast/delete/{uid}").status_code == 200
    with pytest.raises(FileNotFoundError):
        _stored(content_store, uid)


def test_a_preview_over_the_size_cap_is_not_stored(client: TestClient, content_store, monkeypatch, caplog) -> None:
    monkeypatch.setattr(attachment_preview, "PREVIEW_MAX_BYTES", 100)

    uid = _ingest(client)

    with pytest.raises(FileNotFoundError):
        _stored(content_store, uid)
    assert f"over the size cap: doc_uid={uid}" in caplog.text


def test_busy_preview_reads_answer_503_then_recover(client: TestClient, monkeypatch) -> None:
    uid = _ingest(client)
    slots = threading.BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(attachment_preview, "_read_slots", slots)
    monkeypatch.setattr(attachment_preview, "_READ_SLOT_WAIT_S", 0.05)

    assert _get(client, uid, session_id="s-1").status_code == 503

    slots.release()
    assert _get(client, uid, session_id="s-1").status_code == 200
    assert slots.acquire(blocking=False), "the read slot is given back"


class _Store:
    def __init__(self, found: bool) -> None:
        self.found, self.reads, self.deletes = found, 0, 0

    def get_object_stream(self, key: str):
        self.reads += 1
        if not self.found:
            raise FileNotFoundError(key)
        return io.BytesIO(_png((4, 4)))

    def delete_object(self, key: str) -> None:
        self.deletes += 1
        if not self.found:
            raise FileNotFoundError(key)


class _Chunks:
    def __init__(self) -> None:
        self.reads = 0

    def get_chunks_for_document(self, document_uid: str) -> list:
        self.reads += 1
        return []


@pytest.mark.parametrize(
    ("uid", "found", "store_reads", "chunk_reads"),
    [
        ("../secret", True, 0, 0),  # a malformed uid reads nothing
        ("doc-1", False, 1, 0),  # no object: no ownership query
        ("doc-1", True, 1, 1),  # no chunks left: nothing proves ownership
    ],
)
def test_a_preview_without_proof_of_ownership_is_not_read(uid: str, found: bool, store_reads: int, chunk_reads: int) -> None:
    store, chunks = _Store(found), _Chunks()

    assert asyncio.run(read_owned_preview(store, chunks, uid, "alice", "s-1")) is None  # type: ignore[arg-type]
    assert (store.reads, chunks.reads) == (store_reads, chunk_reads)


@pytest.mark.parametrize(("uid", "found", "deletes"), [("../secret", True, 0), ("doc-1", False, 1)])
def test_deleting_a_preview_that_cannot_exist_is_a_no_op(uid: str, found: bool, deletes: int) -> None:
    store = _Store(found)

    delete_preview(store, uid)  # type: ignore[arg-type]

    assert store.deletes == deletes
