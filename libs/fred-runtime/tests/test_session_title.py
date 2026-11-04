# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fred_runtime.app import session_title
from fred_runtime.model_routing.provider import RoutedChatModelFactory
from fred_runtime.model_routing.turn import TurnAuthority
from fred_runtime.runtime_support.run_scope import RunScope
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import RuntimeServices
from fred_sdk.contracts.weaver import TitleAdmission
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from weaver_fixtures import turn_binding

SESSION = "00000000-0000-0000-0000-000000000011"


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            '"Comparaison des offres fournisseurs"\nIgnored',
            "Comparaison des offres fournisseurs",
        ),
        ("### <b>Analyse</b> des offres", "b Analyse b des offres"),
        ("\n  ", None),
        ("123 / []", None),
        ("é" * 100, "é" * 80),
    ],
)
def test_clean_title(text, expected):
    assert session_title.clean_title(text) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,text",
    [
        (204, "Comparaison des offres"),
        (409, "Comparaison des offres"),
        (204, "123"),
        (204, "timeout"),
        (204, "error"),
    ],
)
async def test_title_records_usage_and_persists_provenance(monkeypatch, status, text):
    admitted = turn_binding("template", session=SESSION)
    inference = admitted.inference.model_copy(
        update={
            "selection": admitted.inference.selection.model_copy(
                update={
                    "key": admitted.inference.selection.key.model_copy(
                        update={"upstream_model_id": "title-model"}
                    )
                }
            )
        }
    )
    admitted = admitted.model_copy(
        update={"title": TitleAdmission(attempt_id=uuid4(), inference=inference)}
    )
    authority = TurnAuthority(admitted, None)
    messages = []

    class Factory(RoutedChatModelFactory):
        def build_for_title(self):
            return GenericFakeChatModel(
                messages=iter(
                    [
                        AIMessage(
                            content=text,
                            usage_metadata={
                                "input_tokens": 4,
                                "output_tokens": 3,
                                "total_tokens": 7,
                            },
                        )
                    ]
                )
            )

    calls = []

    def persist(request):
        calls.append(request)
        return httpx.Response(status)

    async def lease(**kwargs):
        return SimpleNamespace(token="fixture-workload")

    monkeypatch.setattr(
        session_title,
        "get_delegation_runtime",
        lambda: SimpleNamespace(workload_token_lease=lease),
    )
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(
            user_id=admitted.subject_id,
            session_id=SESSION,
            space_id=str(admitted.space.id),
            agent_instance_id=str(admitted.agent.instance_id),
        ),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="r",
            actor="alice",
            tenant="test",
            environment=PortableEnvironment.DEV,
        ),
    )
    original = GenericFakeChatModel.ainvoke

    stopped = asyncio.Event()
    monkeypatch.setattr(session_title, "TITLE_TIMEOUT_SECONDS", 0.1)

    async def capture(self, input, *args, **kwargs):
        messages.extend(input)
        try:
            if text == "timeout":
                await asyncio.Event().wait()
            if text == "error":
                raise ValueError("synthetic model failure")
            return await original(self, input, *args, **kwargs)
        finally:
            stopped.set()

    monkeypatch.setattr(GenericFakeChatModel, "ainvoke", capture)
    async with httpx.AsyncClient(transport=httpx.MockTransport(persist)) as client:
        monkeypatch.setattr(
            session_title,
            "get_runtime_context",
            lambda: SimpleNamespace(
                config=SimpleNamespace(
                    control_plane_http_client=client,
                    control_plane_url="https://cp.invalid/api",
                )
            ),
        )
        with RunScope.open() as scope:
            authority.start(scope)
            scope.turn_authority = authority
            result = await session_title.generate_session_title(
                "é" * 700,
                binding=binding,
                services=RuntimeServices(chat_model_factory=Factory()),
            )
    assert stopped.is_set()
    assert len(messages[-1].content) == 600
    if text in ("timeout", "error"):
        assert result is None and not calls and not authority.model_usage
        return
    assert authority.model_usage[inference.selection.key].input_tokens == 4
    assert admitted.inference.selection.key not in authority.model_usage
    assert result == (SESSION if status == 204 and text != "123" else None)
    if text == "123":
        assert not calls
    else:
        [request] = calls
        assert request.url.path.endswith(f"/{SESSION}/generated-title")
        assert admitted.title is not None
        assert json.loads(request.content) == {
            "subject_id": admitted.subject_id,
            "agent_instance_id": str(admitted.agent.instance_id),
            "attempt_id": str(admitted.title.attempt_id),
            "title": text,
        }
        assert request.headers["authorization"] == "Bearer fixture-workload"


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", ["disconnect", "final", "complete", "error"])
async def test_stream_owns_title_until_final_or_cancellation(monkeypatch, ending):
    from fred_runtime.app import agent_app
    from fred_sdk.authoring import ReActAgent

    request = agent_app._AgentExecuteRequest(
        agent_id="template", message="hello", context={}
    )
    request._turn_authority = TurnAuthority(
        turn_binding("template", session=SESSION), None
    )
    stopped = asyncio.Event()
    tasks = []

    async def title():
        try:
            if ending == "complete":
                return SESSION
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async def inner(*args, **kwargs):
        request._title_task = asyncio.create_task(title())
        tasks.append(request._title_task)
        scope = RunScope.current()
        assert scope is not None
        scope.register_child(request._title_task)
        await asyncio.sleep(0)
        if ending == "disconnect":
            yield {"kind": "status", "status": "running"}
            await asyncio.Event().wait()
        else:
            yield {"kind": "execution_error" if ending == "error" else "final"}

    monkeypatch.setattr(agent_app, "_iterate_runtime_event_payloads_inner", inner)
    definition = ReActAgent(
        agent_id="template",
        role="Test",
        description="Test",
        system_prompt_template="Answer",
    )
    stream = agent_app._iterate_runtime_event_payloads(
        definition, request, owns_run_record=True
    )
    if ending == "disconnect":
        await anext(stream)
        await stream.aclose()
    else:
        events = [event async for event in stream]
        assert [event["kind"] for event in events] == (
            ["session_title", "final"]
            if ending == "complete"
            else ["execution_error"]
            if ending == "error"
            else ["final"]
        )
    assert stopped.is_set()
    assert tasks and all(task.done() for task in tasks)
