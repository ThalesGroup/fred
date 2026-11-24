"""Word preparation replays a CP receipt and fences retirement in PostgreSQL."""

from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest
from conftest import form_document, to_bytes
from fred_capability_word_template import preparation
from fred_sdk.contracts.capability.preparation import (
    PreparationContext,
    PreparationWork,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
@pytest.mark.integration
async def test_preparation_replays_and_retirement_refuses_late_attempts() -> None:
    url = os.environ.get("FRED_WORD_TEMPLATE_TEST_POSTGRES_URL")
    if not url:
        pytest.skip(
            "Set FRED_WORD_TEMPLATE_TEST_POSTGRES_URL for PostgreSQL verification"
        )
    schema = f"word_preparation_{uuid4().hex}"
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    content = to_bytes(form_document())
    objects: dict[str, bytes] = {}

    class Objects:
        async def check(self):
            pass

        async def read(self, path):
            return objects[path]

        async def write(self, path, data):
            objects[path] = data

        async def delete(self, path):
            for key in list(objects):
                if key.startswith(path):
                    objects.pop(key)

    class Text:
        calls = 0

        async def complete(self, system, user):
            self.calls += 1
            return '{"summary":"A report template.","parts":[]}'

    model = Text()
    preparation.bind_objects(Objects())
    work = PreparationWork(
        preparation_id=uuid4(),
        installation_id=uuid4(),
        runtime_id="pod",
        capability_id="word_template",
        space_id=uuid4(),
        agent_instance_id=uuid4(),
        configuration_revision=1,
        file_id=uuid4(),
        sha256=hashlib.sha256(content).hexdigest(),
        filename="template.docx",
        size=len(content),
        config={},
        state="pending",
    )
    context = PreparationContext(
        work=work, database=engine, content=content, text=model
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                preparation.WordTemplatePreparation.metadata.create_all
            )
        first = await preparation.prepare(context)
        second = await preparation.prepare(context)
        assert first.reference == second.reference == str(work.preparation_id)
        assert model.calls == 1
        assert list(objects.values()) == [content]
        await preparation.retire(context)
        assert objects == {}
        with pytest.raises(ValueError, match="retired"):
            await preparation.prepare(context)
        async with async_sessionmaker(engine)() as session:
            row = await session.scalar(select(preparation.WordTemplatePreparation))
            assert row is not None and row.state == "retired" and row.analysis is None
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()
