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

from fred_core.history.history_schema import (
    ChatMessage,
    ChatMetadata,
    CommandDescriptor,
    HitlRequestPart,
    HitlResponsePart,
    make_hitl_request,
    make_hitl_response,
    make_user_text,
)


def test_hitl_builders_preserve_occurrence_and_separate_answer_text() -> None:
    request = make_hitl_request(
        "session-1",
        "exchange-1",
        1,
        question="Choose",
        choices=[{"id": "yes", "label": "Yes"}],
        interrupt_id="interrupt-shared",
        occurrence_id="tool-call-1",
    )
    response = make_hitl_response(
        "session-1",
        "exchange-1",
        2,
        choice_id="yes",
        text="With this constraint",
        occurrence_id="tool-call-1",
    )

    request_part = request.parts[0]
    response_part = response.parts[0]
    assert isinstance(request_part, HitlRequestPart)
    assert isinstance(response_part, HitlResponsePart)
    assert request_part.occurrence_id == "tool-call-1"
    assert response_part.occurrence_id == "tool-call-1"
    assert response_part.choice_id == "yes"
    assert response_part.text == "With this constraint"


def test_legacy_hitl_response_shape_remains_readable() -> None:
    response = HitlResponsePart.model_validate(
        {"type": "hitl_response", "choice_id": "legacy free text"}
    )

    assert response.choice_id == "legacy free text"
    assert response.text is None
    assert response.occurrence_id is None


def test_a_command_descriptor_changes_metadata_only() -> None:
    """The turn's content is the assembled text either way.

    History is replayed to the model, so a command turn must read to the
    model exactly like a turn the user typed by hand. The descriptor is side
    data.
    """

    text = "Résume le document et rédige une synthèse de : 33 lignes"
    plain = make_user_text("s-1", "e-1", 1, text)
    with_command = make_user_text(
        "s-1",
        "e-1",
        1,
        text,
        command=CommandDescriptor(
            command="summary",
            appended_text="33 lignes",
            prompt_id="p-1",
            prompt_name="Revue hebdo",
        ),
    )

    assert [part.model_dump() for part in plain.parts] == [
        part.model_dump() for part in with_command.parts
    ]
    assert plain.metadata.command is None
    assert with_command.metadata.command is not None
    assert with_command.metadata.command.command == "summary"
    assert with_command.metadata.command.appended_text == "33 lignes"
    assert with_command.metadata.command.prompt_name == "Revue hebdo"


def test_a_command_descriptor_round_trips_through_serialisation() -> None:
    message = make_user_text(
        "s-1", "e-1", 1, "text", command=CommandDescriptor(command="summary")
    )

    revived = ChatMessage.model_validate(message.model_dump(mode="json"))

    assert revived.metadata.command is not None
    assert revived.metadata.command.command == "summary"
    # Absent by default, so every turn written before this existed reads back
    # as an ordinary one.
    assert ChatMetadata().command is None


def test_a_command_run_with_nothing_appended_has_empty_appended_text() -> None:
    descriptor = CommandDescriptor(command="summary")

    assert descriptor.appended_text == ""
