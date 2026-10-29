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

"""The word_template capability: registration, validate_config, the four
tools and the middleware's prompt fragments, all offline (fake store, fake
assets, fake chat model)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from typing import cast

import pytest
from conftest import form_document, report_document, to_bytes
from docx import Document
from fred_capability_word_template import check as check_module
from fred_capability_word_template import documents as documents_module
from fred_capability_word_template import middleware as middleware_module
from fred_capability_word_template import session_document
from fred_capability_word_template import store as store_module
from fred_capability_word_template import tools as tools_module
from fred_capability_word_template.analysis import TemplateAnalysis
from fred_capability_word_template.capability import (
    WordTemplateCapability,
)
from fred_capability_word_template.check import (
    CheckBasis,
    touched_checks,
)
from fred_capability_word_template.config import (
    TEMPLATE_LIBRARY_SLOT,
    WordTemplateConfig,
    WordTemplateEntry,
)
from fred_capability_word_template.docmap import build_map
from fred_capability_word_template.documents import (
    written_body_addresses,
)
from fred_capability_word_template.middleware import (
    WordTemplateMiddleware,
)
from fred_capability_word_template.operations import apply_batch, replay
from fred_capability_word_template.prompt import (
    ENGINE_PRINCIPLES,
)
from fred_capability_word_template.session_document import content_sha256
from fred_capability_word_template.store import WORD_TEMPLATE_ASSET_PREFIX, BaseRef
from fred_runtime.capabilities.registry import CapabilityRegistry
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
    HitlGateRequest,
    SaveContext,
    UploadedFile,
    asset_keys,
    unclassified_reference_fields,
)
from fred_sdk.contracts.runtime import RunStopError, RuntimeServices
from langchain.agents.middleware.types import ModelResponse
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from port_fakes import FakeAssets, FakeWordTemplateStore

FORM_KEY = "word_template.docx.form"
OTHER_KEY = "word_template.docx.other"


@pytest.fixture(autouse=True)
def _clean_caches() -> Iterator[None]:
    documents_module._BASES.clear()
    documents_module._STATES.clear()
    middleware_module._ANALYSIS_FAILURES.clear()
    middleware_module._ANALYSIS_LOCKS.clear()
    documents_module.SEEN.clear()
    documents_module._TEMPLATE_SHAPES.clear()
    middleware_module.PREFLIGHT.clear()
    check_module.CHECKS.clear()
    check_module._CHECK_BASES.clear()
    yield


@pytest.fixture()
def fake_store() -> Iterator[FakeWordTemplateStore]:
    fake = FakeWordTemplateStore()
    store_module.set_store_provider(lambda: fake)
    try:
        yield fake
    finally:
        store_module.clear_store_provider()


@pytest.fixture()
def assets(form_bytes, report_bytes) -> FakeAssets:
    return FakeAssets({FORM_KEY: form_bytes, OTHER_KEY: report_bytes})


def _library(*keys: str) -> list[WordTemplateEntry]:
    labels = {FORM_KEY: "Weekly report", OTHER_KEY: "Project report"}
    return [WordTemplateEntry(template_key=k, label=labels[k]) for k in keys]


def _ctx(
    assets, library, session_id: str | None = "s-1", metrics=None
) -> CapabilityContext:
    return CapabilityContext(
        identity=CapabilityIdentity(
            user_id="u-1",
            session_id=session_id,
            team_id="team-1",
            agent_instance_id="agent-1",
        ),
        config=WordTemplateConfig(template_library=library),
        turn_options=EmptyModel(),
        services=RuntimeServices(agent_assets=assets, metrics=metrics),
    )


def _tools(assets, library, session_id: str | None = "s-1") -> dict:
    tools = WordTemplateCapability().tools(_ctx(assets, library, session_id))
    return {t.name: t for t in tools}


# --- registration -----------------------------------------------------------------


def test_capability_registers_and_validates_clean():
    registry = CapabilityRegistry()
    registry.register(WordTemplateCapability())
    registry.validate()
    assert "word_template" in registry.ids()


def test_owned_tables_are_prefixed_without_foreign_keys():
    tables = [t.__table__ for t in WordTemplateCapability.manifest.tables]
    assert sorted(t.name for t in tables) == [
        "cap_word_template_analyses",
        "cap_word_template_attachments",
        "cap_word_template_batches",
        "cap_word_template_images",
        "cap_word_template_sessions",
        "cap_word_template_snapshots",
    ]
    assert all(not t.foreign_keys for t in tables)


def test_manifest_shape():
    manifest = WordTemplateCapability.manifest
    assert manifest.icon == "description"
    assert [a.key for a in manifest.assets] == [TEMPLATE_LIBRARY_SLOT]
    assert manifest.assets[0].accepted_types == [".docx"]
    assert manifest.assets[0].max_count is None
    assert manifest.router is not None
    # The guards and prompt fragments are ReAct middleware: ReAct only.
    assert manifest.execution_models == ("react",)


# --- validate_config --------------------------------------------------------------


def _save_ctx(assets) -> SaveContext:
    return SaveContext(
        identity=CapabilityIdentity(user_id="u-1", team_id="team-1"),
        services=RuntimeServices(agent_assets=assets),
    )


@pytest.mark.asyncio
async def test_validate_config_stores_blob_prefills_label_and_parts(form_bytes):
    assets = FakeAssets()
    config = WordTemplateConfig(template_library=[WordTemplateEntry()])
    result = await WordTemplateCapability().validate_config(
        config,
        {
            TEMPLATE_LIBRARY_SLOT: [
                UploadedFile(filename="Weekly_report 2026.docx", content=form_bytes)
            ]
        },
        _save_ctx(assets),
    )
    assert result.template_library is not None
    entry = result.template_library[0]
    assert entry.label == "Weekly report 2026"
    assert entry.template_key and entry.template_key.startswith(
        WORD_TEMPLATE_ASSET_PREFIX
    )
    assert assets.blobs[entry.template_key] == form_bytes
    assert "part 1:" in entry.parts_summary and "part hf" in entry.parts_summary
    # No chat model on the save path: the analysis runs on first use.
    assert entry.analysis is None
    assert "PK" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_validate_config_rejects_unreadable_docx_and_stores_nothing(form_bytes):
    assets = FakeAssets()
    config = WordTemplateConfig(
        template_library=[WordTemplateEntry(label="A"), WordTemplateEntry(label="B")]
    )
    with pytest.raises(ValueError, match="broken.docx"):
        await WordTemplateCapability().validate_config(
            config,
            {
                TEMPLATE_LIBRARY_SLOT: [
                    UploadedFile(filename="good.docx", content=form_bytes),
                    UploadedFile(filename="broken.docx", content=b"not a zip"),
                ]
            },
            _save_ctx(assets),
        )
    assert assets.store_calls == []


@pytest.mark.asyncio
async def test_validate_config_count_mismatch_and_duplicate_names(form_bytes):
    capability = WordTemplateCapability()
    with pytest.raises(ValueError, match="1 new template"):
        await capability.validate_config(
            WordTemplateConfig(template_library=[WordTemplateEntry(label="A")]),
            {},
            _save_ctx(FakeAssets()),
        )
    with pytest.raises(ValueError, match="more than once"):
        await capability.validate_config(
            WordTemplateConfig(
                template_library=[
                    WordTemplateEntry(template_key="k1", label="Rapport"),
                    WordTemplateEntry(label="rapport"),
                ]
            ),
            {
                TEMPLATE_LIBRARY_SLOT: [
                    UploadedFile(filename="x.docx", content=form_bytes)
                ]
            },
            _save_ctx(FakeAssets()),
        )


def test_settings_are_scope_classified():
    """The fred-agents guard (test_capability_scope_classification.py)."""
    for model in (WordTemplateConfig, WordTemplateCapability.StoredConfigModel):
        assert unclassified_reference_fields(model) == []
    stored = WordTemplateConfig(
        template_library=[WordTemplateEntry(template_key="k1.docx", label="A")]
    )
    assert asset_keys(stored) == {TEMPLATE_LIBRARY_SLOT: ["k1.docx"]}


@pytest.mark.asyncio
async def test_validate_config_restores_a_copied_library(form_bytes):
    """An agent copy re-submits each stored file, in order, with no new
    entry: each is stored again for the new instance, name and analysis kept."""
    assets = FakeAssets()
    analysis = TemplateAnalysis(summary="A form.")
    stored = WordTemplateConfig(
        template_library=[
            WordTemplateEntry(template_key="old-a.docx", label="A", analysis=analysis),
            WordTemplateEntry(template_key="old-b.docx", label="B"),
        ]
    )
    result = await WordTemplateCapability().validate_config(
        stored,
        {
            TEMPLATE_LIBRARY_SLOT: [
                UploadedFile(filename="old-a.docx", content=form_bytes),
                UploadedFile(filename="old-b.docx", content=form_bytes),
            ]
        },
        _save_ctx(assets),
    )
    assert result.template_library is not None
    keys = [e.template_key for e in result.template_library]
    assert [e.label for e in result.template_library] == ["A", "B"]
    assert all(
        k and k.endswith(".docx") and k.startswith("word_template.") for k in keys
    )
    assert not {"old-a.docx", "old-b.docx"} & set(keys)
    assert all(assets.blobs[k] == form_bytes for k in keys if k)
    assert result.template_library[0].analysis == analysis
    assert result.template_library[1].analysis is None


@pytest.mark.asyncio
async def test_validate_config_without_library_passes_through():
    config = WordTemplateConfig()
    result = await WordTemplateCapability().validate_config(
        config, {}, _save_ctx(FakeAssets())
    )
    assert result.template_library is None


# --- tools ----------------------------------------------------------------------------


def test_select_template_only_with_several_templates(assets):
    assert set(_tools(assets, _library(FORM_KEY))) == {
        "read_template",
        "edit_document",
        "undo_last_edit",
        "remove_unused_template_parts",
        "use_attached_document",
    }
    assert "select_template" in _tools(assets, _library(FORM_KEY, OTHER_KEY))


@pytest.mark.asyncio
async def test_read_template_returns_the_part_with_addresses(assets, fake_store):
    tools = _tools(assets, _library(FORM_KEY))
    content, artifact = await tools["read_template"].coroutine(part="1")
    assert artifact.is_error is False
    assert "[T1] table" in content and "Week 10" in content
    content, artifact = await tools["read_template"].coroutine(part="hf")
    assert "Footer text" in content
    content, artifact = await tools["read_template"].coroutine(part="1, hf")
    assert content.startswith("Part 1 (current state):")
    assert "\n\nPart hf (current state):" in content and "Footer text" in content
    content, artifact = await tools["read_template"].coroutine(part="9")
    assert artifact.is_error is False
    assert "is not a part id" in content and "part 1:" in content


@pytest.mark.asyncio
async def test_edit_document_applies_pins_and_returns_the_updated_part(
    assets, fake_store
):
    tools = _tools(assets, _library(FORM_KEY))
    content, artifact = await tools["edit_document"].coroutine(
        operations=[
            {"op": "set_text", "address": "T1.R1.C2", "text": "Week 41"},
            {"op": "repeat", "from": "T2.R2", "count": 1},
        ]
    )
    assert artifact.is_error is False, content
    assert "edit #1" in content
    assert "Week 41" in content
    assert "Parts now:" in content  # repeat is structural
    state = fake_store.sessions["s-1"]
    assert state.template_key == FORM_KEY and state.pinned_at is not None
    assert state.team_id == "team-1" and state.agent_instance_id == "agent-1"
    assert fake_store.batches["s-1"] == [
        [
            {"op": "set_text", "address": "T1.R1.C2", "text": "Week 41"},
            {"op": "repeat", "from": "T2.R2", "count": 1},
        ]
    ]
    # The next read sees template + log.
    content, _ = await tools["read_template"].coroutine(part="1")
    assert "Week 41" in content and "[T2] table, 5 rows" in content


@pytest.mark.asyncio
async def test_edit_document_rejects_a_bad_batch_and_stores_nothing(assets, fake_store):
    tools = _tools(assets, _library(FORM_KEY))
    content, artifact = await tools["edit_document"].coroutine(
        operations=[
            {"op": "set_text", "address": "T9.R1.C1", "text": "x"},
            {"op": "replace_text", "address": "F1", "find": "absent", "replace": "y"},
            {"op": "explode", "address": "P1"},
        ]
    )
    assert artifact.is_error is False
    assert "Nothing was applied" in content
    assert "'T9.R1.C1' does not exist" in content
    assert "'absent' is not in 'F1'" in content
    assert "operation 3: invalid" in content
    assert "s-1" not in fake_store.batches or fake_store.batches["s-1"] == []
    assert "s-1" not in fake_store.sessions


@pytest.mark.asyncio
async def test_edit_document_keeps_a_copy_of_each_template_block(assets, fake_store):
    tools = _tools(assets, _library(FORM_KEY))
    # The template's only project block cannot go, rebuilt or not.
    content, artifact = await tools["edit_document"].coroutine(
        operations=[{"op": "remove", "from": "T2"}]
    )
    assert artifact.is_error is False
    assert "keep at least one copy of this block" in content
    assert "s-1" not in fake_store.batches or fake_store.batches["s-1"] == []
    # Repeat it, then remove the extra copy: allowed.
    content, artifact = await tools["edit_document"].coroutine(
        operations=[{"op": "repeat", "from": "T2", "count": 1}]
    )
    assert artifact.is_error is False, content
    content, artifact = await tools["edit_document"].coroutine(
        operations=[{"op": "remove", "from": "T3"}]
    )
    assert artifact.is_error is False, content


@pytest.mark.asyncio
async def test_edit_document_refuses_a_batch_built_on_a_stale_log(assets, fake_store):
    tools = _tools(assets, _library(FORM_KEY))
    # Another call appended a batch between this call's read and its write.
    original = fake_store.append_batch

    async def racing(*args, **kwargs):
        fake_store.batches.setdefault("s-1", []).append(
            [{"op": "remove", "from": "P1"}]
        )
        return await original(*args, **kwargs)

    fake_store.append_batch = racing  # type: ignore[method-assign]
    content, artifact = await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T1.R1.C2", "text": "x"}]
    )
    assert artifact.is_error is False
    assert "at the same time" in content


@pytest.mark.asyncio
async def test_undo_last_edit_drops_the_last_batch(assets, fake_store):
    tools = _tools(assets, _library(FORM_KEY))
    content, artifact = await tools["undo_last_edit"].coroutine()
    assert "Nothing to undo" in content and artifact.is_error is False
    await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T1.R1.C2", "text": "first"}]
    )
    await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T1.R1.C2", "text": "again"}]
    )
    content, _ = await tools["undo_last_edit"].coroutine()
    assert "Undone: set_text T1.R1.C2" in content
    read, _ = await tools["read_template"].coroutine(part="1")
    assert "first" in read and "again" not in read
    await tools["undo_last_edit"].coroutine()
    # Nothing left: the template is no longer pinned.
    assert fake_store.sessions["s-1"].pinned_at is None


@pytest.mark.asyncio
async def test_select_template_flow(assets, fake_store):
    tools = _tools(assets, _library(FORM_KEY, OTHER_KEY))
    content, artifact = await tools["read_template"].coroutine(part="1")
    assert artifact.is_error is False and "No template is selected" in content
    content, artifact = await tools["select_template"].coroutine(label="Nope")
    assert artifact.is_error is False and '"Weekly report"' in content
    content, artifact = await tools["select_template"].coroutine(label="weekly REPORT")
    assert artifact.is_error is False
    assert fake_store.sessions["s-1"].template_key == FORM_KEY
    await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T1.R1.C2", "text": "x"}]
    )
    content, artifact = await tools["select_template"].coroutine(label="Project report")
    assert artifact.is_error is False and "new conversation" in content
    assert fake_store.sessions["s-1"].template_key == FORM_KEY


@pytest.mark.asyncio
async def test_tools_without_session_fail_loud(assets, fake_store):
    tools = _tools(assets, _library(FORM_KEY), session_id=None)
    content, artifact = await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T1.R1.C2", "text": "x"}]
    )
    assert artifact.is_error is True and "No active session" in content


# --- middleware -----------------------------------------------------------------------


class _FakeRequest:
    def __init__(self, model=None, system_prompt: str | None = "AGENT PROMPT") -> None:
        self.model = model
        self.system_prompt = system_prompt
        self.overridden: SystemMessage | None = None

    def override(self, *, system_message: SystemMessage) -> _FakeRequest:
        self.overridden = system_message
        return self


async def _overlay(assets, library, model=None) -> str:
    middleware = WordTemplateMiddleware(_ctx(assets, library))
    request = _FakeRequest(model=model)

    async def handler(req):
        return req

    result = cast(
        _FakeRequest,
        await middleware.awrap_model_call(request, handler),  # type: ignore[arg-type]
    )
    assert result.overridden is not None
    text = str(result.overridden.content)
    assert text.startswith("AGENT PROMPT\n\n")
    return text


_ANALYSIS = {
    "summary": "A weekly report: a title table and one block per project.",
    "parts": [
        {
            "title": "Title",
            "addresses": "T1",
            "purpose": "report period",
            "elements": [{"address": "T1.R1.C2", "role": "fill", "note": "week"}],
        }
    ],
    "repeatable_blocks": [{"addresses": "T2", "one_per": "project"}],
}


@pytest.mark.asyncio
async def test_middleware_without_library_nor_attachment(assets, fake_store):
    text = await _overlay(assets, [])
    assert "no template configured and no Word file was attached" in text
    assert "attach the Word (.docx) file" in text
    assert ENGINE_PRINCIPLES not in text


@pytest.mark.asyncio
async def test_middleware_selection_fragment_until_a_template_is_selected(
    assets, fake_store
):
    library = [
        WordTemplateEntry(
            template_key=FORM_KEY,
            label="Weekly report",
            parts_summary="part 1: Weekly report (T1–P2, 3 elements)\npart hf: headers and footers (H1–F1, 2 elements)",
        ),
        WordTemplateEntry(template_key=OTHER_KEY, label="Project report"),
    ]
    text = await _overlay(assets, library)
    assert "none is selected" in text
    assert '- "Weekly report"' in text and "Parts: Weekly report" in text
    assert ENGINE_PRINCIPLES not in text
    assert "explicit yes" in text


@pytest.mark.asyncio
async def test_middleware_runs_the_analysis_on_first_use_and_caches_it(
    assets, fake_store, form_bytes
):
    model = FakeListChatModel(responses=["```json\n" + json.dumps(_ANALYSIS) + "\n```"])
    text = await _overlay(assets, _library(FORM_KEY), model=model)
    assert ENGINE_PRINCIPLES in text
    assert "A weekly report" in text and "fill: T1.R1.C2 (week)" in text
    assert "- T2: one per project" in text
    assert "DOCUMENT PARTS" in text and "part 1:" in text
    assert "nothing edited yet" in text
    # Keyed by the sha256 of the base's bytes, not by the asset key.
    assert set(fake_store.analyses) == {content_sha256(form_bytes)}
    assert TemplateAnalysis.model_validate_json(
        fake_store.analyses[content_sha256(form_bytes)]
    )
    # Cached: a model with no answer left is never called again.
    exhausted = FakeListChatModel(responses=[])
    again = await _overlay(assets, _library(FORM_KEY), model=exhausted)
    assert "A weekly report" in again


@pytest.mark.asyncio
async def test_middleware_falls_back_to_the_map_when_the_analysis_fails(
    assets, fake_store
):
    model = FakeListChatModel(responses=["sorry, no JSON here"])
    text = await _overlay(assets, _library(FORM_KEY), model=model)
    assert "No analysis of this template is available" in text
    assert not fake_store.analyses
    # Not retried on the next call (failure remembered for a while).
    text = await _overlay(
        assets, _library(FORM_KEY), model=FakeListChatModel(responses=[])
    )
    assert "No analysis of this template is available" in text


@pytest.mark.asyncio
async def test_middleware_uses_an_analysis_stored_in_the_config(assets, fake_store):
    library = [
        WordTemplateEntry(
            template_key=FORM_KEY,
            label="Weekly report",
            analysis=TemplateAnalysis.model_validate(_ANALYSIS),
        )
    ]
    text = await _overlay(assets, library)
    assert "A weekly report" in text


@pytest.mark.asyncio
async def test_middleware_lists_what_was_done(assets, fake_store):
    tools = _tools(assets, _library(FORM_KEY))
    await tools["edit_document"].coroutine(
        operations=[
            {"op": "replace_text", "address": "F1", "find": "Footer", "replace": "Pied"}
        ]
    )
    text = await _overlay(assets, _library(FORM_KEY))
    assert "batch 1 (you): replace_text F1" in text


def test_form_fixture_is_still_the_reference():
    # The tool tests rely on this fixture shape (see conftest.form_document).
    assert b"word/document.xml" in to_bytes(form_document())


# --- first-use analysis: single flight, timeout, KPI ------------------------------------


class _SlowModel:
    """A chat model double that counts its calls and answers after a delay."""

    model_name = "fake-model"

    def __init__(self, answer: str, delay: float = 0.05) -> None:
        self.answer = answer
        self.delay = delay
        self.calls = 0

    async def ainvoke(self, messages, config=None):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return AIMessage(content=self.answer)


class _FakeMetrics:
    def __init__(self) -> None:
        self.timers: list[tuple[str, dict, str]] = []

    @contextmanager
    def timer(self, name, *, dims=None):
        outcome = "ok"
        try:
            yield dict(dims or {})
        except BaseException:
            outcome = "error"
            raise
        finally:
            self.timers.append((name, dict(dims or {}), outcome))


def _form_active() -> documents_module.Active:
    return documents_module.Active(BaseRef("template", FORM_KEY), "Weekly report")


@pytest.mark.asyncio
async def test_concurrent_first_turns_run_one_analysis(assets, fake_store):
    model = _SlowModel(json.dumps(_ANALYSIS))
    metrics = _FakeMetrics()
    first, second = (
        WordTemplateMiddleware(_ctx(assets, _library(FORM_KEY), metrics=metrics))
        for _ in range(2)
    )
    results = await asyncio.gather(
        first._analysis(_form_active(), model),
        second._analysis(_form_active(), model),
    )
    assert model.calls == 1
    assert all(r is not None and "A weekly report" in r.summary for r in results)
    assert len(fake_store.analyses) == 1
    # The analysis call is timed on the canonical LLM latency metric.
    assert metrics.timers == [
        (
            "llm.call_latency_ms",
            {
                "agent_id": "agent-1",
                "operation": "word_template_analysis",
                "model_name": "fake-model",
            },
            "ok",
        )
    ]


@pytest.mark.asyncio
async def test_analysis_timeout_falls_back_and_backs_off(
    assets, fake_store, monkeypatch
):
    monkeypatch.setattr(middleware_module, "_ANALYSIS_TIMEOUT_SECONDS", 0.01)
    metrics = _FakeMetrics()
    middleware = WordTemplateMiddleware(
        _ctx(assets, _library(FORM_KEY), metrics=metrics)
    )
    slow = _SlowModel(json.dumps(_ANALYSIS), delay=5.0)
    assert await middleware._analysis(_form_active(), slow) is None
    assert len(middleware_module._ANALYSIS_FAILURES) == 1
    assert not fake_store.analyses
    assert metrics.timers[0][2] == "error"
    # Backoff: the next turn does not call the model again.
    fast = _SlowModel(json.dumps(_ANALYSIS), delay=0)
    assert await middleware._analysis(_form_active(), fast) is None
    assert fast.calls == 0


# --- persisted document snapshot ------------------------------------------------------


@pytest.fixture()
def replay_spy(monkeypatch) -> list[tuple[bytes, int]]:
    """Records every replay (its base document, its batch count)."""
    calls: list[tuple[bytes, int]] = []
    original = session_document.replay

    def spy(base, batches, *args, **kwargs):
        calls.append((base, len(batches)))
        return original(base, batches, *args, **kwargs)

    monkeypatch.setattr(session_document, "replay", spy)
    return calls


async def _two_edits(tools, fake_store):
    await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T1.R1.C2", "text": "first"}]
    )
    after_first = fake_store.snapshots["s-1"]
    await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T1.R1.C3", "text": "edit-two"}]
    )
    return after_first


def _forget_pod_caches() -> None:
    documents_module._STATES.clear()
    documents_module._BASES.clear()


@pytest.mark.asyncio
async def test_edit_stores_a_snapshot_that_spares_the_replay(
    assets, fake_store, replay_spy
):
    tools = _tools(assets, _library(FORM_KEY))
    await _two_edits(tools, fake_store)
    assert fake_store.snapshots["s-1"].seq == 2
    _forget_pod_caches()  # as on another replica
    fetches = len(assets.fetch_calls)
    content, _ = await tools["read_template"].coroutine(part="1")
    assert "first" in content and "edit-two" in content
    assert replay_spy == []
    # The template is fetched once, for the texts shown whole in a read (in a
    # turn the prompt's document check has already fetched it).
    assert len(assets.fetch_calls) == fetches + 1


@pytest.mark.asyncio
async def test_a_stale_snapshot_replays_only_the_later_batches(
    assets, fake_store, replay_spy
):
    tools = _tools(assets, _library(FORM_KEY))
    after_first = await _two_edits(tools, fake_store)
    fake_store.snapshots["s-1"] = after_first  # e.g. the latest write was lost
    _forget_pod_caches()
    content, _ = await tools["read_template"].coroutine(part="1")
    assert "first" in content and "edit-two" in content
    assert replay_spy == [(after_first.docx, 1)]
    assert fake_store.snapshots["s-1"].seq == 2  # written back


@pytest.mark.asyncio
async def test_a_missing_or_foreign_snapshot_replays_the_whole_log(
    assets, fake_store, replay_spy, form_bytes
):
    tools = _tools(assets, _library(FORM_KEY))
    await _two_edits(tools, fake_store)
    fake_store.snapshots.clear()
    _forget_pod_caches()
    content, _ = await tools["read_template"].coroutine(part="1")
    assert "first" in content and "edit-two" in content
    assert replay_spy == [(form_bytes, 2)]
    # A snapshot built from another log (same seq, other digest) is ignored.
    good = fake_store.snapshots["s-1"]
    fake_store.snapshots["s-1"] = store_module.Snapshot(
        seq=good.seq, digest="other", docx=b"not this"
    )
    _forget_pod_caches()
    content, _ = await tools["read_template"].coroutine(part="1")
    assert "first" in content and "edit-two" in content
    assert replay_spy[-1] == (form_bytes, 2)


@pytest.mark.asyncio
async def test_undo_replaces_the_snapshot(assets, fake_store, replay_spy):
    tools = _tools(assets, _library(FORM_KEY))
    after_first = await _two_edits(tools, fake_store)
    await tools["undo_last_edit"].coroutine()
    snapshot = fake_store.snapshots["s-1"]
    assert (snapshot.seq, snapshot.digest) == (after_first.seq, after_first.digest)
    _forget_pod_caches()
    replay_spy.clear()
    content, _ = await tools["read_template"].coroutine(part="1")
    assert "first" in content and "edit-two" not in content
    assert replay_spy == []
    # Undoing the last edit leaves no snapshot behind.
    await tools["undo_last_edit"].coroutine()
    assert "s-1" not in fake_store.snapshots


# --- guards: engine rules, one edit per step, no tool message in the answer ----------


def test_principles_state_one_edit_at_a_time_and_keeping_the_structure():
    text = " ".join(ENGINE_PRINCIPLES.split())
    assert "One edit_document call at a time" in text
    assert "Never send several edits in the same step" in text
    assert "never remove every copy of a block" in text
    assert "undo it with undo_last_edit" in text


def _call(call_id: str, name: str = "edit_document") -> dict:
    return {"id": call_id, "name": name, "args": {}, "type": "tool_call"}


async def _run_tool_call(middleware, state, call):
    executed: list[str] = []

    async def handler(req):
        executed.append(req.tool_call["id"])
        return ToolMessage(content="ran", tool_call_id=req.tool_call["id"])

    request = SimpleNamespace(tool_call=call, state=state)
    result = await middleware.awrap_tool_call(request, handler)  # type: ignore[arg-type]
    return result, executed


def _read_result(call_id: str = "r0", parts: tuple[str, ...] = ("1",)) -> list:
    return [
        AIMessage(content="", tool_calls=[_call(call_id, "read_template")]),
        ToolMessage(
            "\n\n".join(f"Part {p} (current state):\n[P1] ..." for p in parts),
            tool_call_id=call_id,
            name="read_template",
        ),
    ]


@pytest.mark.asyncio
async def test_only_the_first_edit_of_a_step_runs(assets, fake_store):
    middleware = WordTemplateMiddleware(_ctx(assets, _library(FORM_KEY)))
    step = AIMessage(
        content="",
        tool_calls=[
            _call("r1", "read_template"),
            _call("e1"),
            _call("e2"),
            _call("e3"),
        ],
    )
    state = {"messages": [HumanMessage("go"), *_read_result(), step]}
    for call_id, name in (("r1", "read_template"), ("e1", "edit_document")):
        result, executed = await _run_tool_call(middleware, state, _call(call_id, name))
        assert executed == [call_id] and result.content == "ran"
    for call_id in ("e2", "e3"):
        result, executed = await _run_tool_call(middleware, state, _call(call_id))
        assert executed == []
        assert isinstance(result, ToolMessage)
        assert result.tool_call_id == call_id and result.name == "edit_document"
        # Not an error: the runtime would show it instead of the model's answer.
        assert result.status == "success" and result.artifact is None
        assert "only one edit_document at a time" in str(result.content)


@pytest.mark.asyncio
async def test_a_single_edit_or_an_unknown_call_runs(assets, fake_store):
    middleware = WordTemplateMiddleware(_ctx(assets, _library(FORM_KEY)))
    earlier = AIMessage(content="", tool_calls=[_call("e0"), _call("e1")])
    later = AIMessage(content="", tool_calls=[_call("e2")])
    state = {
        "messages": [
            *_read_result(),
            earlier,
            ToolMessage("x", tool_call_id="e0"),
            later,
        ]
    }
    _result, executed = await _run_tool_call(middleware, state, _call("e2"))
    assert executed == ["e2"]
    _result, executed = await _run_tool_call(middleware, {"messages": []}, _call("e9"))
    assert executed == ["e9"]


@pytest.mark.asyncio
async def test_an_edit_needs_a_read_since_the_base_was_chosen(assets, fake_store):
    middleware = WordTemplateMiddleware(_ctx(assets, _library(FORM_KEY)))
    select = [
        AIMessage(content="", tool_calls=[_call("s1", "select_template")]),
        ToolMessage(
            'Template "Form" selected for this session. Read the parts ...',
            tool_call_id="s1",
            name="select_template",
        ),
    ]
    edit = AIMessage(content="", tool_calls=[_call("e1")])

    # Never read: refused, as a plain result the model reads.
    result, executed = await _run_tool_call(
        middleware, {"messages": [HumanMessage("go"), *select, edit]}, _call("e1")
    )
    assert executed == [] and result.status == "success"
    assert "read before you edit" in str(result.content)

    # Read before the base changed: refused too.
    state = {"messages": [*_read_result(), *select, edit]}
    _result, executed = await _run_tool_call(middleware, state, _call("e1"))
    assert executed == []

    # A read in the same step had not run when the edit was planned.
    same_step = AIMessage(
        content="", tool_calls=[_call("r1", "read_template"), _call("e1")]
    )
    state = {"messages": [*select, same_step]}
    _result, executed = await _run_tool_call(middleware, state, _call("e1"))
    assert executed == []

    # Read (or an applied edit, whose reply shows the part) after the choice: runs.
    for shown in (
        _read_result("r2"),
        [
            ToolMessage(
                "Applied 1 operation(s) as edit #1.\n\nPart 1 now:\n[P1] ...",
                tool_call_id="x",
                name="edit_document",
            )
        ],
    ):
        state = {"messages": [*select, *shown, edit]}
        _result, executed = await _run_tool_call(middleware, state, _call("e1"))
        assert executed == ["e1"]


@pytest.mark.asyncio
async def test_an_edit_after_shifted_addresses_needs_a_new_read(assets, fake_store):
    # The report: part 1 = "Context" (P4-P6), part 2 = "Scope" (P7-T1).
    middleware = WordTemplateMiddleware(_ctx(assets, _library(OTHER_KEY)))
    # The engine's real reply to a structural edit, not a hand-written copy.
    tools = _tools(assets, _library(OTHER_KEY), session_id="s-2")
    await tools["read_template"].coroutine(part="1")
    reply, _ = await tools["edit_document"].coroutine(
        operations=[{"op": "write", "from": "P5", "to": "P6", "markdown": "A\n\nB"}]
    )
    assert reply.startswith("Applied") and "have shifted" in reply
    assert "Part 1 now:" in reply
    shifted = ToolMessage(reply, tool_call_id="w1", name="edit_document")
    undone = ToolMessage(
        "Undone: write P5–P6.", tool_call_id="u1", name="undo_last_edit"
    )
    read_both = _read_result(parts=("1", "2"))

    async def run(messages, call):
        step = AIMessage(content="", tool_calls=[call])
        return await _run_tool_call(middleware, {"messages": [*messages, step]}, call)

    in_part_1 = _edit_call("e1", {"op": "set_text", "address": "P4", "text": "x"})
    in_part_2 = _edit_call("e2", {"op": "set_text", "address": "P8", "text": "x"})
    # The reply shows part 1 as it is now: an edit there runs; part 2 was
    # read before the change, so its addresses may have moved.
    _r, executed = await run([*read_both, shifted], in_part_1)
    assert executed == ["e1"]
    result, executed = await run([*read_both, shifted], in_part_2)
    assert executed == [] and "read before you edit. part 2 has" in str(result.content)
    # An undo shows no part: everything is read again.
    result, executed = await run([*read_both, undone], in_part_1)
    assert executed == [] and "read before you edit" in str(result.content)
    _r, executed = await run([*read_both, undone, *_read_result("r2")], in_part_1)
    assert executed == ["e1"]


@pytest.mark.asyncio
async def test_the_model_undoes_on_its_own_only_this_turn_s_edits(assets, fake_store):
    middleware = WordTemplateMiddleware(_ctx(assets, _library(FORM_KEY)))

    async def undo(messages, args=None):
        call = {**_call("u1", "undo_last_edit"), "args": args or {}}
        step = AIMessage(content="", tool_calls=[call])
        state = {"messages": [HumanMessage("go"), *messages, step]}
        return await _run_tool_call(middleware, state, call)

    # Only a refused batch in this turn: nothing to repair, nothing undone.
    refused = [
        AIMessage(content="", tool_calls=[_call("e1")]),
        ToolMessage("Nothing was applied. Fix...", tool_call_id="e1"),
    ]
    result, executed = await undo(refused)
    assert executed == [] and "Nothing undone" in str(result.content)
    # The collaborator asked (the approval gate confirms it): runs.
    _r, executed = await undo(refused, {"collaborator_asked": True})
    assert executed == ["u1"]
    # An edit applied in this turn: the model may undo it, once.
    applied = [
        AIMessage(content="", tool_calls=[_call("e2")]),
        ToolMessage("Applied 1 operation(s) as edit #3.", tool_call_id="e2"),
    ]
    _r, executed = await undo(applied)
    assert executed == ["u1"]
    undone = [
        AIMessage(content="", tool_calls=[_call("u0", "undo_last_edit")]),
        ToolMessage("Undone: write P5.", tool_call_id="u0"),
    ]
    _r, executed = await undo([*applied, *undone])
    assert executed == []


def _edit_call(call_id: str, *operations: dict) -> dict:
    return {
        "id": call_id,
        "name": "edit_document",
        "args": {"operations": list(operations)},
        "type": "tool_call",
    }


def _write(start: str, end: str) -> dict:
    return {"op": "write", "from": start, "to": end, "markdown": "Text."}


@pytest.mark.asyncio
async def test_written_content_goes_into_one_part_per_turn(assets, fake_store):
    # The report: part 2 = "Context" (P4–P6), part 3 = "Scope" (P7–T1).
    middleware = WordTemplateMiddleware(_ctx(assets, _library(OTHER_KEY)))
    read = _read_result(parts=("0", "1", "2"))

    async def run(messages, call):
        step = AIMessage(content="", tool_calls=[call])
        return await _run_tool_call(middleware, {"messages": [*messages, step]}, call)

    # One part: runs. Two parts in one batch: refused.
    _r, executed = await run(
        [HumanMessage("go"), *read], _edit_call("a", _write("P5", "P6"))
    )
    assert executed == ["a"]
    result, executed = await run(
        [HumanMessage("go"), *read],
        _edit_call("b", _write("P5", "P6"), _write("P8", "P8")),
    )
    assert executed == [] and "one part per turn" in str(result.content)

    # A part already written in this turn: the same part again runs, another
    # part is refused, until the collaborator answers.
    first = AIMessage(content="", tool_calls=[_edit_call("w1", _write("P5", "P6"))])
    applied = ToolMessage(
        'Applied 1 operation(s) as edit #1.\n\nPart 1 now:\n[P4 heading 1] "Context"',
        tool_call_id="w1",
        name="edit_document",
    )
    turn = [
        HumanMessage("go"),
        *read,
        first,
        applied,
        *_read_result("r2", ("0", "1", "2")),
    ]
    _r, executed = await run(turn, _edit_call("c", _write("P5", "P5")))
    assert executed == ["c"]
    result, executed = await run(turn, _edit_call("d", _write("P8", "P8")))
    assert executed == [] and "one part per turn" in str(result.content)
    _r, executed = await run(
        [*turn, HumanMessage("ok, next")], _edit_call("e", _write("P8", "P8"))
    )
    assert executed == ["e"]

    # Filling fields or cells is never limited.
    fill = _edit_call(
        "f",
        {"op": "set_text", "address": "P1", "text": "x"},
        {"op": "set_text", "address": "T1.R1.C1", "text": "y"},
    )
    _r, executed = await run(turn, fill)
    assert executed == ["f"]


@pytest.mark.asyncio
async def test_fixed_wording_is_kept_unless_the_change_is_declared(assets, fake_store):
    # The report's "Fixed sentence." (P6) is fixed wording per the analysis.
    analysis = TemplateAnalysis.model_validate(
        {
            "summary": "A report.",
            "parts": [
                {
                    "title": "Context",
                    "addresses": "P4–P6",
                    "elements": [
                        {"address": "P5", "role": "replace"},
                        {"address": "P6", "role": "fixed"},
                    ],
                }
            ],
        }
    )
    entry = WordTemplateEntry(
        template_key=OTHER_KEY, label="Project report", analysis=analysis
    )
    middleware = WordTemplateMiddleware(_ctx(assets, [entry]))

    async def run(call):
        step = AIMessage(content="", tool_calls=[call])
        state = {"messages": [HumanMessage("go"), *_read_result(), step]}
        return await _run_tool_call(middleware, state, call)

    # Rewriting the fixed sentence: refused, with the way to ask for it.
    result, executed = await run(_edit_call("a", _write("P5", "P6")))
    assert executed == [] and "changes_template" in str(result.content)
    result, executed = await run(
        _edit_call("b", {"op": "set_text", "address": "P6", "text": "Other."})
    )
    assert executed == []
    # The guidance next to it, a detail inside it, or a declared change: run.
    for call_id, op in (
        ("c", _write("P5", "P5")),
        (
            "d",
            {"op": "replace_text", "address": "P6", "find": "Fixed", "replace": "Set"},
        ),
    ):
        _r, executed = await run(_edit_call(call_id, op))
        assert executed == [call_id]
    declared = _edit_call("e", _write("P5", "P6"))
    declared["args"]["changes_template"] = True
    _r, executed = await run(declared)
    assert executed == ["e"]


class _EchoRequest:
    def __init__(self, messages, system_prompt: str = "AGENT PROMPT") -> None:
        self.model = None
        self.system_prompt = system_prompt
        self.messages = messages
        self.system_message: SystemMessage | None = None

    def override(self, *, system_message: SystemMessage) -> _EchoRequest:
        clone = _EchoRequest(self.messages, self.system_prompt)
        clone.system_message = system_message
        return clone


_ECHO = (
    "Nothing was applied. Fix these problems and send the whole batch again:\n"
    "- operation 1 (write): 'P1' does not exist (the document has tables T1)"
)


async def _answer_with(assets, drafts, messages=None, key=FORM_KEY):
    middleware = WordTemplateMiddleware(_ctx(assets, _library(key)))
    prompts: list[str] = []
    queue = list(drafts)

    async def handler(req):
        prompts.append(str(req.system_message.content))
        return ModelResponse(result=[queue.pop(0)])

    request = _EchoRequest(messages or [HumanMessage("Remplis le document")])
    result = await middleware.awrap_model_call(request, handler)  # type: ignore[arg-type]
    return result, prompts


@pytest.mark.asyncio
async def test_a_clean_answer_is_returned_after_one_call(assets, fake_store):
    result, prompts = await _answer_with(assets, [AIMessage("Le document est rempli.")])
    assert len(prompts) == 1 and result.result[0].content == "Le document est rempli."


@pytest.mark.asyncio
async def test_the_document_check_is_in_the_prompt_and_in_edit_replies(
    assets, fake_store
):
    # The report's chapter 1 still holds its blue guidance.
    _result, prompts = await _answer_with(assets, [AIMessage("ok")], key=OTHER_KEY)
    assert "DOCUMENT CHECK (from the document itself, not from memory):" in prompts[0]
    assert '- part 1 ("Context"): 1 place(s) left' in prompts[0]
    tools = _tools(assets, _library(OTHER_KEY))
    await tools["read_template"].coroutine(part="1")
    reply, _artifact = await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "P5", "text": "Written."}]
    )
    assert 'CHECK of part 1 ("Context"): finished.' in reply
    _result, prompts = await _answer_with(assets, [AIMessage("ok")], key=OTHER_KEY)
    assert "every part is finished" in prompts[0]


@pytest.mark.asyncio
async def test_an_edit_reply_lists_the_places_left_in_the_part(assets, fake_store):
    tools = _tools(assets, _library(OTHER_KEY))
    await tools["read_template"].coroutine(part="1")
    reply, _artifact = await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "P6", "text": "Other fixed."}],
        changes_template=True,
    )
    assert 'CHECK of part 1 ("Context"): 1 place(s) left.' in reply
    assert '- template text still in place: under "Context" - P5' in reply


@pytest.mark.asyncio
async def test_an_echoed_tool_message_is_answered_again(assets, fake_store):
    result, prompts = await _answer_with(
        assets, [AIMessage(_ECHO), AIMessage("J'ai rempli les trois projets.")]
    )
    assert len(prompts) == 2
    assert "repeated an internal tool message" not in prompts[0]
    assert "repeated an internal tool message" in prompts[1]
    assert result.result[0].content == "J'ai rempli les trois projets."


@pytest.mark.asyncio
async def test_a_second_echo_becomes_a_neutral_sentence(assets, fake_store):
    echo = AIMessage("Applied 2 operation(s) as edit #3.", id="m-1")
    result, prompts = await _answer_with(assets, [AIMessage(_ECHO), echo])
    assert len(prompts) == 2
    final = result.result[0]
    assert final.id == "m-1" and "aperçu du document" in str(final.content)
    english, _ = await _answer_with(
        assets,
        [AIMessage(_ECHO), AIMessage(_ECHO)],
        [HumanMessage("Please fill in the report with the projects you have")],
    )
    assert str(english.result[0].content).startswith("I could not write my answer")
    undetermined, _ = await _answer_with(
        assets, [AIMessage(_ECHO), AIMessage(_ECHO)], [HumanMessage("OK")]
    )
    assert str(undetermined.result[0].content).startswith("I could not write my answer")


@pytest.mark.asyncio
async def test_tool_calls_are_never_checked_for_echoes(assets, fake_store):
    step = AIMessage(_ECHO, tool_calls=[_call("r1", "read_template")])
    result, prompts = await _answer_with(assets, [step])
    assert len(prompts) == 1 and result.result[0] is step


# --- checks of a planned step: refused before it runs, no unsaved claim -------------


def _planned(call_id: str, *operations: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[_edit_call(call_id, *operations)])


_MISSING = {"op": "remove", "from": "P99", "to": "P99"}


@pytest.mark.asyncio
async def test_a_planned_edit_the_engine_refuses_is_planned_again(assets, fake_store):
    # Read, then a removal of a paragraph the report does not have.
    messages = [HumanMessage("Remplis le contexte"), *_read_result()]
    fixed = _planned("p2", {"op": "set_text", "address": "P5", "text": "Written."})
    result, prompts = await _answer_with(
        assets, [_planned("p1", _MISSING), fixed], messages, key=OTHER_KEY
    )
    assert len(prompts) == 2 and result.result[0] is fixed
    assert "NOTE: your previous step was not run" in prompts[1]
    assert "'P99' does not exist" in prompts[1]


@pytest.mark.asyncio
async def test_another_part_after_the_replan_ends_the_turn_with_the_answer(
    assets, fake_store
):
    # Part 1 ("Context", P4-P6) written in this turn; the model then plans
    # part 2 ("Scope", P7-T1) twice: the third call ends the turn.
    written = _planned("w1", _write("P5", "P6"))
    applied = ToolMessage(
        'Applied 1 operation(s) as edit #1.\n\nPart 1 now:\n[P4 heading 1] "Context"',
        tool_call_id="w1",
        name="edit_document",
    )
    messages = [
        HumanMessage("Rédige tout"),
        *_read_result(parts=("1", "2")),
        written,
        applied,
    ]
    answer = AIMessage("Voici la partie 1 ; je passe à la suite après votre retour.")
    result, prompts = await _answer_with(
        assets,
        [
            _planned("p1", _write("P8", "P8")),
            _planned("p2", _write("P8", "P8")),
            answer,
            answer,
        ],
        messages,
        key=OTHER_KEY,
    )
    assert len(prompts) >= 3 and result.result[0] is answer
    assert "Make no other edit in this turn" in prompts[2]


@pytest.mark.asyncio
async def test_an_edit_still_refused_skips_the_approval_and_returns_its_refusal(
    assets, fake_store
):
    messages = [HumanMessage("Supprime ce paragraphe"), *_read_result()]
    planned = _planned("p1", _MISSING)
    result, prompts = await _answer_with(
        assets, [planned, planned], messages, key=OTHER_KEY
    )
    assert len(prompts) == 2 and result.result[0] is planned
    call = planned.tool_calls[0]
    # A removal is normally approved by the collaborator; not this one.
    gate = {s.tool: s for s in WordTemplateCapability().hitl_specs()}["edit_document"]
    context = _ctx(assets, _library(OTHER_KEY))
    assert gate.when is not None
    assert (
        gate.when(HitlGateRequest(tool_call=call, tool=None, context=context)) is False
    )
    middleware = WordTemplateMiddleware(context)
    state = {"messages": [*messages, planned]}
    refused, executed = await _run_tool_call(middleware, state, call)
    assert executed == [] and "'P99' does not exist" in str(refused.content)
    # Answered once: the same id planned again is checked again.
    assert (
        gate.when(HitlGateRequest(tool_call=call, tool=None, context=context)) is True
    )


@pytest.mark.asyncio
async def test_an_answer_after_an_unapplied_edit_is_asked_again(assets, fake_store):
    edit = _planned("e1", _write("P5", "P6"))
    refused = ToolMessage(
        "Not applied: written content goes into one part per turn.",
        tool_call_id="e1",
        name="edit_document",
    )
    claim = AIMessage("Le chapitre est à jour dans le document.")
    honest = AIMessage("Je n'ai pas pu enregistrer ce chapitre.")
    messages = [HumanMessage("continue"), *_read_result(), edit, refused]
    result, prompts = await _answer_with(assets, [claim, honest], messages)
    assert len(prompts) == 2 and result.result[0] is honest
    assert "was not applied (Not applied: written content" in prompts[1]
    # Applied, or before the collaborator's last message: answered at once.
    applied = ToolMessage(
        "Applied 1 operation(s) as edit #1.", tool_call_id="e1", name="edit_document"
    )
    for history in (
        [HumanMessage("go"), edit, applied],
        [HumanMessage("go"), edit, refused, HumanMessage("ok")],
    ):
        result, prompts = await _answer_with(assets, [claim], history)
        assert len(prompts) == 1 and result.result[0] is claim


@pytest.mark.asyncio
async def test_the_reply_of_written_content_says_to_show_it_before_another_part(
    assets, fake_store
):
    tools = _tools(assets, _library(OTHER_KEY))
    await tools["read_template"].coroutine(part="1")
    reply, _ = await tools["edit_document"].coroutine(
        operations=[{"op": "write", "from": "P5", "to": "P5", "markdown": "A\n\nB"}]
    )
    assert "Written content of this turn: part 1." in reply
    assert 'OUTLINE of chapter 1 now: "Context"; sub-headings: none' in reply
    filled, _ = await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "T1.R1.C1", "text": "x"}]
    )
    assert filled.startswith("Applied") and "Written content of this turn" not in filled


@pytest.mark.asyncio
async def test_a_new_heading_needs_the_collaborator_to_ask_for_it(assets, fake_store):
    tools = _tools(assets, _library(OTHER_KEY))
    await tools["read_template"].coroutine(part="1")
    for op in (
        {"op": "write", "from": "P5", "markdown": "### Planning\n\nText."},
        {"op": "set_text", "address": "P5", "text": "### Planning"},
    ):
        content, artifact = await tools["edit_document"].coroutine(operations=[op])
        assert artifact.is_error is False and "adds a heading" in content
    # No sub-heading level in this template: a numbered title loses its number.
    content, _ = await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "P5", "text": "**1.2 Costs**"}]
    )
    assert "write it without its number" in content
    assert fake_store.batches.get("s-1") in (None, [])
    content, _ = await tools["edit_document"].coroutine(
        operations=[{"op": "write", "from": "P5", "markdown": "### Planning\n\nText."}],
        changes_template=True,
    )
    assert content.startswith("Applied")


@pytest.mark.asyncio
async def test_sub_headings_of_a_level_the_template_uses_need_no_request(fake_store):
    document = report_document()
    document.add_heading("Annex detail", level=2)
    key = "word_template.docx.subheadings"
    assets = FakeAssets({key: to_bytes(document)})
    tools = _tools(assets, [WordTemplateEntry(template_key=key, label="Report")])
    await tools["read_template"].coroutine(part="1")

    async def edit(markdown: str) -> str:
        op = {"op": "write", "from": "P5", "markdown": markdown}
        content, _ = await tools["edit_document"].coroutine(operations=[op])
        return content

    refused = await edit("# Planning\n\nText.")
    assert "adds a heading" in refused and '"## "' in refused
    assert fake_store.batches.get("s-1") in (None, [])
    applied = await edit("## Costs\n\nText.")
    assert applied.startswith("Applied") and '[P5 heading 2] "Costs"' in applied
    # A title written as a bold line becomes a sub-heading too.
    await tools["read_template"].coroutine(part="1")
    bold = await edit("**Budget** :\n\nText.")
    assert bold.startswith("Applied") and '[P5 heading 2] "Budget"' in bold
    # A bold label introducing a list stays a bold line, not a sub-heading.
    await tools["read_template"].coroutine(part="1")
    label = await edit("**Goals** :\n- one\n- two\n\n**Risks** :\n- three")
    assert label.startswith("Applied") and "Goals" in label
    assert 'heading 2] "Goals' not in label
    # Siblings written alike: one is followed by text, so all are titles.
    await tools["read_template"].coroutine(part="1")
    siblings = await edit("**Background** :\n\nText.\n\n**Goals** :\n- one")
    assert 'heading 2] "Background"' in siblings and 'heading 2] "Goals"' in siblings
    # Numbered at two depths: the deeper one, with no level left, stays bold.
    await tools["read_template"].coroutine(part="1")
    nested = await edit("**1. Phase**\n\n### 1.1 Goals\n- one")
    assert '[P5 heading 2] "Phase"\n[P6] "Goals" {bold}' in nested
    # A title typed with its number as plain text becomes a sub-heading too.
    await tools["read_template"].coroutine(part="1")
    typed = await edit("2.1 Planning\n\nText.")
    assert typed.startswith("Applied") and 'heading 2] "' in typed
    # Deeper than the template's sub-headings: taken at their level, not refused.
    await tools["read_template"].coroutine(part="1")
    deeper = await edit("### Risks\n\nText.")
    assert deeper.startswith("Applied") and '[P5 heading 2] "Risks"' in deeper


@pytest.mark.asyncio
async def test_a_text_already_in_place_never_blocks_the_rest_of_the_batch(
    assets, fake_store
):
    tools = _tools(assets, _library(OTHER_KEY))
    await tools["read_template"].coroutine(part="1")
    same = {"op": "set_text", "address": "P4", "text": "Context"}
    alone, _ = await tools["edit_document"].coroutine(operations=[same])
    assert "already holds this text" in alone
    mixed, _ = await tools["edit_document"].coroutine(
        operations=[same, {"op": "write", "from": "P5", "markdown": "Written."}]
    )
    assert mixed.startswith("Applied 1 operation(s)")


@pytest.mark.asyncio
async def test_a_set_outline_gets_sub_chapters_only_with_approval(fake_store):
    # Real titles everywhere (a contract): "Context" has a sub-heading in
    # the template, "Scope" has none.
    document = Document()
    document.add_heading("Context", level=1)
    document.add_heading("Background", level=2)
    document.add_paragraph("Describe the background.")
    document.add_heading("Scope", level=1)
    document.add_paragraph("Describe the scope.")
    key = "word_template.docx.contract"
    analysis = TemplateAnalysis.model_validate(
        {
            "summary": "A contract.",
            "parts": [
                {
                    "title": "Context",
                    "addresses": "P1–P3",
                    "elements": [{"address": "P3", "role": "replace"}],
                },
                {
                    "title": "Scope",
                    "addresses": "P4–P5",
                    "elements": [{"address": "P5", "role": "replace"}],
                },
            ],
        }
    )
    entry = WordTemplateEntry(template_key=key, label="Contract", analysis=analysis)
    tools = _tools(FakeAssets({key: to_bytes(document)}), [entry])

    async def edit(start, markdown, changes_template=False):
        await tools["read_template"].coroutine(part="1, 2")
        op = {"op": "write", "from": start, "markdown": markdown}
        reply, _ = await tools["edit_document"].coroutine(
            operations=[op], changes_template=changes_template
        )
        return reply

    # The chapter with the template's sub-heading keeps it: a bold title.
    kept = await edit("P3", "**Risks**\n\nText.")
    assert kept.startswith("Applied") and '"Risks" {bold}' in kept
    # A heading line there is a sub-chapter to approve, never made bold silently.
    asked = await edit("P3", "## Stakes\n\nText.")
    assert "needs the collaborator's approval" in asked and '"Stakes"' in asked
    # The chapter without: sub-chapters are proposed, then approved.
    proposed = await edit("P6", "**Lots**\n\nText.")
    assert "needs the collaborator's approval" in proposed and '"Lots"' in proposed
    approved = await edit("P6", "**Lots**\n\nText.", changes_template=True)
    assert approved.startswith("Applied") and 'heading 2] "Lots"' in approved
    # Asked for, a sub-chapter joins the template's own too.
    added = await edit("P3", "## Extra\n\nText.", changes_template=True)
    assert added.startswith("Applied") and 'heading 2] "Extra"' in added


@pytest.mark.asyncio
async def test_a_map_note_is_never_written_as_text(assets, fake_store):
    tools = _tools(assets, _library(OTHER_KEY))
    await tools["read_template"].coroutine(part="1")
    reply, _ = await tools["edit_document"].coroutine(
        operations=[{"op": "set_text", "address": "P5", "text": "Describe it. {blue}"}]
    )
    assert '"{blue}" is a note of the document map' in reply


@pytest.mark.asyncio
async def test_unused_template_parts_are_removed_in_one_edit(
    assets, fake_store, report_bytes
):
    analysis = TemplateAnalysis.model_validate(
        {
            "summary": "A report.",
            "parts": [
                {
                    "title": "Context",
                    "addresses": "P4–P6",
                    "elements": [
                        {"address": "P5", "role": "replace"},
                        {"address": "P6", "role": "fixed"},
                    ],
                },
                {
                    "title": "Scope",
                    "addresses": "P7–T1",
                    "elements": [
                        {"address": "P7", "role": "fill"},
                        {"address": "P8", "role": "replace"},
                    ],
                },
            ],
        }
    )
    entry = WordTemplateEntry(template_key=OTHER_KEY, label="Report", analysis=analysis)
    tools = _tools(assets, [entry])
    await tools["read_template"].coroutine(part="1")
    await tools["edit_document"].coroutine(
        operations=[{"op": "write", "from": "P5", "markdown": "Our context."}]
    )
    reply, _ = await tools["remove_unused_template_parts"].coroutine()
    assert reply.startswith("Applied") and '"Scope" (heading and content)' in reply
    document = replay(report_bytes, await fake_store.list_batches("s-1"))
    texts = [e.text for e in build_map(document).elements]
    # The unused chapter goes with its table-of-contents line; the rest stays.
    assert "Scope" not in texts and "2 Scope" not in texts and "A" not in texts
    for kept in (
        "Our context.",
        "Fixed sentence.",
        "Annex",
        "Annex text.",
        "1 Context",
    ):
        assert kept in texts
    again, _ = await tools["remove_unused_template_parts"].coroutine()
    assert again.startswith("Nothing to remove")


@pytest.mark.asyncio
async def test_the_prompt_gives_today_s_date(assets, fake_store):
    _result, prompts = await _answer_with(assets, [AIMessage("ok")], key=OTHER_KEY)
    assert f"TODAY'S DATE: {date.today().isoformat()}" in prompts[0]


@pytest.mark.asyncio
async def test_an_answer_after_a_chapter_left_with_template_text_is_asked_again(
    assets, fake_store
):
    # Written in part 1 this turn, but its blue guidance (P5) is still there.
    edit = _planned("w1", _write("P6", "P6"))
    applied = ToolMessage(
        "Applied 1 operation(s) as edit #1.\n\nPart 1 now:\n[P4 heading 1] ...",
        tool_call_id="w1",
        name="edit_document",
    )
    claim = AIMessage("Le chapitre 1 est à jour dans le document.")
    honest = AIMessage("Le chapitre 1 garde une consigne du modèle.")
    messages = [HumanMessage("rédige le contexte"), edit, applied]
    result, prompts = await _answer_with(
        assets, [claim, honest], messages, key=OTHER_KEY
    )
    assert len(prompts) == 2 and result.result[0] is honest
    assert (
        "part 1, written in this turn, still holds text of the template" in prompts[1]
    )


def test_written_content_counts_by_chapter_not_by_piece():
    reply = (
        "Applied 1 operation(s) as edit #1.\n\nPart 5 now:\n...\n\nPart 5b now:\n..."
    )
    messages = [
        HumanMessage("go"),
        AIMessage(content="", tool_calls=[_edit_call("w1", _write("P9", "P9"))]),
        ToolMessage(reply, tool_call_id="w1", name="edit_document"),
    ]
    assert middleware_module._chapters_written_this_turn(
        {"messages": messages}, ""
    ) == {"5"}


def test_a_set_text_of_several_paragraphs_counts_as_written_content():
    # Written as a write, so the one-part-per-turn rule sees it.
    operations = [
        {"op": "set_text", "address": "P5", "text": "One.\n\nTwo."},
        {"op": "set_text", "address": "P9", "text": "A value"},
        {"op": "set_text", "address": "T1.R2.C1", "text": "One.\n\nTwo."},
    ]
    assert written_body_addresses(operations) == ["P5"]
    # "from_" is read as "from": no guard can be bypassed by the key's spelling.
    assert written_body_addresses(
        [{"op": "write", "from_": "P6", "markdown": "x"}]
    ) == ["P6"]


def test_after_a_removal_the_checked_part_is_named_by_its_title():
    docx = to_bytes(report_document())
    before = build_map(docx)
    after = build_map(apply_batch(docx, [{"op": "remove", "from": "P4", "to": "P6"}]))
    basis = CheckBasis(frozenset({"Scope instruction."}), frozenset(), {})
    (check,) = touched_checks(before, after, ["1"], basis)
    # "Context" is gone: the part now at its place is checked, by its title.
    assert check.startswith('CHECK of part 1 ("Scope"): 1 place(s) left.')


@pytest.mark.asyncio
async def test_a_store_failure_is_a_tool_result_and_a_run_stop_ends_the_run(
    assets, fake_store, monkeypatch
):
    tools = _tools(assets, _library(FORM_KEY))

    async def broken(_session_id):
        raise OSError("database unreachable")

    monkeypatch.setattr(fake_store, "list_batch_records", broken)
    content, artifact = await tools["read_template"].coroutine(part="1")
    assert artifact.is_error and "could not be loaded right now" in content

    async def stopped(_session_id):
        raise RuntimeError("wrapped") from RunStopError()

    monkeypatch.setattr(fake_store, "list_batch_records", stopped)
    with pytest.raises(RunStopError):
        await tools["read_template"].coroutine(part="1")


def test_an_applied_edit_always_gets_a_reply(monkeypatch):
    def broken(*_args, **_kwargs):
        raise ValueError("odd document")

    monkeypatch.setattr(tools_module, "_edit_reply", broken)
    reply = tools_module._edit_reply_safe(b"", b"", [{"op": "remove"}], 3)
    assert reply.startswith("Applied 1 operation(s) as edit #3.")
