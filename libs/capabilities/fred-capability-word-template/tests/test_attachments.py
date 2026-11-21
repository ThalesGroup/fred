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

"""An attached Word file as the base document: the upload route,
``use_attached_document``, the
prompt fragment, the base-bytes helper, the sha256-keyed analysis and an
empty library - all offline (fake store, fake assets, fake chat model)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import cast

import pytest
from conftest import load
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_capability_word_template import documents as documents_module
from fred_capability_word_template import middleware as middleware_module
from fred_capability_word_template import router as router_module
from fred_capability_word_template import store as store_module
from fred_capability_word_template.capability import (
    WordTemplateCapability,
)
from fred_capability_word_template.config import (
    WordTemplateConfig,
    WordTemplateEntry,
)
from fred_capability_word_template.middleware import (
    WordTemplateMiddleware,
)
from fred_capability_word_template.prompt import (
    ENGINE_PRINCIPLES,
)
from fred_capability_word_template.router import build_router
from fred_capability_word_template.session_document import (
    BaseUnavailable,
    content_sha256,
    load_base_bytes,
)
from fred_capability_word_template.store import BaseRef
from fred_core import KeycloakUser, get_current_user
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
    SaveContext,
)
from fred_sdk.contracts.runtime import RuntimeServices
from langchain_core.messages import AIMessage, SystemMessage
from port_fakes import FakeAssets, FakeWordTemplateStore

FORM_KEY = "word_template.docx.form"
_PREFIX = "/capabilities/word_template"
_AUTH = {"Authorization": "Bearer token-1"}
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture(autouse=True)
def _clean_caches() -> Iterator[None]:
    documents_module._BASES.clear()
    documents_module._STATES.clear()
    middleware_module._ANALYSIS_FAILURES.clear()
    middleware_module._ANALYSIS_LOCKS.clear()
    documents_module.SEEN.clear()
    yield


@pytest.fixture()
def fake_store() -> Iterator[FakeWordTemplateStore]:
    fake = FakeWordTemplateStore()
    store_module.set_store_provider(lambda: fake)
    try:
        yield fake
    finally:
        store_module.clear_store_provider()


async def _attach_async(
    fake: FakeWordTemplateStore, content: bytes, name: str = "report.docx"
):
    return await fake.put_attachment("s-1", name, content_sha256(content), content)


def _attach(fake: FakeWordTemplateStore, content: bytes, name: str = "report.docx"):
    return asyncio.run(
        fake.put_attachment("s-1", name, content_sha256(content), content)
    )


def _ctx(assets, library) -> CapabilityContext:
    return CapabilityContext(
        identity=CapabilityIdentity(
            user_id="u-1",
            session_id="s-1",
            team_id="team-1",
            agent_instance_id="agent-1",
        ),
        config=WordTemplateConfig(template_library=library),
        turn_options=EmptyModel(),
        services=RuntimeServices(agent_assets=assets),
    )


def _tools(assets, library) -> dict:
    return {t.name: t for t in WordTemplateCapability().tools(_ctx(assets, library))}


def _form_library() -> list[WordTemplateEntry]:
    return [WordTemplateEntry(template_key=FORM_KEY, label="Weekly report")]


class _Request:
    def __init__(self, model=None) -> None:
        self.model = model
        self.system_prompt = "AGENT PROMPT"
        self.overridden: SystemMessage | None = None

    def override(self, *, system_message: SystemMessage) -> _Request:
        self.overridden = system_message
        return self


async def _overlay(assets, library, model=None) -> str:
    middleware = WordTemplateMiddleware(_ctx(assets, library))

    async def handler(req):
        return req

    result = cast(
        _Request,
        await middleware.awrap_model_call(_Request(model), handler),  # type: ignore[arg-type]
    )
    assert result.overridden is not None
    return str(result.overridden.content)


# --- route ---------------------------------------------------------------------------


@pytest.fixture()
def http(fake_store) -> TestClient:
    app = FastAPI()
    app.include_router(build_router(), prefix=_PREFIX)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="u-1", username="u-1", roles=[]
    )
    return TestClient(app)


def _upload(http: TestClient, content: bytes, name: str = "report.docx"):
    return http.post(
        f"{_PREFIX}/sessions/s-1/attachments",
        files={"file": (name, content, _DOCX)},
        headers=_AUTH,
    )


def test_upload_keeps_a_valid_docx(http, fake_store, report_bytes):
    response = _upload(http, report_bytes)
    assert response.status_code == 201
    assert response.json() == {"attachment_id": "doc1", "filename": "report.docx"}
    assert asyncio.run(fake_store.get_attachment_content("s-1", "doc1")) == report_bytes


def test_upload_rejects_a_file_python_docx_cannot_open(http, fake_store):
    response = _upload(http, b"PK not really a docx", name="broken.docx")
    assert response.status_code == 415
    assert fake_store.attachments == {}


def test_upload_rejects_a_too_big_file(http, fake_store, report_bytes, monkeypatch):
    monkeypatch.setattr(router_module, "MAX_ATTACHMENT_BYTES", len(report_bytes) - 1)
    response = _upload(http, report_bytes)
    assert response.status_code == 413
    assert fake_store.attachments == {}


def test_upload_deduplicates_by_content(http, fake_store, report_bytes, form_bytes):
    assert _upload(http, report_bytes).json()["attachment_id"] == "doc1"
    again = _upload(http, report_bytes, name="copy.docx").json()
    assert again == {"attachment_id": "doc1", "filename": "report.docx"}
    assert _upload(http, form_bytes, name="form.docx").json()["attachment_id"] == "doc2"
    assert len(fake_store.attachments["s-1"]) == 2


def test_session_and_download_with_an_attachment_base(http, fake_store, report_bytes):
    info = _attach(fake_store, report_bytes)
    asyncio.run(
        fake_store.select_base(
            "s-1",
            BaseRef("attachment", info.attachment_id),
            store_module.Writer(user_id="u-1"),
            expected_count=0,
        )
    )
    body = http.get(f"{_PREFIX}/sessions/s-1").json()
    assert body["base_kind"] == "attachment" and body["base_ref"] == "doc1"
    assert body["base_filename"] == "report.docx" and body["template_key"] is None
    # No agent instance needed: the base is the capability's own copy.
    response = http.get(f"{_PREFIX}/sessions/s-1/document.docx", headers=_AUTH)
    assert response.status_code == 200
    assert "Describe the context here." in [
        p.text for p in load(response.content).paragraphs
    ]


def test_a_file_removed_from_the_chat_is_forgotten(http, fake_store, report_bytes):
    _upload(http, report_bytes)
    response = http.delete(f"{_PREFIX}/sessions/s-1/attachments/doc1", headers=_AUTH)
    assert response.status_code == 204
    assert fake_store.attachments["s-1"] == []
    gone = http.delete(f"{_PREFIX}/sessions/s-1/attachments/doc1", headers=_AUTH)
    assert gone.status_code == 404


def test_the_document_base_is_never_forgotten(http, fake_store, report_bytes):
    info = _attach(fake_store, report_bytes)
    asyncio.run(
        fake_store.select_base(
            "s-1",
            BaseRef("attachment", info.attachment_id),
            store_module.Writer(user_id="u-1"),
            expected_count=0,
        )
    )
    response = http.delete(f"{_PREFIX}/sessions/s-1/attachments/doc1", headers=_AUTH)
    assert response.status_code == 409
    assert len(fake_store.attachments["s-1"]) == 1


def test_an_image_removed_from_the_chat_is_forgotten_unless_placed(http, fake_store):
    for name in ("a.png", "b.png"):
        asyncio.run(
            fake_store.put_image(
                "s-1",
                filename=name,
                content_type="image/png",
                sha256=name,
                content=b"png",
            )
        )
    fake_store.batches["s-1"] = [
        [{"op": "write", "from": "P1", "to": "P1", "markdown": "![A](img:img1)"}]
    ]
    placed = http.delete(f"{_PREFIX}/sessions/s-1/images/img1", headers=_AUTH)
    assert placed.status_code == 409
    response = http.delete(f"{_PREFIX}/sessions/s-1/images/img2", headers=_AUTH)
    assert response.status_code == 204
    assert [i.image_id for i, _ in fake_store.images["s-1"]] == ["img1"]


# --- base-bytes helper -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_base_bytes_for_both_kinds(fake_store, form_bytes, report_bytes):
    async def fetch(key: str) -> bytes:
        if key == FORM_KEY:
            return form_bytes
        raise KeyError(key)

    template = BaseRef("template", FORM_KEY)
    assert await load_base_bytes(template, "s-1", fetch) == form_bytes
    with pytest.raises(BaseUnavailable):
        await load_base_bytes(BaseRef("template", "gone"), "s-1", fetch)
    await fake_store.put_attachment(
        "s-1", "r.docx", content_sha256(report_bytes), report_bytes
    )
    attachment = BaseRef("attachment", "doc1")
    assert await load_base_bytes(attachment, "s-1", fetch) == report_bytes
    with pytest.raises(BaseUnavailable):
        await load_base_bytes(BaseRef("attachment", "doc9"), "s-1", fetch)
    with pytest.raises(BaseUnavailable):
        await load_base_bytes(attachment, None, fetch)
    assert template.identity == FORM_KEY
    assert attachment.identity == "attachment:doc1"


# --- use_attached_document ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_use_attached_document_before_any_edit(
    fake_store, report_bytes, form_bytes
):
    await _attach_async(fake_store, report_bytes)
    tools = _tools(FakeAssets({FORM_KEY: form_bytes}), _form_library())
    content, artifact = await tools["use_attached_document"].coroutine(
        attachment=" DOC1 "
    )
    assert artifact.is_error is False, content
    assert '"report.docx" (doc1) is now the base' in content and "part 0:" in content
    assert fake_store.sessions["s-1"].attachment_id == "doc1"
    # The tools now work on the attachment, and the first edit pins it.
    read, _ = await tools["read_template"].coroutine(part="0")
    assert "Cover title" in read
    content, artifact = await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "P1", "text": "New cover"}]
    )
    assert artifact.is_error is False, content
    row = fake_store.sessions["s-1"]
    assert row.pinned_at is not None and row.base == BaseRef("attachment", "doc1")


@pytest.mark.asyncio
async def test_use_attached_document_refused_after_edits_on_another_base(
    fake_store, report_bytes, form_bytes
):
    await _attach_async(fake_store, report_bytes)
    tools = _tools(FakeAssets({FORM_KEY: form_bytes}), _form_library())
    await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T1.R1.C2", "text": "Week 41"}]
    )
    content, artifact = await tools["use_attached_document"].coroutine(
        attachment="doc1"
    )
    assert artifact.is_error is False
    assert "explicitly agrees to start over" in content and "undo_last_edit" in content
    assert fake_store.sessions["s-1"].base == BaseRef("template", FORM_KEY)
    # Undo back to zero edits: switching is possible again.
    await tools["undo_last_edit"].coroutine()
    content, artifact = await tools["use_attached_document"].coroutine(
        attachment="doc1"
    )
    assert artifact.is_error is False, content
    assert fake_store.sessions["s-1"].base == BaseRef("attachment", "doc1")


@pytest.mark.asyncio
async def test_use_attached_document_unknown_or_unreadable(fake_store, report_bytes):
    tools = _tools(FakeAssets(), [])
    content, artifact = await tools["use_attached_document"].coroutine(
        attachment="doc1"
    )
    assert artifact.is_error is False and "No Word file is attached" in content
    await _attach_async(fake_store, report_bytes)
    content, artifact = await tools["use_attached_document"].coroutine(
        attachment="doc7"
    )
    assert artifact.is_error is False and 'doc1 ("report.docx")' in content
    # Stored bytes that cannot be mapped are never made the base.
    await fake_store.put_attachment("s-1", "bad.docx", "x", b"not a docx")
    content, artifact = await tools["use_attached_document"].coroutine(
        attachment="doc2"
    )
    assert artifact.is_error is False and "could not be read" in content
    assert "s-1" not in fake_store.sessions


@pytest.mark.asyncio
async def test_select_template_after_an_attachment_base_with_edits_is_refused(
    fake_store, report_bytes, form_bytes
):
    await _attach_async(fake_store, report_bytes)
    library = [
        *_form_library(),
        WordTemplateEntry(template_key="word_template.docx.other", label="Other"),
    ]
    tools = _tools(FakeAssets({FORM_KEY: form_bytes}), library)
    await tools["use_attached_document"].coroutine(attachment="doc1")
    await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "P1", "text": "x"}]
    )
    content, artifact = await tools["select_template"].coroutine(label="Weekly report")
    assert artifact.is_error is False and "an attached file" in content


# --- prompt -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_lists_attachments_as_sources_by_default(
    fake_store, report_bytes, form_bytes
):
    await _attach_async(fake_store, report_bytes)
    text = await _overlay(FakeAssets({FORM_KEY: form_bytes}), _form_library())
    assert ENGINE_PRINCIPLES in text
    assert '- doc1: "report.docx"' in text and "- the base of the document" not in text
    assert "source of information by default" in text
    assert "platform's approval step" in text and "use_attached_document" in text
    assert ", instead of a template" in text
    # A file that feeds the content stays a source, even "to write from".
    flat = " ".join(text.split())
    assert "only when it IS the document to deliver" in flat
    assert "stays a source, even when they ask to write the document from it" in flat
    assert "the document starts from that template" in flat


@pytest.mark.asyncio
async def test_prompt_names_the_only_template_as_loaded(fake_store, form_bytes):
    text = " ".join(
        (await _overlay(FakeAssets({FORM_KEY: form_bytes}), _form_library())).split()
    )
    assert 'Template for this conversation: "Weekly report", already loaded' in text
    assert "Never look for a template with other tools" in text
    assert "may switch with select_template" not in text
    # With several templates, the selected one is named and can be switched.
    library = [*_form_library(), WordTemplateEntry(template_key="k2.docx", label="B")]
    await fake_store.select_base(
        "s-1",
        BaseRef("template", FORM_KEY),
        store_module.Writer(user_id="u-1"),
        expected_count=0,
    )
    text = " ".join(
        (await _overlay(FakeAssets({FORM_KEY: form_bytes}), library)).split()
    )
    assert 'Template for this conversation: "Weekly report", already loaded' in text
    assert "may switch with select_template" in text


@pytest.mark.asyncio
async def test_prompt_with_an_empty_library(fake_store, report_bytes):
    await _attach_async(fake_store, report_bytes)
    # Attachment, no base yet: the list and the rule, no document yet.
    text = await _overlay(FakeAssets(), [])
    assert ENGINE_PRINCIPLES not in text
    assert '- doc1: "report.docx"' in text
    assert "this agent has no template" in text
    assert "starts from that template" not in " ".join(text.split())
    # Once chosen, the engine works on it: principles, analysis, parts.
    await fake_store.select_base(
        "s-1",
        BaseRef("attachment", "doc1"),
        store_module.Writer(user_id="u-1"),
        expected_count=0,
    )
    text = await _overlay(FakeAssets(), [])
    assert ENGINE_PRINCIPLES in text
    assert '- doc1: "report.docx" - the base of the document' in text
    assert "DOCUMENT PARTS" in text and "nothing edited yet" in text


@pytest.mark.asyncio
async def test_validate_config_accepts_an_empty_library():
    result = await WordTemplateCapability().validate_config(
        WordTemplateConfig(template_library=[]),
        {},
        SaveContext(
            identity=CapabilityIdentity(user_id="u-1", team_id="team-1"),
            services=RuntimeServices(agent_assets=FakeAssets()),
        ),
    )
    assert result.template_library is None


# --- analysis keyed by sha256 -----------------------------------------------------------


class _CountingModel:
    model_name = "fake-model"

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls = 0

    async def ainvoke(self, messages, config=None):
        self.calls += 1
        return AIMessage(content=self.answer)


_ANALYSIS = {"summary": "A report with chapters.", "parts": [], "repeatable_blocks": []}


@pytest.mark.asyncio
async def test_identical_bytes_are_analysed_once_whatever_their_origin(
    fake_store, form_bytes
):
    model = _CountingModel(json.dumps(_ANALYSIS))
    assets = FakeAssets({FORM_KEY: form_bytes})
    text = await _overlay(assets, _form_library(), model=model)
    assert "A report with chapters." in text and model.calls == 1
    # The same bytes attached and made the base: the cached analysis is used.
    await _attach_async(fake_store, form_bytes, name="same.docx")
    await fake_store.select_base(
        "s-1",
        BaseRef("attachment", "doc1"),
        store_module.Writer(user_id="u-1"),
        expected_count=0,
    )
    documents_module._BASES.clear()
    text = await _overlay(assets, _form_library(), model=model)
    assert "A report with chapters." in text and model.calls == 1
    assert set(fake_store.analyses) == {content_sha256(form_bytes)}


def test_pod_caches_are_bounded_by_bytes_too():
    lru = documents_module.Lru[str, bytes](10, max_weight=10, weigh=len)
    lru.put("a", b"12345")
    lru.put("b", b"123456")  # 11 bytes in total: the oldest goes
    assert lru.get("a") is None and lru.get("b") == b"123456"
    lru.put("huge", b"x" * 11)  # never kept
    assert lru.get("huge") is None and lru.get("b") == b"123456"
    lru.put("b", b"1")  # replacing re-weighs
    lru.put("c", b"123456789")
    assert lru.get("b") == b"1" and lru.get("c") == b"123456789"


@pytest.mark.asyncio
async def test_two_conversations_never_share_an_attached_document(
    fake_store, report_bytes, form_bytes
):
    # Both files are "doc1" in their own conversation, with the same empty log.
    def tools_of(session_id: str, user_id: str) -> dict:
        ctx = CapabilityContext(
            identity=CapabilityIdentity(
                user_id=user_id,
                session_id=session_id,
                team_id="team-1",
                agent_instance_id="agent-1",
            ),
            config=WordTemplateConfig(template_library=[]),
            turn_options=EmptyModel(),
            services=RuntimeServices(agent_assets=FakeAssets({})),
        )
        return {t.name: t for t in WordTemplateCapability().tools(ctx)}

    for session_id, content in (("s-1", report_bytes), ("s-2", form_bytes)):
        await fake_store.put_attachment(
            session_id, "file.docx", content_sha256(content), content
        )
    alice, bob = tools_of("s-1", "alice"), tools_of("s-2", "bob")
    await alice["use_attached_document"].coroutine(attachment="doc1")
    await bob["use_attached_document"].coroutine(attachment="doc1")
    read_alice, _ = await alice["read_template"].coroutine(part="0")
    read_bob, _ = await bob["read_template"].coroutine(part="1")
    assert "Cover title" in read_alice and "Cover title" not in read_bob
    assert "Weekly report" in read_bob


@pytest.mark.asyncio
async def test_a_reused_attachment_id_never_serves_the_old_file(
    fake_store, report_bytes, form_bytes
):
    # The cache must follow the file's content, not its short id.
    tools = _tools(FakeAssets({FORM_KEY: form_bytes}), _form_library())
    await _attach_async(fake_store, report_bytes)
    await tools["use_attached_document"].coroutine(attachment="doc1")
    await tools["read_template"].coroutine(part="1")
    await fake_store.delete_attachment("s-1", "doc1", keep_image_ids=())
    await _attach_async(fake_store, form_bytes, "other.docx")  # gets "doc1" again
    read, _ = await tools["read_template"].coroutine(part="1")
    assert "Cover title" not in read and "Weekly report" in read
