# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Consumption reports use workload identity after run teardown; no real servers."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from conftest import StaticWorkloadTokens
from fastapi.routing import APIRoute
from fred_core.security.backend_to_backend_auth import TokenLease
from fred_runtime.app import agent_app, usage
from fred_runtime.app.context import PodApplicationContext
from fred_runtime.common.background_tasks import spawn
from fred_runtime.common.outbound_credentials import DelegationRuntime
from fred_runtime.model_routing.turn import TurnAuthority
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.execution import RuntimeExecuteRequest
from fred_sdk.contracts.models import ReActAgentDefinition
from starlette.requests import Request
from starlette.responses import StreamingResponse
from weaver_fixtures import INSTANCE_ID, SPACE_ID, turn_binding

SESSION = "00000000-0000-0000-0000-000000000005"
COUNTERS = {
    "input_tokens": 21,
    "output_tokens": 5,
    "cache_read_tokens": 3,
    "cache_creation_tokens": 2,
}
ENDED = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def reporting(monkeypatch):
    monkeypatch.setattr(usage, "_missing_workload_logged", False)
    calls = []
    state = SimpleNamespace(reply=None)

    async def endpoint(request):
        calls.append(request)
        if state.reply is not None:
            return await state.reply(request)
        return httpx.Response(204)

    tokens = StaticWorkloadTokens()
    delegation = DelegationRuntime(token_provider=tokens)
    monkeypatch.setattr(usage, "get_delegation_runtime", lambda: delegation)
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as client:
        config = SimpleNamespace(
            control_plane_url="https://control.invalid/api",
            control_plane_http_client=client,
            history_store=None,
        )
        context = SimpleNamespace(config=config)
        monkeypatch.setattr(usage, "get_runtime_context", lambda: context)
        monkeypatch.setattr(agent_app, "get_runtime_context", lambda: context)
        monkeypatch.setattr(agent_app, "_emit_turn_completed", lambda *a, **kw: None)
        tasks = []

        def tracked_spawn(coro):
            task = spawn(coro)
            tasks.append(task)
            return task

        monkeypatch.setattr(agent_app, "spawn", tracked_spawn)
        state.calls = calls
        state.tokens = tokens
        state.delegation = delegation
        state.config = config
        state.tasks = tasks
        yield state
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def admitted_run(*, consumed=True):
    authority = TurnAuthority(turn_binding("template", session=SESSION), None)
    if consumed:
        authority.record_usage(COUNTERS)
    return authority


@pytest.mark.asyncio
async def test_closed_run_reports_canonical_offer_without_delegation(reporting, caplog):
    caplog.set_level(logging.INFO)
    authority = admitted_run()
    authority.close()
    assert len(reporting.delegation.records) == 0
    await usage.report_run_usage(authority, exchange_id="exchange", occurred_at=ENDED)
    [sent] = reporting.calls
    assert sent.url.path == (
        f"/api/spaces/{SPACE_ID}/sessions/{SESSION}/exchanges/exchange/usage"
    )
    assert not sent.url.query
    assert sent.headers["Authorization"] == "Bearer workload-token"
    assert UUID(sent.headers["Idempotency-Key"]).version == 4
    assert json.loads(sent.content) == {
        "occurred_at": ENDED.isoformat(),
        "models": [{"model_source_id": "a", "upstream_model_id": "first", **COUNTERS}],
    }
    assert "outcome=recorded" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("responses", "outcome"),
    [
        ([503, 204], "recorded"),
        (["network", 204], "recorded"),
        ([503, 503], "lost"),
        (["network", "network"], "lost"),
        ([400], "rejected"),
        ([403], "rejected"),
        ([404], "rejected"),
        ([409], "conflict"),
        ([422], "rejected"),
    ],
)
async def test_retry_budget_and_identical_report(reporting, caplog, responses, outcome):
    caplog.set_level(logging.INFO)

    async def reply(request):
        status = responses[len(reporting.calls) - 1]
        if status == "network":
            raise httpx.ConnectError("private upstream detail", request=request)
        return httpx.Response(status)

    reporting.reply = reply
    await usage.report_run_usage(admitted_run(), exchange_id="turn", occurred_at=ENDED)
    assert len(reporting.calls) == len(responses)
    assert len({call.headers["Idempotency-Key"] for call in reporting.calls}) == 1
    assert len({call.content for call in reporting.calls}) == 1
    assert f"outcome={outcome}" in caplog.text
    assert "private upstream detail" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("second_status", [204, 401])
async def test_401_refreshes_workload_only_once(reporting, monkeypatch, second_status):
    refresh = AsyncMock(return_value=TokenLease("renewed-workload", 1))
    monkeypatch.setattr(reporting.tokens, "refresh_rejected", refresh)

    async def reply(request):
        return httpx.Response(401 if len(reporting.calls) == 1 else second_status)

    reporting.reply = reply
    await usage.report_run_usage(admitted_run(), exchange_id="turn", occurred_at=ENDED)
    refresh.assert_awaited_once()
    assert len(reporting.calls) == 2
    assert reporting.calls[1].headers["Authorization"] == "Bearer renewed-workload"
    assert reporting.calls[0].content == reporting.calls[1].content
    assert (
        reporting.calls[0].headers["Idempotency-Key"]
        == reporting.calls[1].headers["Idempotency-Key"]
    )


@pytest.mark.asyncio
async def test_no_refresh_support_does_not_repeat_401(reporting, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(reporting.tokens, "refresh_rejected", None)
    reporting.reply = AsyncMock(return_value=httpx.Response(401))
    await usage.report_run_usage(admitted_run(), exchange_id="turn", occurred_at=ENDED)
    assert len(reporting.calls) == 1
    assert "outcome=rejected" in caplog.text


@pytest.mark.asyncio
async def test_skip_unknown_consumption_and_log_missing_workload_once(
    reporting, monkeypatch, caplog
):
    caplog.set_level(logging.INFO)
    await usage.report_run_usage(
        admitted_run(consumed=False), exchange_id="turn", occurred_at=ENDED
    )
    assert not reporting.calls
    assert "reason=no_consumption" in caplog.text
    for missing in (None, DelegationRuntime(), DelegationRuntime()):
        monkeypatch.setattr(
            usage, "get_delegation_runtime", lambda missing=missing: missing
        )
        await usage.report_run_usage(
            admitted_run(), exchange_id="turn", occurred_at=ENDED
        )
    assert not reporting.calls
    assert caplog.text.count("reason=no_workload_token") == 1


@pytest.mark.asyncio
async def test_evaluate_without_session_skips_report_without_warning(
    reporting, monkeypatch, caplog
):
    caplog.set_level(logging.INFO)
    authority = TurnAuthority(turn_binding("template", session=None), None)
    internal = agent_app._AgentExecuteRequest(
        agent_instance_id=INSTANCE_ID,
        message="hello",
        context={"space_id": SPACE_ID, "user_id": "alice"},
    )
    internal._turn_authority = authority
    target = SimpleNamespace(
        definition=SimpleNamespace(agent_id="template", tags=()),
        credential_provider=None,
        tuning=None,
        team_settings=None,
        platform_prompt=None,
        team_id=None,
        agent_instance_name=None,
    )
    monkeypatch.setattr(
        agent_app, "_authorize_and_resolve", AsyncMock(return_value=(internal, target))
    )
    monkeypatch.setattr(agent_app, "_enforce_turn_options", lambda *args: None)
    acquire = AsyncMock()
    monkeypatch.setattr(reporting.tokens, "get_token_lease", acquire)

    async def events(*args, **kwargs):
        authority.record_usage(COUNTERS)
        yield {"kind": "final", "content": "done"}
        authority.close()

    monkeypatch.setattr(agent_app, "_iterate_runtime_event_payloads", events)
    router = agent_app._build_agent_router({}, False, 5000)
    evaluate = next(
        route.endpoint
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == "/agents/evaluate"
    )
    result = await evaluate(
        request=RuntimeExecuteRequest(
            agent_instance_id=INSTANCE_ID,
            input="hello",
            runtime_context=RuntimeContext(space_id=SPACE_ID),
        ),
        http_request=Request(
            {
                "type": "http",
                "headers": [],
                "app": SimpleNamespace(state=SimpleNamespace()),
            }
        ),
        authenticated_user=None,
        container=SimpleNamespace(),
    )
    await asyncio.gather(*reporting.tasks)
    assert result.output == "done"
    assert not reporting.calls
    acquire.assert_not_awaited()
    assert "event=run_usage outcome=skipped reason=no_session" in caplog.text
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)


def stream_run(monkeypatch, *, kind="final", consumed=True, resume=False):
    authority = admitted_run(consumed=False)
    request = agent_app._AgentExecuteRequest(
        agent_instance_id=INSTANCE_ID,
        message="hello",
        context={"session_id": SESSION, "space_id": SPACE_ID, "user_id": "alice"},
        resume_payload={"answer": "yes"} if resume else None,
    )
    request._turn_authority = authority

    async def events(*args, **kwargs):
        try:
            if consumed:
                authority.record_usage(COUNTERS)
            yield {"kind": kind, "model_name": "untrusted-provider-alias"}
            if kind == "cancelled":
                await asyncio.Event().wait()
        finally:
            authority.close()

    monkeypatch.setattr(agent_app, "_iterate_runtime_event_payloads", events)
    return agent_app._stream(
        cast(ReActAgentDefinition, SimpleNamespace(agent_id="template")),
        request,
        container=cast(PodApplicationContext, SimpleNamespace()),
    )


@pytest.mark.asyncio
async def test_sse_closes_while_control_plane_is_still_blocked(reporting, monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(request):
        started.set()
        await release.wait()
        return httpx.Response(204)

    reporting.reply = slow
    response = StreamingResponse(
        stream_run(monkeypatch), media_type="text/event-stream"
    )
    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    await asyncio.wait_for(
        response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send),
        timeout=0.5,
    )
    await asyncio.wait_for(started.wait(), timeout=0.5)
    assert sent[-1] == {"type": "http.response.body", "body": b"", "more_body": False}
    assert not reporting.tasks[-1].done()
    release.set()
    await asyncio.gather(*reporting.tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["network", "timeout"])
async def test_report_failure_does_not_fail_turn(
    reporting, monkeypatch, caplog, failure
):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(usage, "REPORT_TIMEOUT_SECONDS", 0.01)

    async def failing(request):
        if failure == "timeout":
            await asyncio.Event().wait()
        raise httpx.ConnectError("private detail", request=request)

    reporting.reply = failing
    events = [event async for event in stream_run(monkeypatch)]
    await asyncio.wait_for(asyncio.gather(*reporting.tasks), timeout=0.5)
    assert len(events) == 1 and '"kind": "final"' in events[0]
    assert "outcome=lost" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["final", "awaiting_human", "execution_error", "cancelled"]
)
@pytest.mark.parametrize("consumed", [True, False])
async def test_all_endings_report_only_known_usage(
    reporting, monkeypatch, kind, consumed
):
    stream = stream_run(monkeypatch, kind=kind, consumed=consumed)
    if kind == "cancelled":
        await anext(stream)
        await stream.aclose()
    else:
        _ = [event async for event in stream]
    await asyncio.gather(*reporting.tasks)
    assert len(reporting.calls) == int(consumed)


@pytest.mark.asyncio
async def test_task_cancellation_still_spawns_report(reporting, monkeypatch):
    stream = stream_run(monkeypatch, kind="cancelled")
    await anext(stream)
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await asyncio.gather(*reporting.tasks)
    assert len(reporting.calls) == 1


@pytest.mark.asyncio
async def test_token_acquisition_shares_total_deadline(reporting, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(usage, "REPORT_TIMEOUT_SECONDS", 0.01)

    async def slow_token():
        await asyncio.Event().wait()

    monkeypatch.setattr(reporting.tokens, "get_token_lease", slow_token)
    await asyncio.wait_for(
        usage.report_run_usage(admitted_run(), exchange_id="turn", occurred_at=ENDED),
        timeout=0.5,
    )
    assert not reporting.calls
    assert "outcome=lost reason=timeout" in caplog.text


@pytest.mark.asyncio
async def test_hitl_resume_has_new_key_on_same_exchange(reporting, monkeypatch):
    history = SimpleNamespace(
        latest_exchange_id=AsyncMock(return_value=None),
        next_rank=AsyncMock(return_value=0),
    )
    reporting.config.history_store = history

    async def save(**kwargs):
        history.latest_exchange_id.return_value = kwargs["exchange_id"]

    monkeypatch.setattr(agent_app, "_write_turn_history", save)
    _ = [event async for event in stream_run(monkeypatch, kind="awaiting_human")]
    await asyncio.gather(*reporting.tasks)
    _ = [event async for event in stream_run(monkeypatch, resume=True)]
    await asyncio.gather(*reporting.tasks)
    first, resumed = reporting.calls
    assert first.url == resumed.url
    assert first.headers["Idempotency-Key"] != resumed.headers["Idempotency-Key"]


@pytest.mark.asyncio
async def test_title_usage_aggregates_by_offer_in_the_existing_report(reporting):
    authority = admitted_run()
    main = authority.binding.inference.selection.key
    title = main.model_copy(update={"upstream_model_id": "title-model"})
    authority.record_usage(COUNTERS, offer=main)
    authority.record_usage(COUNTERS, offer=title)
    authority.close()
    await usage.report_run_usage(authority, exchange_id="exchange", occurred_at=ENDED)
    [sent] = reporting.calls
    models = json.loads(sent.content)["models"]
    assert len(models) == 2
    assert models[0]["input_tokens"] == 2 * COUNTERS["input_tokens"]
    assert models[1]["input_tokens"] == COUNTERS["input_tokens"]
    assert models[1]["upstream_model_id"] == "title-model"
