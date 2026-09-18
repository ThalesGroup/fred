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
    HitlRequestPart,
    HitlResponsePart,
    make_hitl_request,
    make_hitl_response,
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
