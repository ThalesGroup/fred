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
