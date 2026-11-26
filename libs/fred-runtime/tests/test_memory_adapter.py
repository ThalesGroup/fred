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

"""`MemoryAdapter` — the wire boundary of the agent instance's memory (#3698)."""

from __future__ import annotations

import json

import httpx
import pytest
from fred_core.security.backend_to_backend_auth import M2MAuthConfig, M2MTokenProvider
from fred_core.security.delegation import DelegationConfig
from fred_runtime.common.outbound_credentials import DelegationRuntime, RunRecord
from fred_runtime.integrations.v2_runtime.adapters import MemoryAdapter
from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import MemoryNote, MemoryPortError

pytestmark = pytest.mark.asyncio

_BASE = "https://control-plane.internal/spaces/space-1/agent-instances/inst-1/memory"
_NOTE = {
    "note_id": "n-1",
    "content": "Prefers tables.",
    "created_by": "u-1",
    "created_session_id": "s-1",
    "created_at": "2026-11-26T10:00:00Z",
}


def _binding(**overrides: str | None) -> BoundRuntimeContext:
    fields: dict[str, str | None] = {
        "session_id": "s-1",
        "user_id": "u-1",
        "space_id": "space-1",
        "agent_instance_id": "inst-1",
        "access_token": "tok",
    }
    fields.update(overrides)
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(**fields),  # type: ignore[arg-type]
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


async def _run(
    respond: httpx.Response | None = None,
    *,
    call: str = "list",
    binding: BoundRuntimeContext | None = None,
) -> tuple[object, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if respond is not None:
            return respond
        if request.method == "GET":
            return httpx.Response(200, json={"notes": [_NOTE]})
        if request.method == "POST":
            return httpx.Response(201, json=_NOTE)
        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MemoryAdapter(
            binding=binding or _binding(),
            control_plane_url="https://control-plane.internal/",
            http_client=client,
        )
        if call == "list":
            result: object = await adapter.list_notes()
        elif call == "remember":
            result = await adapter.remember("Prefers tables.")
        else:
            result = await adapter.forget("n-1")
    return result, seen


async def test_list_reads_the_instance_memory_of_this_conversation() -> None:
    notes, seen = await _run()

    assert notes == [
        MemoryNote(
            note_id="n-1", content="Prefers tables.", created_at="2026-11-26T10:00:00Z"
        )
    ]
    (request,) = seen
    assert request.method == "GET"
    assert str(request.url) == f"{_BASE}?session_id=s-1"
    assert request.headers["Authorization"] == "Bearer tok"


async def test_remember_posts_the_content() -> None:
    note, seen = await _run(call="remember")

    assert isinstance(note, MemoryNote) and note.note_id == "n-1"
    assert seen[0].method == "POST"
    assert json.loads(seen[0].content) == {"content": "Prefers tables."}


async def test_forget_deletes_the_note() -> None:
    result, seen = await _run(call="forget")

    assert result is None
    assert seen[0].method == "DELETE"
    assert str(seen[0].url) == f"{_BASE}/n-1?session_id=s-1"


async def test_a_full_memory_keeps_the_problem_code_and_detail() -> None:
    problem = httpx.Response(
        409,
        json={"code": "memory_full", "detail": "This memory already holds 50 notes."},
    )
    with pytest.raises(MemoryPortError) as raised:
        await _run(problem, call="remember")

    assert raised.value.status_code == 409
    assert raised.value.code == "memory_full"
    assert str(raised.value) == "This memory already holds 50 notes."


async def test_an_unbound_instance_never_calls_the_control_plane() -> None:
    with pytest.raises(MemoryPortError, match="no bound agent instance"):
        await _run(binding=_binding(agent_instance_id=None))


async def test_a_conversation_is_required() -> None:
    with pytest.raises(MemoryPortError, match="bound conversation"):
        await _run(binding=_binding(session_id=None))


async def test_a_delegated_call_carries_its_grant_and_ends_the_run_when_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRED_TEST_MEMORY_WORKLOAD_SECRET", "synthetic")
    tokens = M2MTokenProvider(
        M2MAuthConfig(
            keycloak_realm_url="https://iam.invalid/realms/test",
            client_id="test-workload",
            secret_env="FRED_TEST_MEMORY_WORKLOAD_SECRET",
        ),
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, json={"access_token": "workload", "expires_in": 300}
            )
        ),
    )
    runtime = DelegationRuntime(
        config=DelegationConfig(act_for_people=True), token_provider=tokens
    )
    runtime.records.admit(RunRecord(run_id="run-1", person_id="p-1", agent_id="inst-1"))
    seen: list[httpx.Request] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(403)

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as client:
        adapter = MemoryAdapter(
            binding=_binding(access_token=None),
            control_plane_url="https://control-plane.internal",
            http_client=client,
            credentials=runtime.provider_for(run_id="run-1", agent_id="inst-1"),
        )
        with pytest.raises(AuthorityLostError):
            await adapter.remember("A note.")

    (request,) = seen
    assert dict(request.url.params) == {
        "session_id": "s-1",
        "person": "p-1",
        "run": "run-1",
        "agent": "inst-1",
    }
    assert json.loads(request.content) == {"content": "A note."}
