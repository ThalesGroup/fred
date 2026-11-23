# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0

"""Check invalid document-call history against PostgreSQL's actual JSONB rules.

Set FRED_PG_DSN to a local test database; only a disposable schema is touched.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

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

pytestmark = [pytest.mark.integration, pytest.mark.integration_postgres]


@pytest.mark.asyncio
async def test_rejected_document_turn_is_durable_and_idempotent() -> None:
    dsn = os.environ.get("FRED_PG_DSN")
    if not dsn:
        pytest.skip("Set FRED_PG_DSN to a local PostgreSQL test database")
    schema = f"fred_history_test_{uuid4().hex}"
    admin = create_async_engine(dsn)
    engine = create_async_engine(
        dsn, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await create_history_schema(engine)
        store = PostgresHistoryStore(engine)
        content = "Décisions\n\t" + "\x00" * 107 + "東京"
        call = make_tool_call(
            "s1",
            "e1",
            1,
            "write-1",
            "write_document",
            {"title": "Résumé", "content_markdown": content},
        )
        messages = [
            make_user_text("s1", "e1", 0, "Write a report"),
            call,
            make_tool_result(
                "s1", "e1", 2, "write-1", "INVALID_DOCUMENT_CONTENT", ok=False
            ),
            make_assistant_final("s1", "e1", 3, "The document was not saved."),
        ]
        await store.save("s1", messages, "u1")
        await store.save("s1", messages, "u1")

        reader = PostgresHistoryStore(engine)
        restored = await reader.get("s1", "u1")
        assert len(restored) == 4
        assert [message.rank for message in restored] == [0, 1, 2, 3]
        recorded = restored[1].parts[0].model_dump()
        assert recorded["call_id"] == "write-1"
        assert recorded["args"]["content_markdown"] == content.replace(
            "\x00", "[U+0000]"
        )
        assert (
            restored[1].metadata.model_dump()["history_text_normalization"]["count"]
            == 107
        )
        assert restored[2].parts[0].model_dump()["ok"] is False
        assert call.parts[0].model_dump()["args"]["content_markdown"] == content
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()
