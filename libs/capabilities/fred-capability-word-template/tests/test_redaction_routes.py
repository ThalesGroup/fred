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

"""The collaborator edits the document: the
content / edits / undo routes, the session-ownership check, what the model
is told about the collaborator's edits and the stale-read guard of
``edit_document`` - offline (fake store, stubbed template fetch)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_capability_word_template import documents as documents_module
from fred_capability_word_template import router as router_module
from fred_capability_word_template import store as store_module
from fred_capability_word_template.capability import (
    WordTemplateCapability,
)
from fred_capability_word_template.config import (
    WordTemplateConfig,
    WordTemplateEntry,
)
from fred_capability_word_template.documents import (
    _changed_under_the_model,
    log_mark,
)
from fred_capability_word_template.middleware import (
    WordTemplateMiddleware,
)
from fred_capability_word_template.router import build_router
from fred_capability_word_template.session_document import content_sha256
from fred_capability_word_template.store import (
    BaseRef,
    BatchConflict,
    BatchRecord,
    Writer,
)
from fred_core import KeycloakUser, get_current_user
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.runtime import RuntimeServices
from langchain_core.messages import SystemMessage
from port_fakes import FakeAssets, FakeWordTemplateStore

_PREFIX = "/capabilities/word_template"
_AUTH = {"Authorization": "Bearer token-1"}
FORM_KEY = "word_template.docx.form"
_SET_WEEK = {"op": "set_text", "address": "T1.R1.C2", "text": "Week 41"}


@pytest.fixture(autouse=True)
def _clean_caches() -> Iterator[None]:
    documents_module._BASES.clear()
    documents_module._STATES.clear()
    documents_module.SEEN.clear()
    router_module._TEMPLATE_SHA.clear()
    yield


@pytest.fixture()
def fake() -> Iterator[FakeWordTemplateStore]:
    store = FakeWordTemplateStore()
    store_module.set_store_provider(lambda: store)
    try:
        yield store
    finally:
        store_module.clear_store_provider()


@pytest.fixture()
def http(fake, monkeypatch, form_bytes) -> TestClient:
    async def fetch(**kwargs):
        return form_bytes if kwargs["template_key"] == FORM_KEY else None

    monkeypatch.setattr(router_module, "_fetch_template_bytes", fetch)
    app = FastAPI()
    app.include_router(build_router(), prefix=_PREFIX)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="u-1", username="u-1", roles=[]
    )
    asyncio.run(
        fake.select_base(
            "s-1",
            BaseRef("template", FORM_KEY),
            Writer(user_id="u-1", team_id="team-1", agent_instance_id="agent-1"),
            expected_count=0,
        )
    )
    return TestClient(app)


def _cell(view: dict, table: int, row: int, cell: int) -> dict:
    blocks = view["parts"][0]["blocks"]
    tables = [b for b in blocks if b["kind"] == "table"]
    return tables[table]["rows"][row]["cells"][cell]


def _edit(http: TestClient, base_seq: int, *operations: dict):
    return http.post(
        f"{_PREFIX}/sessions/s-1/edits",
        json={"base_seq": base_seq, "operations": list(operations)},
        headers=_AUTH,
    )


# --- content -------------------------------------------------------------------------


def test_content_of_the_selected_base(http):
    response = http.get(f"{_PREFIX}/sessions/s-1/content", headers=_AUTH)
    assert response.status_code == 200
    view = response.json()
    assert view["seq"] == 0
    assert view["base"] == {"kind": "template", "ref": FORM_KEY}
    assert [p["id"] for p in view["parts"]] == ["1", "hf"]
    assert _cell(view, 0, 0, 1) == {
        "address": "T1.R1.C2",
        "text": "Week 10",
        "edit": "set_text",
        "markdown": "Week 10",
        "col": 2,
        "col_span": 1,
        "row_span": 1,
    }
    assert view["parts"][0]["blocks"][0]["duplicate"] == {
        "op": "repeat",
        "from": "T1",
        "count": 1,
    }


def test_content_without_a_base_is_404(http):
    response = http.get(f"{_PREFIX}/sessions/other/content", headers=_AUTH)
    assert response.status_code == 404


def test_content_shows_the_analysis_repeatable_blocks_until_a_structural_edit(
    http, fake, form_bytes
):
    fake.analyses[content_sha256(form_bytes)] = json.dumps(
        {
            "summary": "a weekly report",
            "repeatable_blocks": [{"addresses": "T1–T2", "one_per": "project"}],
        }
    )
    view = http.get(f"{_PREFIX}/sessions/s-1/content", headers=_AUTH).json()
    (group,) = view["parts"][0]["blocks"]
    assert (group["kind"], group["from"], group["to"]) == ("block_group", "T1", "T2")
    # A set_text keeps the addresses: still grouped (the base's sha is
    # remembered, the snapshot spares the fetch).
    assert _edit(http, 0, _SET_WEEK).json()["parts"][0]["blocks"][0]["kind"] == (
        "block_group"
    )
    view = _edit(http, 1, {"op": "repeat", "from": "T2", "count": 1}).json()
    assert [b["kind"] for b in view["parts"][0]["blocks"]] == [
        "table",
        "paragraph",
        "table",
        "table",
    ]


# --- edits ---------------------------------------------------------------------------


def test_edit_applies_and_records_the_collaborator(http, fake):
    response = _edit(http, 0, _SET_WEEK)
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["seq"] == 1
    assert _cell(view, 0, 0, 1)["text"] == "Week 41"
    assert fake.authors["s-1"] == ["collaborator"]
    assert fake.batches["s-1"] == [[_SET_WEEK]]
    assert fake.sessions["s-1"].pinned_at is not None
    assert fake.snapshots["s-1"].seq == 1
    # The next read uses the snapshot.
    again = http.get(f"{_PREFIX}/sessions/s-1/content", headers=_AUTH).json()
    assert _cell(again, 0, 0, 1)["text"] == "Week 41"


def test_the_collaborator_may_remove_every_copy_of_a_block(http, fake):
    # Only the model's batches must keep a copy of each template block.
    response = _edit(http, 0, {"op": "remove", "from": "T2"})
    assert response.status_code == 200, response.text
    assert fake.authors["s-1"] == ["collaborator"]


def test_a_stale_edit_is_409(http, fake):
    assert _edit(http, 0, _SET_WEEK).status_code == 200
    response = _edit(http, 0, {**_SET_WEEK, "text": "Week 42"})
    assert response.status_code == 409
    assert response.json()["detail"]["seq"] == 1
    assert "reload" in response.json()["detail"]["message"]
    assert len(fake.batches["s-1"]) == 1


def test_an_invalid_batch_is_422_with_every_problem(http, fake):
    response = _edit(
        http,
        0,
        {"op": "set_text", "address": "T9", "text": "x"},
        {"op": "remove", "from": "T2.R1", "to": "T2.R4"},
    )
    assert response.status_code == 422
    problems = response.json()["detail"]["problems"]
    assert len(problems) == 2
    assert "T9" in problems[0] and "every row" in problems[1]
    assert fake.batches.get("s-1", []) == []


def test_an_unknown_field_is_rejected_by_the_request_model(http):
    response = _edit(http, 0, {**_SET_WEEK, "colour": "red"})
    assert response.status_code == 422


def test_undo_drops_the_last_batch_whoever_made_it(http, fake):
    _edit(http, 0, _SET_WEEK)
    asyncio.run(
        fake.append_batch(
            "s-1",
            BaseRef("template", FORM_KEY),
            [{"op": "set_text", "address": "T1.R1.C3", "text": "Year 2027"}],
            Writer(user_id="u-1"),
            expected_count=1,
        )
    )
    stale = http.post(
        f"{_PREFIX}/sessions/s-1/undo", json={"base_seq": 1}, headers=_AUTH
    )
    assert stale.status_code == 409 and stale.json()["detail"]["seq"] == 2
    view = http.post(
        f"{_PREFIX}/sessions/s-1/undo", json={"base_seq": 2}, headers=_AUTH
    ).json()
    assert view["seq"] == 1 and fake.authors["s-1"] == ["collaborator"]
    assert _cell(view, 0, 0, 2)["text"] == "Year 2026"
    view = http.post(f"{_PREFIX}/sessions/s-1/undo", headers=_AUTH).json()
    assert view["seq"] == 0 and _cell(view, 0, 0, 1)["text"] == "Week 10"
    # Nothing left: the view comes back unchanged.
    assert http.post(f"{_PREFIX}/sessions/s-1/undo", headers=_AUTH).json()["seq"] == 0


# --- ownership -----------------------------------------------------------------------


class _History:
    def __init__(self, owner: str | None) -> None:
        self.owner = owner

    async def session_exists(self, session_id: str) -> bool:
        return self.owner is not None

    async def session_belongs_to_user(self, session_id: str, user_id: str) -> bool:
        return user_id == self.owner


_ROUTES = [
    ("get", "/sessions/s-1"),
    ("get", "/sessions/s-1/content"),
    ("post", "/sessions/s-1/edits"),
    ("post", "/sessions/s-1/undo"),
    ("get", "/sessions/s-1/document.docx"),
    ("get", "/sessions/s-1/preview.pdf"),
    ("post", "/sessions/s-1/attachments"),
    ("post", "/sessions/s-1/images"),
    ("get", "/sessions/s-1/images/img1"),
]


@pytest.mark.parametrize(("method", "path"), _ROUTES)
def test_every_route_refuses_another_users_session(http, monkeypatch, method, path):
    monkeypatch.setattr(router_module, "_security_enabled", lambda: True)
    monkeypatch.setattr(router_module, "_history_store", lambda: _History("u-2"))
    response = getattr(http, method)(f"{_PREFIX}{path}", headers=_AUTH)
    assert response.status_code == 403


def test_the_owner_and_a_new_session_are_allowed(http, monkeypatch):
    monkeypatch.setattr(router_module, "_security_enabled", lambda: True)
    monkeypatch.setattr(router_module, "_history_store", lambda: _History("u-1"))
    assert http.get(f"{_PREFIX}/sessions/s-1/content", headers=_AUTH).status_code == 200
    monkeypatch.setattr(router_module, "_history_store", lambda: _History(None))
    assert http.get(f"{_PREFIX}/sessions/s-1", headers=_AUTH).status_code == 200


# --- the model's side ----------------------------------------------------------------


def _ctx(form_bytes) -> CapabilityContext:
    return CapabilityContext(
        identity=CapabilityIdentity(
            user_id="u-1",
            session_id="s-1",
            team_id="team-1",
            agent_instance_id="agent-1",
        ),
        config=WordTemplateConfig(
            template_library=[WordTemplateEntry(template_key=FORM_KEY, label="Report")]
        ),
        turn_options=EmptyModel(),
        services=RuntimeServices(agent_assets=FakeAssets({FORM_KEY: form_bytes})),
    )


def _tools(form_bytes) -> dict[str, Any]:
    return {t.name: t for t in WordTemplateCapability().tools(_ctx(form_bytes))}


class _Request:
    model = None
    system_prompt = "AGENT PROMPT"
    overridden: SystemMessage | None = None

    def override(self, *, system_message: SystemMessage) -> _Request:
        self.overridden = system_message
        return self


async def _overlay(form_bytes) -> str:
    middleware = WordTemplateMiddleware(_ctx(form_bytes))

    async def handler(req):
        return req

    result = cast(_Request, await middleware.awrap_model_call(_Request(), handler))  # type: ignore[arg-type]
    assert result.overridden is not None
    return str(result.overridden.content)


async def _collaborator_edit(fake: FakeWordTemplateStore, *operations: dict) -> None:
    await fake.append_batch(
        "s-1",
        BaseRef("template", FORM_KEY),
        list(operations),
        Writer(user_id="u-1"),
        expected_count=len(fake.batches.get("s-1", [])),
        author="collaborator",
    )


@pytest.mark.asyncio
async def test_the_prompt_lists_the_collaborators_edits_since_the_models_last(
    fake, form_bytes
):
    tools = _tools(form_bytes)
    await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T1.R1.C3", "text": "Year 2027"}]
    )
    text = await _overlay(form_bytes)
    assert "EDITED BY THE COLLABORATOR" not in text
    await _collaborator_edit(
        fake, _SET_WEEK, {"op": "repeat", "from": "T2", "count": 1}
    )
    text = await _overlay(form_bytes)
    assert "batch 1 (you): set_text T1.R1.C3" in text
    assert "batch 2 (the collaborator): set_text T1.R1.C2, repeat T2 ×1" in text
    assert 'T1.R1.C2 set to "Week 41"' in text and "T2 duplicated ×1" in text
    assert "never overwrite, rewrite or undo their edits unless they ask" in text
    # Once the model edits again, the list is gone (the done list remains).
    tools = _tools(form_bytes)
    await tools["read_template"].coroutine(part="1")
    await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T1.R1.C1", "text": "Report"}]
    )
    text = await _overlay(form_bytes)
    assert "EDITED BY THE COLLABORATOR" not in text
    assert "batch 3 (you)" in text


@pytest.mark.asyncio
async def test_edit_document_refuses_a_batch_made_before_a_collaborator_edit(
    fake, form_bytes
):
    tools = _tools(form_bytes)
    await tools["read_template"].coroutine(part="1")
    await _collaborator_edit(fake, {"op": "repeat", "from": "T2", "count": 1})
    content, artifact = await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T2.R2.C2", "text": "P1"}]
    )
    assert artifact.is_error is False
    assert "collaborator changed the document" in content
    assert len(fake.batches["s-1"]) == 1
    # Read again: the batch goes through.
    await tools["read_template"].coroutine(part="1")
    content, artifact = await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T2.R2.C2", "text": "P1"}]
    )
    assert artifact.is_error is False, content
    assert fake.authors["s-1"] == ["collaborator", "model"]


@pytest.mark.asyncio
async def test_edit_document_refuses_after_a_collaborator_undo(fake, form_bytes):
    tools = _tools(form_bytes)
    await tools["edit_document"].coroutine(operations=[_SET_WEEK])
    await fake.drop_last_batch("s-1")
    content, artifact = await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T1.R1.C3", "text": "x"}]
    )
    assert artifact.is_error is False and "read_template" in content


@pytest.mark.asyncio
async def test_without_a_read_mark_the_models_last_batch_stands_in(fake, form_bytes):
    """Another replica served the read: the model's batch after the
    collaborator's means it worked on the collaborator's version."""
    await _collaborator_edit(fake, _SET_WEEK)
    await fake.append_batch(
        "s-1",
        BaseRef("template", FORM_KEY),
        [{"op": "set_text", "address": "T1.R1.C3", "text": "x"}],
        Writer(user_id="u-1"),
        expected_count=1,
    )
    tools = _tools(form_bytes)
    content, artifact = await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T1.R1.C1", "text": "y"}]
    )
    assert artifact.is_error is False, content


def test_an_undo_then_an_edit_of_the_same_length_is_still_a_change():
    # The model read a log of two batches; the collaborator undid #2 and saved
    # their own #2: same length, other content.
    first = [{"op": "set_text", "address": "P1", "text": "a"}]
    read = [first, [{"op": "set_text", "address": "P2", "text": "model"}]]
    now = [
        BatchRecord(1, "model", first),
        BatchRecord(2, "collaborator", [{"op": "remove", "from": "P3"}]),
    ]
    assert _changed_under_the_model(now, log_mark(read))
    assert not _changed_under_the_model(now, log_mark([r.operations for r in now]))


@pytest.mark.asyncio
async def test_the_model_never_undoes_the_collaborators_edit(form_bytes, fake):
    tools = _tools(form_bytes)
    await tools["read_template"].coroutine(part="1")
    await fake.append_batch(
        "s-1",
        BaseRef("template", FORM_KEY),
        [{"op": "set_text", "address": "T1.R1.C2", "text": "mine"}],
        Writer("u-1"),
        expected_count=0,
        author="collaborator",
    )
    content, _ = await tools["undo_last_edit"].coroutine()
    assert "collaborator's own" in content
    assert len(fake.batches["s-1"]) == 1


@pytest.mark.asyncio
async def test_choosing_a_base_while_the_document_is_edited_changes_nothing(
    form_bytes, fake, monkeypatch
):
    tools = _tools(form_bytes)
    await fake.put_attachment(
        "s-1", "other.docx", content_sha256(form_bytes), form_bytes
    )

    async def conflict(*_args, **_kwargs):
        raise BatchConflict("s-1")

    monkeypatch.setattr(fake, "select_base", conflict)
    content, _ = await tools["use_attached_document"].coroutine(attachment="doc1")
    assert content.startswith("Nothing changed")
