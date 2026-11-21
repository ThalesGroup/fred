"""Word templates are analysed once by the shared preparation worker."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import cast
from uuid import uuid4

import pytest
from conftest import form_document, report_document, to_bytes
from fred_capability_word_template.capability import WordTemplateCapability
from fred_capability_word_template.config import (
    WordTemplateConfig,
    WordTemplateEntry,
    resolve_library,
)
from fred_capability_word_template.documents import Documents
from fred_capability_word_template.store import (
    BaseRef,
    SqlWordTemplateStore,
    WordTemplateBase,
    clear_store_provider,
    set_store_provider,
)
from fred_capability_word_template.store import (
    Writer as SessionWriter,
)
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
    SaveContext,
)
from fred_sdk.contracts.capability.preparation import (
    PreparationAsset,
    PreparationContext,
    PreparationWork,
)
from fred_sdk.contracts.runtime import RuntimeServices
from port_fakes import FakeWordTemplateStore
from pydantic import JsonValue
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture(autouse=True)
def direct_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    async def direct(function, *args):
        return function(*args)

    monkeypatch.setattr(asyncio, "to_thread", direct)


@pytest.mark.asyncio
async def test_prepare_two_templates_and_read_published_analysis() -> None:
    contents = [to_bytes(form_document()), to_bytes(report_document())]
    hashes = [hashlib.sha256(content).hexdigest() for content in contents]
    assets = [
        PreparationAsset(
            asset_id=uuid4(),
            slot_key="word_template_library",
            filename=f"template-{index}.docx",
            sha256=sha,
            size=len(content),
        )
        for index, (sha, content) in enumerate(zip(hashes, contents))
    ]
    blobs = {asset.asset_id: content for asset, content in zip(assets, contents)}
    artifacts: dict[str, bytes] = {}
    calls: list[str] = []

    class Reader:
        async def read(self, asset_id):
            return blobs[asset_id]

    class Writer:
        async def write(self, path, content):
            artifacts[path] = content

        async def read(self, path):
            return artifacts[path]

        async def delete(self, path):
            artifacts.pop(path, None)

    class Text:
        async def complete(self, system, user):
            assert "Word document template" in system
            calls.append(user)
            return json.dumps({"summary": "A report template.", "parts": []})

    work = PreparationWork(
        preparation_id=uuid4(),
        owner_kind="agent",
        owner_id="agent-1",
        runtime_id="runtime",
        capability_id="word_template",
        input_revision="revision",
        rules_version="1",
        attempt=1,
        assets=tuple(assets),
        config=cast(dict[str, JsonValue], {"preparation_hashes": hashes}),
    )
    capability = WordTemplateCapability()
    writer = Writer()
    results = await asyncio.gather(
        *[
            capability.prepare(
                PreparationContext(
                    work=work.model_copy(
                        update={
                            "assets": (asset,),
                            "config": {"preparation_hashes": [sha]},
                        }
                    ),
                    assets=Reader(),
                    artifacts=writer,
                    text=Text(),
                )
            )
            for asset, sha in zip(assets, hashes)
        ]
    )
    result = await capability.combine_preparations(
        PreparationContext(work=work, assets=Reader(), artifacts=writer, text=Text()),
        results,
    )
    duplicate_labels = work.model_copy(
        update={
            "owner_kind": "platform",
            "config": {
                "preparation_hashes": hashes,
                "template_labels": ["Report", "report"],
            },
        }
    )
    with pytest.raises(ValueError, match="labels"):
        await capability.combine_preparations(
            PreparationContext(
                work=duplicate_labels, assets=Reader(), artifacts=writer, text=Text()
            ),
            results,
        )
    assert len(calls) == 2
    assert set(json.loads(artifacts[result.reference])) == set(hashes)
    assert all(
        artifacts[result.reference.rpartition("/")[0] + f"/template-{sha}.docx"]
        == content
        for sha, content in zip(hashes, contents)
    )


@pytest.mark.asyncio
async def test_platform_template_is_available_when_agent_has_no_library() -> None:
    fake_store = FakeWordTemplateStore()
    set_store_provider(lambda: fake_store)
    try:
        await _check_platform_template(fake_store)
    finally:
        clear_store_provider()


async def _check_platform_template(fake_store: FakeWordTemplateStore) -> None:
    contents = [to_bytes(form_document()), to_bytes(report_document())]
    hashes = [hashlib.sha256(content).hexdigest() for content in contents]
    key = "word_template:platform:word_template_library"

    class Prepared:
        def has_result(self, capability_id):
            return capability_id == key

        def settings(self, capability_id):
            assert capability_id == key
            return {
                "preparation_hashes": hashes,
                "template_labels": ["Weekly report", "Monthly report"],
            }

        async def read_result(self, capability_id):
            assert capability_id == key
            return json.dumps(
                {
                    sha: {"summary": label + "."}
                    for sha, label in zip(hashes, ["Weekly report", "Monthly report"])
                }
            ).encode()

        async def read_sibling(self, capability_id, filename):
            assert capability_id == key
            return contents[
                hashes.index(filename.removeprefix("template-").removesuffix(".docx"))
            ]

    ctx = CapabilityContext(
        identity=CapabilityIdentity(
            user_id="u", team_id="t", agent_instance_id="a", session_id="s"
        ),
        config=WordTemplateConfig(),
        turn_options=EmptyModel(),
        services=RuntimeServices(
            preparation_artifacts=Prepared(),
            preparation_enabled_capabilities=("word_template",),
        ),
    )
    docs = Documents(ctx)
    assert len(docs.library) == 2
    assert docs.library[0].label == "Weekly report"
    assert docs.library[1].label == "Monthly report"
    assert await docs._fetch_template(str(docs.library[0].template_key)) == contents[0]
    assert await docs._fetch_template(str(docs.library[1].template_key)) == contents[1]
    prepared = await docs.prepared_analysis(docs.library[0])
    assert prepared is not None and prepared.summary == "Weekly report."
    assert hashes[0] in fake_store.analyses
    previous = str(docs.library[1].template_key)
    previous_content = contents[1]
    await fake_store.select_base(
        "s",
        BaseRef("template", previous),
        SessionWriter(user_id="u", team_id="t", agent_instance_id="a"),
        expected_count=0,
        base_content=previous_content,
    )
    hashes[1] = hashes[0]
    contents[1] = contents[0]
    duplicate_docs = Documents(ctx)
    assert (
        duplicate_docs.library[0].template_key != duplicate_docs.library[1].template_key
    )
    active = await duplicate_docs.active()
    assert active is not None and active.base.ref == previous
    assert await duplicate_docs._fetch_template(previous) == previous_content


@pytest.mark.asyncio
async def test_agent_library_rejects_more_than_eight_templates() -> None:
    entries = [WordTemplateEntry(label=f"Template {index}") for index in range(9)]
    with pytest.raises(ValueError, match="at most 8"):
        await resolve_library(entries, [], cast(SaveContext, None))


@pytest.mark.asyncio
async def test_selected_platform_base_is_persisted_across_store_instances() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(WordTemplateBase.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        store = SqlWordTemplateStore(sessions)
        writer = SessionWriter(user_id="u", team_id="t", agent_instance_id="a")
        original = to_bytes(form_document())
        key = f"platform:0:{hashlib.sha256(original).hexdigest()}"
        await store.select_base(
            "session-1",
            BaseRef("template", key),
            writer,
            expected_count=0,
            base_content=original,
        )
        another_store = SqlWordTemplateStore(sessions)
        assert await another_store.get_base_content("session-1", key) == original
        assert (
            await another_store.get_base_content("session-1", "platform:1:new") is None
        )
    finally:
        await engine.dispose()
