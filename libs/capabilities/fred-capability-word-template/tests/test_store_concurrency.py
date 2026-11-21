"""Cross-pod document mutations must serialize on one session row."""

from __future__ import annotations

import asyncio
import json
import os
from uuid import uuid4

import pytest
from fred_capability_word_template.store import (
    AssetInUse,
    BaseRef,
    BatchConflict,
    SqlWordTemplateStore,
    WordTemplateBase,
    WordTemplateBatch,
    WordTemplateSession,
    Writer,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
@pytest.mark.integration
async def test_concurrent_session_mutations_recheck_under_the_row_lock() -> None:
    url = os.environ.get("FRED_WORD_TEMPLATE_TEST_POSTGRES_URL")
    if not url:
        pytest.skip(
            "Set FRED_WORD_TEMPLATE_TEST_POSTGRES_URL for PostgreSQL verification"
        )
    schema = f"word_concurrency_{uuid4().hex}"
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(WordTemplateBase.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        store = SqlWordTemplateStore(sessions)
        writer = Writer(user_id="user", team_id="team", agent_instance_id="agent")
        first = BaseRef("template", "first")
        second = BaseRef("template", "second")
        await store.select_base("session", first, writer, expected_count=0)

        async with sessions() as lock_session:
            async with lock_session.begin():
                row = await lock_session.scalar(
                    select(WordTemplateSession)
                    .where(WordTemplateSession.session_id == "session")
                    .with_for_update()
                )
                assert row is not None
                append = asyncio.create_task(
                    store.append_batch("session", first, [], writer, expected_count=0)
                )
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(append), 0.1)
                row.template_key = second.ref
        with pytest.raises(BatchConflict):
            await append
        selected = await store.get_session("session")
        assert selected is not None and selected.template_key == second.ref

        await store.append_batch("session", second, [], writer, expected_count=0)
        async with sessions() as lock_session:
            async with lock_session.begin():
                await lock_session.scalar(
                    select(WordTemplateSession.session_id)
                    .where(WordTemplateSession.session_id == "session")
                    .with_for_update()
                )
                undo = asyncio.create_task(
                    store.drop_last_batch("session", expected_count=1)
                )
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(undo), 0.1)
                lock_session.add(
                    WordTemplateBatch(
                        session_id="session", seq=2, operations="[]", author="model"
                    )
                )
        with pytest.raises(BatchConflict):
            await undo
        updated = await store.get_session("session")
        assert updated is not None and updated.batch_count == 2

        await store.select_base("attached", first, writer, expected_count=0)
        attachment = await store.put_attachment(
            "attached", "base.docx", "a" * 64, b"base"
        )
        async with sessions() as lock_session:
            async with lock_session.begin():
                row = await lock_session.scalar(
                    select(WordTemplateSession)
                    .where(WordTemplateSession.session_id == "attached")
                    .with_for_update()
                )
                assert row is not None
                removal = asyncio.create_task(
                    store.delete_attachment(
                        "attached", attachment.attachment_id, keep_image_ids=()
                    )
                )
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(removal), 0.1)
                row.attachment_id = attachment.attachment_id
        with pytest.raises(AssetInUse):
            await removal
        assert (
            await store.get_attachment_content("attached", attachment.attachment_id)
            == b"base"
        )

        await store.select_base("images", first, writer, expected_count=0)
        image = await store.put_image(
            "images",
            filename="chart.png",
            content_type="image/png",
            sha256="b" * 64,
            content=b"png",
        )
        async with sessions() as lock_session:
            async with lock_session.begin():
                await lock_session.scalar(
                    select(WordTemplateSession.session_id)
                    .where(WordTemplateSession.session_id == "images")
                    .with_for_update()
                )
                remove_image = asyncio.create_task(
                    store.delete_image("images", image.image_id)
                )
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(remove_image), 0.1)
                lock_session.add(
                    WordTemplateBatch(
                        session_id="images",
                        seq=1,
                        operations=json.dumps(
                            [
                                {
                                    "op": "write",
                                    "markdown": f"![Chart](img:{image.image_id})",
                                }
                            ]
                        ),
                        author="model",
                    )
                )
        with pytest.raises(AssetInUse):
            await remove_image
        assert (await store.get_image("images", image.image_id)) is not None
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()
