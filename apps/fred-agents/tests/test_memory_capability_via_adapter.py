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
`MemoryAdapter` (fred-runtime) driven through `MemoryCapability`'s real tools
and prompt overlay (fred-capability-memory), wired the way `agent_app.py`
wires them, against a simulated Control Plane holding the notes.

The capability's own tests use a fake port and the adapter's own tests a
fake transport; this file proves the two agree on the wire shapes: the note
the server returns is the card the chat shows, a forget reaches the note the
model named, and an edit keeps the note in place.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from fred_capability_memory.capability import (
    MemoryCapability,
    MemoryConfig,
    _MemoryPromptMiddleware,
)
from fred_runtime.capabilities import CapabilityRegistry
from fred_runtime.integrations.v2_runtime.adapters import MemoryAdapter
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import RuntimeServices

_BASE_PATH = "/spaces/space-1/agent-instances/inst-1/memory"


class _ControlPlane:
    """The notes of one agent instance, with the server's 50-note cap."""

    def __init__(self, *, capacity: int = 50) -> None:
        self.notes: list[dict[str, Any]] = []
        self.capacity = capacity
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.params["session_id"] == "s-1"
        if request.method == "GET" and request.url.path == _BASE_PATH:
            return httpx.Response(200, json={"notes": self.notes})
        if request.method == "POST" and request.url.path == _BASE_PATH:
            if len(self.notes) >= self.capacity:
                return httpx.Response(
                    409,
                    json={"code": "memory_full", "detail": "The memory is full."},
                )
            note = {
                "note_id": f"note-{len(self.notes) + 1}",
                "content": json.loads(request.content)["content"],
                "created_by": "u-1",
                "created_session_id": "s-1",
                "created_at": "2026-11-26T10:00:00Z",
            }
            self.notes.append(note)
            return httpx.Response(201, json=note)
        if request.method == "PATCH":
            note_id = request.url.path.rsplit("/", 1)[-1]
            index = next(i for i, n in enumerate(self.notes) if n["note_id"] == note_id)
            note = {
                **self.notes[index],
                "note_id": f"{note_id}-r",
                "content": json.loads(request.content)["content"],
            }
            self.notes[index] = note
            return httpx.Response(200, json=note)
        if request.method == "DELETE":
            note_id = request.url.path.rsplit("/", 1)[-1]
            self.notes = [n for n in self.notes if n["note_id"] != note_id]
            return httpx.Response(204)
        return httpx.Response(404)


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="s-1",
            space_id="space-1",
            agent_instance_id="inst-1",
            user_id="u-1",
            access_token="tok",
        ),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


async def _turn(server: _ControlPlane, script: list[tuple[str, dict[str, Any]]]):
    registry = CapabilityRegistry()
    registry.register(MemoryCapability())
    registry.validate(env={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(server)) as client:
        adapter = MemoryAdapter(
            binding=_binding(),
            control_plane_url="https://control-plane.internal",
            http_client=client,
        )
        ctx: Any = CapabilityContext(
            identity=CapabilityIdentity(user_id="u-1", session_id="s-1"),
            config=MemoryConfig(),
            turn_options=EmptyModel(),
            services=RuntimeServices(memory=adapter),
        )
        tools = {t.name: t for t in MemoryCapability().tools(ctx)}
        results = []
        for name, args in script:
            results.append(
                await tools[name].ainvoke(
                    {"type": "tool_call", "name": name, "args": args, "id": "c"}
                )
            )
        block = await _MemoryPromptMiddleware(adapter)._compose()
    return results, block


def test_remember_then_forget_round_trips_through_the_control_plane() -> None:
    server = _ControlPlane()
    (remembered, forgotten), block = asyncio.run(
        _turn(
            server,
            [
                ("memory_remember", {"text": "Prefers tables."}),
                ("memory_forget", {"note_id": "note-1"}),
            ],
        )
    )

    assert remembered.artifact.ui_parts[0].model_dump() == {
        "type": "memory_note",
        "note_id": "note-1",
        "content": "Prefers tables.",
        "action": "remembered",
        "previous_content": None,
    }
    assert forgotten.artifact.ui_parts[0].action == "forgotten"
    assert [(r.method, r.url.path) for r in server.requests][:3] == [
        ("POST", _BASE_PATH),
        ("GET", _BASE_PATH),
        ("DELETE", f"{_BASE_PATH}/note-1"),
    ]
    assert server.notes == []
    assert "no notes yet" in block


def test_edit_keeps_the_note_in_place_through_the_control_plane() -> None:
    server = _ControlPlane()
    (_, _, edited), block = asyncio.run(
        _turn(
            server,
            [
                ("memory_remember", {"text": "Uses metric units."}),
                ("memory_remember", {"text": "Answers in French."}),
                ("memory_edit", {"note_id": "note-1", "text": "Uses imperial units."}),
            ],
        )
    )

    part = edited.artifact.ui_parts[0]
    assert (part.action, part.note_id, part.previous_content) == (
        "edited",
        "note-1-r",
        "Uses metric units.",
    )
    assert ("PATCH", f"{_BASE_PATH}/note-1") in [
        (r.method, r.url.path) for r in server.requests
    ]
    assert block.index("Uses imperial units.") < block.index("Answers in French.")
