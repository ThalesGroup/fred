# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0

"""Check successful NUL normalization at the document and JSONB boundaries."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fred_capability_writable_document.capability import (
    WritableDocumentPart,
    save_writable_document,
)
from fred_capability_writable_document.store import (
    SqlWritableDocumentStore,
    WritableDocumentBase,
    clear_store_provider,
    set_store_provider,
)
from fred_core.history.history_schema import (
    make_assistant_final,
    make_tool_call,
    make_tool_result,
    make_user_text,
)
from fred_core.history.postgres_history_store import (
    PostgresHistoryStore,
    create_history_schema,
)
from fred_sdk.contracts.ui_part_union import rebuild_ui_part_union
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.integration_postgres]


@pytest.mark.asyncio
@pytest.mark.parametrize("only_nul", [False, True])
async def test_cleaned_document_and_original_arguments_are_durable(
    only_nul: bool,
) -> None:
    dsn = os.environ.get("FRED_PG_DSN")
    if not dsn:
        pytest.skip("Set FRED_PG_DSN to a local PostgreSQL test database")
    schema = f"fred_write_test_{uuid4().hex}"
    admin = create_async_engine(dsn)
    engine = create_async_engine(
        dsn, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await create_history_schema(engine)
        async with engine.begin() as connection:
            await connection.run_sync(WritableDocumentBase.metadata.create_all)
        documents = SqlWritableDocumentStore(
            async_sessionmaker(engine, expire_on_commit=False)
        )
        set_store_provider(lambda: documents)
        rebuild_ui_part_union([WritableDocumentPart])
        title = "\x00" if only_nul else "Ré\x00sumé"
        body = "\x00" * 107 if only_nul else "Décisions\n\t" + "\x00" * 107 + "東京"
        args = {"title": title, "content_markdown": body}
        content, artifact = await save_writable_document(
            session_id="s1", user_id="u1", **args
        )
        assert not artifact.is_error and artifact.blocks[0].text == content
        assert "title: 1" in content and "content_markdown: 107" in content
        part = artifact.ui_parts[0]
        assert isinstance(part, WritableDocumentPart)
        assert part.title == title.replace("\x00", "")
        assert part.content_md == body.replace("\x00", "")
        stored = await documents.get("s1", part.document_id)
        assert stored is not None and stored.content_md == part.content_md
        assert "[U+0000]" not in stored.content_md

        call = make_tool_call("s1", "e1", 1, "write-1", "write_document", args)
        messages = [
            make_user_text("s1", "e1", 0, "Write a report"),
            call,
            make_tool_result("s1", "e1", 2, "write-1", content),
            make_assistant_final("s1", "e1", 3, "The document was saved."),
        ]
        await PostgresHistoryStore(engine).save("s1", messages, "u1")
        await PostgresHistoryStore(engine).save("s1", messages, "u1")
        restored = await PostgresHistoryStore(engine).get("s1", "u1")
        assert len(restored) == 4
        assert restored[2].parts[0].model_dump()["call_id"] == "write-1"
        assert restored[2].parts[0].model_dump()["failure"] is None
        assert restored[1].parts[0].model_dump()["args"][
            "content_markdown"
        ] == body.replace("\x00", "[U+0000]")
        assert call.parts[0].model_dump()["args"] == args
    finally:
        clear_store_provider()
        rebuild_ui_part_union()
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()
