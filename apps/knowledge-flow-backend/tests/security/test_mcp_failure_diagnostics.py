"""Exercise the MCP v2 client seam and real mounted failure envelopes."""

from __future__ import annotations

import asyncio
import io
import json
import logging
from uuid import uuid4

import httpx2
import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient
from fred_core.common import register_exception_handlers
from fred_core.logs.context import current_context, request_log_scope
from fred_core.logs.http import RequestLoggingFastAPI
from fred_core.logs.log_setup import log_setup
from fred_core.logs.propagation import CONTEXT_HEADER, admit_delegated_log_context, encode_log_context
from fred_core.security import mcp_delegation
from fred_core.security.delegation import AssertedUser, DelegationGrant
from fred_core.security.mcp_delegation import declare_delegation_parameters

from knowledge_flow_backend import mcp_mount
from knowledge_flow_backend.features.tabular.controller import TabularController
from knowledge_flow_backend.mcp_mount import _DelegatedMCPTransport, _mcp_http_client, mount_fastapi_tools

_GRANT = {"person": "person-a", "run": "run-a", "agent": "agent-a"}
_HEADERS = {"Authorization": "Bearer fixture", "Accept": "application/json, text/event-stream"}
_META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}


@pytest.fixture(autouse=True)
def _admitted_mcp_request(monkeypatch):
    async def authenticate(request: Request, token: str):
        grant = DelegationGrant(**{name: request.query_params.get(name, value) for name, value in _GRANT.items()})
        reset = mcp_delegation._verified_grant.set(grant)
        try:
            admit_delegated_log_context(request.headers.get(CONTEXT_HEADER), user_id=grant.person, run_id=grant.run, agent_id=grant.agent)
            yield None
        finally:
            mcp_delegation._verified_grant.reset(reset)

    monkeypatch.setattr(mcp_mount, "mcp_mount_auth", authenticate)


async def admitted_person(request: Request):
    grant = mcp_delegation.verified_grant()
    assert grant is not None
    admit_delegated_log_context(request.headers.get(CONTEXT_HEADER), user_id=grant.person, run_id=grant.run, agent_id=grant.agent)
    return AssertedUser(uid=grant.person, client_id="fixture-pod", run_id=grant.run, agent_id=grant.agent)


def _call(client, name, arguments, *, context=None):
    headers = {
        **_HEADERS,
        "MCP-Protocol-Version": "2026-07-28",
        "Mcp-Method": "tools/call",
        "Mcp-Name": name,
        **({CONTEXT_HEADER: context} if context else {}),
    }
    response = client.post("/mcp", params=_GRANT, headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"_meta": _META, "name": name, "arguments": arguments}})
    assert response.status_code == 200
    return response


def _mount(app):
    from unittest.mock import patch

    inner = _mcp_http_client(app)
    for route in app.routes:
        if hasattr(route, "tags"):
            route.tags.append("Diagnostics")
    with patch("knowledge_flow_backend.mcp_mount._mcp_http_client", return_value=inner):
        mount = mount_fastapi_tools(app, path="/mcp", name="Diagnostics", description="Diagnostics", tags={"Diagnostics", "Tabular"})
    return inner, mount


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_mounted_failure_retains_registered_metadata_and_receiver_references(caplog, status):
    app = RequestLoggingFastAPI()
    register_exception_handlers(app)
    seen = {}

    @app.get("/documents/{uid}", operation_id="describe_document", dependencies=[Depends(declare_delegation_parameters)])
    async def describe(uid: str, user=Depends(admitted_person)):
        seen.update(current_context())
        raise HTTPException(status, detail="BODY-CANARY")

    inner, _ = _mount(app)
    with caplog.at_level(logging.INFO), TestClient(app) as client:
        response = _call(client, "describe_document", {"uid": "PATH-CANARY", **dict.fromkeys(_GRANT, "FORGED-CANARY")}, context=encode_log_context({"session_id": "session-a", "team_id": "team-a"}))
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["content"][0]["text"] == "Tool request failed."
    assert "BODY-CANARY" not in response.text
    [failure] = [record for record in caplog.records if record.getMessage() == "mcp.inner_http_failure"]
    assert failure.levelno == (logging.ERROR if status >= 500 else logging.WARNING)
    assert failure.tool_name == "describe_document"
    assert failure.upstream_route == "/documents/{uid}"
    assert failure.method == "GET"
    assert failure.upstream_http_status == status
    assert failure.upstream_request_id == seen["request_id"]
    assert failure.upstream_correlation_id == seen["correlation_id"]
    assert seen["user_id"] == _GRANT["person"]
    assert seen["session_id"] == "session-a"
    assert seen["team_id"] == "team-a"
    assert "CANARY" not in repr(failure.__dict__)
    assert inner.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("delegated", [False, True])
@pytest.mark.parametrize(
    "content_type,content",
    [
        ("application/json", b'{"person":"forged","run":"forged","agent":"forged","keep":{"person":"nested"}}'),
        ("application/octet-stream", b"unchanged bytes"),
        ("application/json", b'["unchanged array"]'),
        ("application/json", b"{malformed"),
    ],
)
async def test_wire_sanitization_preserves_unrelated_payload_and_framing(delegated, content_type, content):
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request):
        body = await request.body()
        return {"query": list(request.query_params.multi_items()), "body": body.decode(), "length": request.headers.get("content-length"), "context": request.headers.get(CONTEXT_HEADER)}

    grant = DelegationGrant(**_GRANT) if delegated else None
    token = mcp_delegation._verified_grant.set(grant)
    try:
        with request_log_scope(session_id="trusted-session"):
            async with _mcp_http_client(app) as client:
                result = (await client.post("/echo?person=x&person=y&run=x&agent=x&keep=a&keep=b", content=content, headers={"Content-Type": content_type, CONTEXT_HEADER: "FORGED-HEADER"})).json()
    finally:
        mcp_delegation._verified_grant.reset(token)
    expected = [["keep", "a"], ["keep", "b"]] + ([[k, v] for k, v in _GRANT.items()] if delegated else [])
    assert result["query"] == expected
    if content.startswith(b'{"person"'):
        assert json.loads(result["body"]) == {"keep": {"person": "nested"}}
    else:
        assert result["body"].encode() == content
    assert int(result["length"]) == len(result["body"].encode())
    assert result["context"] == (encode_log_context({"session_id": "trusted-session"}) if delegated else None)


@pytest.mark.asyncio
@pytest.mark.parametrize("reference", [None, "bad-reference-CANARY", "x" * 2000, str(uuid4()).upper()])
async def test_invalid_or_missing_response_references_are_omitted(caplog, reference):
    app = FastAPI()

    @app.get("/failure", operation_id="failure")
    async def failure():
        return Response("body", status_code=404, headers={"X-Request-ID": reference, "X-Correlation-ID": reference} if reference else {})

    async with _mcp_http_client(app) as client:
        response = await client.get("/failure")
    assert response.text == "body"
    [record] = [r for r in caplog.records if r.getMessage() == "mcp.inner_http_failure"]
    assert not hasattr(record, "upstream_request_id")
    assert not hasattr(record, "upstream_correlation_id")


@pytest.mark.asyncio
async def test_missing_route_and_success_add_no_invented_metadata_or_failure(caplog):
    async with _mcp_http_client(FastAPI()) as client:
        response = await client.get("/missing/PATH-CANARY")
    assert response.status_code == 404
    [record] = [r for r in caplog.records if r.getMessage() == "mcp.inner_http_failure"]
    assert not hasattr(record, "tool_name") and not hasattr(record, "upstream_route")
    assert "CANARY" not in repr(record.__dict__)


@pytest.mark.asyncio
async def test_redirects_are_not_followed_and_success_is_silent(caplog):
    app = FastAPI()
    calls = []

    @app.get("/redirect")
    async def redirect():
        return Response(status_code=307, headers={"Location": "/target"})

    @app.get("/target")
    async def target():
        calls.append(1)
        return {}

    async with _mcp_http_client(app) as client:
        assert (await client.get("/redirect")).status_code == 307
        assert calls == []
        assert (await client.get("/target")).status_code == 200
    assert not [r for r in caplog.records if r.getMessage() == "mcp.inner_http_failure"]


@pytest.mark.asyncio
async def test_interleaved_invocations_restore_grant_context_and_metadata(caplog):
    app = FastAPI()
    arrived = asyncio.Event()
    contexts = {}

    @app.get("/one", operation_id="one")
    @app.get("/two", operation_id="two")
    async def endpoint(request: Request):
        key = request.query_params["person"]
        contexts[key] = request.headers[CONTEXT_HEADER]
        arrived.set()
        await asyncio.sleep(0)
        return Response(key, status_code=404, headers={"X-Request-ID": str(uuid4())})

    async with _mcp_http_client(app) as client:

        async def invoke(person, path):
            token = mcp_delegation._verified_grant.set(DelegationGrant(person=person, run="run", agent="agent"))
            try:
                with request_log_scope(session_id=person):
                    if person == "two":
                        await arrived.wait()
                    else:
                        await asyncio.sleep(0)
                    return await client.get(path)
            finally:
                mcp_delegation._verified_grant.reset(token)

        responses = await asyncio.gather(invoke("one", "/one"), invoke("two", "/two"))
    assert [r.text for r in responses] == ["one", "two"]
    assert contexts == {key: encode_log_context({"session_id": key}) for key in ("one", "two")}
    failures = [r for r in caplog.records if r.getMessage() == "mcp.inner_http_failure"]
    assert {r.tool_name for r in failures} == {"one", "two"}
    assert len({r.upstream_request_id for r in failures}) == 2
    assert mcp_delegation.verified_grant() is None


@pytest.mark.asyncio
async def test_cancellation_transport_errors_and_cleanup(caplog, monkeypatch):
    app = FastAPI()
    transport = _DelegatedMCPTransport(app)
    closed = []

    async def close():
        closed.append(True)

    monkeypatch.setattr(transport._transport, "aclose", close)
    async with httpx2.AsyncClient(transport=transport, base_url="http://apiserver", event_hooks={"response": []}) as client:
        for exception in (asyncio.CancelledError(), httpx2.ConnectError("transport-failed")):

            async def fail(_request):
                raise exception

            monkeypatch.setattr(transport._transport, "handle_async_request", fail)
            with pytest.raises(type(exception)):
                await client.get("/test")
    assert closed == [True]
    assert not [r for r in caplog.records if r.getMessage() == "mcp.inner_http_failure"]


@pytest.fixture
def logging_sinks():
    # Reuse the shared logging fixture's restoration and generic store contract.
    from fred_core.tests.common.test_log_setup import _StubLogStore

    loggers = [logging.getLogger(), *[v for v in logging.Logger.manager.loggerDict.values() if isinstance(v, logging.Logger)]]
    saved = [(v, v.level, list(v.handlers), list(v.filters), v.propagate, v.disabled) for v in loggers]
    factory = logging.getLogRecordFactory()
    store = _StubLogStore()
    log_setup(service_name="knowledge-flow", service_role="api", log_level="DEBUG", log_format="json", store=store, use_rich=False)
    output = io.StringIO()
    for handler in {h for v in [logging.getLogger(), logging.getLogger("fastmcp")] for h in v.handlers if isinstance(h, logging.StreamHandler)}:
        handler.setStream(output)
    try:
        yield store, output
    finally:
        logging.setLogRecordFactory(factory)
        for v in list(logging.Logger.manager.loggerDict.values()):
            if isinstance(v, logging.Logger) and v not in loggers:
                v.handlers.clear()
                v.filters.clear()
                v.propagate = True
                v.setLevel(logging.NOTSET)
        for v, level, handlers, filters, propagate, disabled in saved:
            v.setLevel(level)
            v.handlers[:] = handlers
            v.filters[:] = filters
            v.propagate = propagate
            v.disabled = disabled


def test_curated_sql_400_result_and_full_delegated_json_log(logging_sinks, capsys):
    """Exercise the Weaver controller/error policy and MCP logging boundary."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from knowledge_flow_backend.features.tabular.controller import tabular_service
    from knowledge_flow_backend.security.weaver_admission import delegated_person

    app = RequestLoggingFastAPI()
    register_exception_handlers(app)
    router = APIRouter(dependencies=[Depends(declare_delegation_parameters)])
    TabularController(router)
    app.include_router(router)
    app.dependency_overrides[tabular_service] = lambda: SimpleNamespace(query_read=AsyncMock(side_effect=ValueError("Unknown column amount_typo")))
    app.dependency_overrides[delegated_person] = admitted_person
    inner, _ = _mount(app)
    context = encode_log_context(
        {
            "session_id": "session-proof",
            "team_id": "team-proof",
            "exchange_id": "exchange-proof",
            "agent_instance_id": "instance-proof",
            "agent_id": "forged-agent",
            "user_id": "forged-user",
            "run_id": "forged-run",
            "request_id": "forged-request",
        }
    )
    with TestClient(app) as client:
        response = _call(client, "query_tabular_documents", {"sql": "SELECT amount_typo FROM sales", "dataset_uids": ["sales"]}, context=context)
    result = response.json()["result"]
    assert result["isError"] is True
    assert "Status code: 400" in result["content"][0]["text"]
    assert "amount_typo" in result["content"][0]["text"]
    store, captured = logging_sinks
    output = captured.getvalue()
    events = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    [event] = [e for e in events if e["message"] == "mcp.inner_http_failure"]
    assert event["tool_name"] == "query_tabular_documents" and event["upstream_http_status"] == 400
    assert event["session_id"] == "session-proof" and event["team_id"] == "team-proof"
    assert event["exchange_id"] == "exchange-proof" and event["agent_instance_id"] == "instance-proof"
    assert event["agent_id"] == _GRANT["agent"] and event["user_id"] == _GRANT["person"] and event["run_id"] == _GRANT["run"]
    assert event["request_id"] == response.headers["X-Request-ID"]
    assert event["request_id"] != event["upstream_request_id"]
    [access] = [e for e in events if e.get("request_id") == event["upstream_request_id"] and e["logger"] == "http"]
    assert access["http_status"] == 400 and access["session_id"] == "session-proof"
    for e in (event, access):
        assert "amount_typo" not in json.dumps(e)
    stored = [e for e in store.indexed if e.msg == "mcp.inner_http_failure"]
    assert len(stored) == 1
    # Optional local evidence export; no synthetic proof artifacts enter the repo.
    import os

    if destination := os.environ.get("KF_MCP_PROOF_FILE"):
        from pathlib import Path

        Path(destination).write_text(json.dumps({"outer_http_status": response.status_code, "mcp_result": result, "knowledge_flow_failure_log": event, "inner_access_log": access}, indent=2))


def test_dependency_and_explicit_events_confine_canaries_in_all_sinks(logging_sinks, capsys):
    app = RequestLoggingFastAPI()

    @app.get("/items/{item}", operation_id="read_item")
    async def endpoint(item: str, query: str):
        return Response("BODY-CANARY", status_code=404, headers={"X-Request-ID": "HEADER-CANARY", "X-Arbitrary": "OTHER-HEADER-CANARY"})

    inner, _ = _mount(app)
    with TestClient(app) as client:
        response = _call(client, "read_item", {"item": "PATH-CANARY", "query": "QUERY-CANARY"})
    assert "BODY-CANARY" not in response.text
    dependency = logging.getLogger("fastmcp.server")
    dependency.setLevel(logging.DEBUG)
    dependency.debug("PATH-CANARY")
    dependency.error("BODY-CANARY", extra={"arbitrary": "EXTRA-CANARY"}, exc_info=ValueError("EXCEPTION-CANARY"))
    store, captured = logging_sinks
    output = captured.getvalue()
    assert "CANARY" not in output
    assert "CANARY" not in repr(store.indexed)
    assert "mcp.inner_http_failure" in output
    assert "Dependency diagnostic" in output
    assert not [e for e in store.indexed if e.logger.startswith("fastmcp")]


def test_actual_mcp_body_grant_forgery_is_removed_without_losing_business_fields():
    from fastapi import Body

    app = FastAPI()

    @app.post("/body", operation_id="read_body")
    async def body(payload: dict = Body(...), user=Depends(admitted_person)):
        return {"payload": payload, "subject": user.uid}

    inner, _ = _mount(app)
    with TestClient(app) as client:
        response = _call(client, "read_body", {"payload": {**dict.fromkeys(_GRANT, "FORGED"), "business": {"person": "nested-kept"}}})
    result = response.json()["result"]
    assert result["isError"] is False
    assert json.loads(result["content"][0]["text"]) == {"payload": {"business": {"person": "nested-kept"}}, "subject": _GRANT["person"]}


def test_interleaved_mounted_mcp_calls_keep_admitted_scopes_and_inner_references(caplog):
    from fred_core.logs.processors import event_properties, install_context_capture

    app = RequestLoggingFastAPI()
    admitted = {}
    reached_both = asyncio.Event()

    @app.get("/interleaved", operation_id="interleaved")
    async def interleaved(user=Depends(admitted_person)):
        admitted[user.uid] = current_context()
        if len(admitted) == 2:
            reached_both.set()
        await asyncio.wait_for(reached_both.wait(), timeout=5)
        raise HTTPException(404, detail="missing")

    inner, _ = _mount(app)

    async def check():
        async with app.router.lifespan_context(app), httpx2.AsyncClient(transport=httpx2.ASGITransport(app), base_url="http://receiver") as client:

            async def invoke(person):
                grant = {"person": person, "run": "run-" + person, "agent": "agent-" + person}
                headers = {
                    **_HEADERS,
                    "MCP-Protocol-Version": "2026-07-28",
                    "Mcp-Method": "tools/call",
                    "Mcp-Name": "interleaved",
                    CONTEXT_HEADER: encode_log_context({"session_id": "session-" + person, "team_id": "team-" + person}),
                }
                response = await client.post(
                    "/mcp",
                    params=grant,
                    headers=headers,
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"_meta": _META, "name": "interleaved", "arguments": dict.fromkeys(_GRANT, "FORGED")}},
                )
                assert response.status_code == 200 and response.json()["result"]["isError"] is True

            await asyncio.gather(invoke("one"), invoke("two"))

    factory = logging.getLogRecordFactory()
    install_context_capture()
    try:
        asyncio.run(check())
    finally:
        logging.setLogRecordFactory(factory)
    failures = [event_properties(r) for r in caplog.records if r.getMessage() == "mcp.inner_http_failure"]
    assert len(failures) == 2
    for event in failures:
        person = event["user_id"]
        assert event["session_id"] == "session-" + person
        assert event["team_id"] == "team-" + person
        assert event["agent_id"] == "agent-" + person
        assert event["run_id"] == "run-" + person
        assert event["upstream_request_id"] == admitted[person]["request_id"]
        assert event["request_id"] != event["upstream_request_id"]
    assert admitted["one"]["request_id"] != admitted["two"]["request_id"]
    assert mcp_delegation.verified_grant() is None
