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

from dataclasses import fields

import pytest
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.capability.hitl import HitlGateRequest
from fred_sdk.contracts.runtime import (
    MEMORY_MAX_ACTIVE_NOTES,
    MEMORY_NOTE_MAX_CHARS,
    MemoryNote,
    MemoryPort,
    MemoryPortError,
    RuntimeServices,
)
from pydantic import ValidationError


def test_memory_is_the_last_runtime_service() -> None:
    """Appended last: no positional caller may see another field move."""

    assert fields(RuntimeServices)[-1].name == "memory"
    assert RuntimeServices().memory is None


def test_a_note_is_frozen_and_carries_only_what_the_model_needs() -> None:
    note = MemoryNote(note_id="n-1", content="Prefers tables.")

    assert note.created_at is None
    with pytest.raises(ValidationError, match="frozen"):
        note.content = "other"
    with pytest.raises(ValidationError):
        MemoryNote.model_validate({"note_id": "n", "content": "c", "created_by": "u"})


def test_port_errors_carry_status_and_problem_code() -> None:
    error = MemoryPortError("full", status_code=409, code="memory_full")

    assert (error.status_code, error.code, error.timed_out) == (
        409,
        "memory_full",
        False,
    )
    assert MemoryPortError("down").code is None


def test_the_bounds_match_the_control_plane() -> None:
    assert (MEMORY_NOTE_MAX_CHARS, MEMORY_MAX_ACTIVE_NOTES) == (500, 50)


def test_the_port_is_abstract() -> None:
    assert MemoryPort.__abstractmethods__ == {
        "list_notes",
        "remember",
        "forget",
        "edit",
    }


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
