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

"""The prompt command descriptor on its way from the request to the turn.

It reaches the runtime as a plain dict, because `RuntimeContext` is
`model_dump()`ed into the internal context before the turn is assembled. It
decides rendering only, so a malformed one must degrade to an ordinary text
turn rather than fail the turn.
"""

from fred_core.history.history_schema import CommandDescriptor
from fred_runtime.app.agent_app import _turn_command
from fred_sdk.contracts.context import RuntimeContext, TurnCommand


def test_a_dumped_runtime_context_carries_the_descriptor() -> None:
    context = RuntimeContext(
        session_id="s-1",
        command=TurnCommand(
            command="summary",
            appended_text="33 lignes",
            prompt_id="p-1",
            prompt_name="Revue hebdo",
        ),
    )

    descriptor = _turn_command(context.model_dump(mode="json"))

    assert descriptor is not None
    assert descriptor.command == "summary"
    assert descriptor.appended_text == "33 lignes"
    assert descriptor.prompt_id == "p-1"
    assert descriptor.prompt_name == "Revue hebdo"


def test_an_ordinary_turn_carries_no_descriptor() -> None:
    assert (
        _turn_command(RuntimeContext(session_id="s-1").model_dump(mode="json")) is None
    )
    assert _turn_command({}) is None


def test_a_malformed_descriptor_degrades_instead_of_failing() -> None:
    """Anything a client can put there must leave the turn storable."""

    for junk in ["oops", 42, [], {"nope": 1}, {"command": None}]:
        assert _turn_command({"command": junk}) is None


def test_the_descriptor_is_not_part_of_what_the_model_reads() -> None:
    """The agent receives the assembled text; commands never reach it."""

    from fred_core.history.history_schema import TextPart, make_user_text

    text = "Résume le document : 33 lignes"
    turn = make_user_text(
        "s-1", "e-1", 1, text, command=CommandDescriptor(command="summary")
    )

    texts = [part.text for part in turn.parts if isinstance(part, TextPart)]
    assert texts == [text]
    assert "summary" not in "".join(texts)


def _prompt(index: int = 0, **overrides: object) -> dict[str, object]:
    return {
        "command": f"cmd{index}",
        "prompt_id": f"p-{index}",
        "prompt_name": f"Prompt {index}",
        "draft_offset": index * 10,
        "text_offset": index * 50,
        "text_length": 40,
        **overrides,
    }


def test_every_prompt_of_the_turn_reaches_the_descriptor() -> None:
    prompts = [_prompt(0), _prompt(1)]
    context = RuntimeContext.model_validate(
        {
            "session_id": "s-1",
            "command": {
                "command": "cmd0",
                "prompt_id": "p-0",
                "prompt_name": "Prompt 0",
                "draft_text": "/cmd0 and /cmd1",
                "draft_command_offset": 0,
                "prompts": prompts,
            },
        }
    )

    # Same dump as `RuntimeExecuteRequest.to_legacy_context()`.
    descriptor = _turn_command(context.model_dump(exclude_none=True))

    assert descriptor is not None
    assert descriptor.prompts is not None
    assert [entry.model_dump() for entry in descriptor.prompts] == prompts
    # The single fields keep naming the first prompt for older readers.
    assert descriptor.command == "cmd0"
    assert descriptor.prompt_id == "p-0"
    assert descriptor.draft_command_offset == 0


def test_a_malformed_prompts_list_drops_the_whole_descriptor() -> None:
    for prompts in (
        "oops",
        [],
        [{"command": "summary"}],
        [_prompt(text_length=0)],
        [_prompt(index) for index in range(17)],
    ):
        assert (
            _turn_command({"command": {"command": "summary", "prompts": prompts}})
            is None
        )


def test_the_request_and_stored_models_share_one_bound() -> None:
    """Two packages, two constants: a list one accepts the other must too."""

    import pytest
    from pydantic import ValidationError

    for count, accepted in ((16, True), (17, False)):
        payload = {
            "command": "cmd0",
            "prompts": [_prompt(index) for index in range(count)],
        }
        for model in (TurnCommand, CommandDescriptor):
            if accepted:
                model.model_validate(payload)
            else:
                with pytest.raises(ValidationError):
                    model.model_validate(payload)


def test_the_stored_text_is_the_request_text_unchanged() -> None:
    """The listed offsets point into the stored text, so it must not move."""

    import asyncio
    from unittest.mock import AsyncMock

    from fred_runtime.app.agent_app import _write_turn_history

    store = AsyncMock()
    store.next_rank = AsyncMock(return_value=0)
    store.save = AsyncMock()
    text = "  Avant \U0001f600\n\nR\u00e9sume le document.\n\napr\u00e8s  \n"
    descriptor = _turn_command({"command": {"command": "cmd0", "prompts": [_prompt()]}})

    asyncio.run(
        _write_turn_history(
            session_id="s1",
            user_id="alice",
            request_message=text,
            turn_command=descriptor,
            payloads=[{"kind": "final", "content": "ok"}],
            history_store=store,
        )
    )

    user_row = store.save.call_args.kwargs["messages"][0]
    assert user_row.parts[0].text == text
    assert user_row.metadata.command is not None
    assert user_row.metadata.command.prompts is not None
    assert user_row.metadata.command.prompts[0].command == "cmd0"
