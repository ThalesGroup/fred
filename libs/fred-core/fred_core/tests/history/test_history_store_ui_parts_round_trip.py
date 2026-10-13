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

"""
Offline unit test: a turn's chat parts survive the metadata JSON column.

The bug this guards (RUNTIME-EXECUTION-CONTRACT.md §8.59) was "the runtime
emitted them and nothing wrote them down". Asserting on the in-memory message
would not catch a regression on the write/read path itself - a stricter dump, a
validator, or the read-side fallback swallowing the row - each of which
reproduces the original symptom: text back, cards gone.
"""

from __future__ import annotations

import pytest
from fred_core.history.history_schema import (
    ChatMetadata,
    CommandDescriptor,
    CommandPromptDescriptor,
    make_assistant_final,
    make_user_text,
)
from fred_core.history.postgres_history_store import (
    PostgresHistoryStore,
    create_history_schema,
)
from sqlalchemy.ext.asyncio import create_async_engine

DECK = {
    "type": "ppt_preview",
    "preview_id": "p1",
    "title": "Q3 review",
    "version": "v1",
    "nested": {"slides": [1, 2, 3], "author": None},
}


async def _store(tmp_path) -> PostgresHistoryStore:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'history.sqlite3'}")
    # The store never creates its own tables (Alembic owns that DDL).
    await create_history_schema(engine)
    return PostgresHistoryStore(engine)


@pytest.mark.asyncio
async def test_ui_parts_survive_a_save_and_read_back(tmp_path) -> None:
    store = await _store(tmp_path)

    await store.save(
        session_id="s1",
        messages=[
            make_user_text("s1", "e1", 0, "make me a deck"),
            make_assistant_final("s1", "e1", 1, "Here it is.", ui_parts=[DECK]),
        ],
        user_id="u1",
    )

    final = (await store.get("s1", user_id="u1"))[-1]
    assert final.metadata.ui_parts == [DECK], (
        "the stored card must come back whole, nested values and explicit nulls included"
    )


@pytest.mark.asyncio
async def test_a_turn_with_no_ui_parts_reads_back_as_an_empty_list(tmp_path) -> None:
    store = await _store(tmp_path)

    await store.save(
        session_id="s1",
        messages=[make_assistant_final("s1", "e1", 0, "Just text.")],
        user_id="u1",
    )

    final = (await store.get("s1", user_id="u1"))[-1]
    # Never None: every consumer iterates this field.
    assert final.metadata.ui_parts == []


def _prompt(index: int) -> dict[str, object]:
    return {
        "command": f"cmd{index}",
        "prompt_id": f"p-{index}",
        "prompt_name": f"Prompt {index}",
        "draft_offset": index * 10,
        "text_offset": index * 50,
        "text_length": 40,
    }


@pytest.mark.asyncio
async def test_a_descriptor_listing_two_prompts_survives_a_save_and_read_back(
    tmp_path,
) -> None:
    store = await _store(tmp_path)
    prompts = [_prompt(0), _prompt(1)]
    command = CommandDescriptor.model_validate(
        {"command": "cmd0", "prompt_id": "p-0", "prompts": prompts}
    )

    await store.save(
        session_id="s1",
        messages=[make_user_text("s1", "e1", 0, "assembled text", command=command)],
        user_id="u1",
    )

    stored = (await store.get("s1", user_id="u1"))[0].metadata.command
    assert stored is not None and stored.prompts is not None
    assert [entry.model_dump() for entry in stored.prompts] == prompts


@pytest.mark.asyncio
async def test_a_stored_list_over_the_bound_reads_back_without_failing(
    tmp_path,
) -> None:
    """A row written by a laxer writer degrades to an ordinary text turn."""

    store = await _store(tmp_path)
    # Built without validation, as an older package would have stored it.
    command = CommandDescriptor.model_construct(
        command="cmd0",
        prompts=[
            CommandPromptDescriptor.model_validate(_prompt(index))
            for index in range(17)
        ],
    )
    message = make_user_text("s1", "e1", 0, "assembled text")
    message.metadata = ChatMetadata.model_construct(command=command)

    await store.save(session_id="s1", messages=[message], user_id="u1")

    row = (await store.get("s1", user_id="u1"))[0]
    assert row.metadata.command is None
    assert [part.model_dump()["text"] for part in row.parts] == ["assembled text"]
