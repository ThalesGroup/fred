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

"""Agent memory port contract (#3698)."""

from __future__ import annotations

import pytest
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.capability.hitl import HitlGateRequest
from fred_sdk.contracts.runtime import (
    MemoryNote,
    MemoryPortError,
    RememberedMemoryNote,
    RuntimeServices,
)
from pydantic import ValidationError


def test_port_errors_carry_status_and_problem_code() -> None:
    error = MemoryPortError("full", status_code=409, code="memory_full")

    assert (error.status_code, error.code, error.timed_out) == (
        409,
        "memory_full",
        False,
    )
    assert MemoryPortError("down").code is None


def test_a_remembered_note_says_whether_it_was_created() -> None:
    note = RememberedMemoryNote(note_id="n-1", content="Prefers tables.", created=False)

    assert isinstance(note, MemoryNote) and note.created is False
    with pytest.raises(ValidationError):
        RememberedMemoryNote.model_validate({"note_id": "n-1", "content": "c"})


def test_a_gate_request_without_history_has_no_messages() -> None:
    """A runtime that cannot hand over history gives an empty sequence, which
    a predicate relying on it must treat as unknown."""

    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id="u", session_id="s"),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    request = HitlGateRequest(tool_call={"name": "t"}, tool=None, context=ctx)

    assert tuple(request.messages) == ()
