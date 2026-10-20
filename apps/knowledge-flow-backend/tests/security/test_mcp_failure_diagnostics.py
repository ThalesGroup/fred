"""Exercise the public client seam and real mounted MCP failure envelopes."""

from __future__ import annotations

import asyncio
import json
import io
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient
from fastapi_mcp import AuthConfig
from fred_core import get_current_user
from fred_core.common import register_exception_handlers
from fred_core.logs.context import current_context, request_log_scope
from fred_core.logs.http import RequestLoggingFastAPI
from fred_core.logs.log_setup import log_setup
from fred_core.logs.propagation import CONTEXT_HEADER, encode_log_context
from fred_core.security import mcp_delegation
from fred_core.security.delegation import DelegationGrant
from fred_core.security.mcp_delegation import declare_delegation_parameters, mcp_mount_auth, strip_grant_tool_fields
from fred_core.security.mcp_delegation_fastapi import DelegatedFastApiMCP, DelegatedMCPTransport, delegated_mcp_http_client
from fred_core.security.oidc import get_current_user_without_gcu

from knowledge_flow_backend.features.tabular.artifacts import build_default_query_alias
from knowledge_flow_backend.features.tabular.controller import TabularController
from tests.security.test_delegated_receiver import (
    _GRANT,
    _HEADERS,
    _INITIALIZE,
    _configure,
    _delegation_globals,  # noqa: F401 - reuse admission fixture
)
from tests.services.test_tabular_service import _FakeRebac, _ingest_csv


def _call(client, name, arguments, *, context=None):
    headers = {**_HEADERS, **({CONTEXT_HEADER: context} if context else {})}
    initialized = client.post("/mcp", params=_GRANT, headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INITIALIZE})
    assert initialized.status_code == 200
    response = client.post("/mcp", params=_GRANT, headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
    assert response.status_code == 200
    return response


def _mount(app):
    inner = delegated_mcp_http_client(app)
    mount = strip_grant_tool_fields(DelegatedFastApiMCP(app, http_client=inner, auth_config=AuthConfig(dependencies=[Depends(mcp_mount_auth)])))
    mount.mount_http(mount_path="/mcp")
    return inner, mount


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_mounted_failure_retains_registered_metadata_and_receiver_references(caplog, status):
    _configure()

    @asynccontextmanager
    async def lifespan(_app):
        async with inner:
            yield

    app = RequestLoggingFastAPI(lifespan=lifespan)
    register_exception_handlers(app)
    seen = {}

    @app.get("/documents/{uid}", operation_id="describe_document", dependencies=[Depends(declare_delegation_parameters)])
    async def describe(uid: str, user=Depends(get_current_user_without_gcu)):
        seen.update(current_context())
        raise HTTPException(status, detail="BODY-CANARY")

    inner, _ = _mount(app)
    with caplog.at_level(logging.INFO), TestClient(app) as client:
        response = _call(client, "describe_document", {"uid": "PATH-CANARY", **dict.fromkeys(_GRANT, "FORGED-CANARY")}, context=encode_log_context({"session_id": "session-a", "team_id": "team-a"}))
    result = response.json()["result"]
    assert result["isError"] is True
    assert f"Status code: {status}" in result["content"][0]["text"]
    assert "BODY-CANARY" in result["content"][0]["text"]
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
            async with delegated_mcp_http_client(app) as client:
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

    async with delegated_mcp_http_client(app) as client:
        response = await client.get("/failure")
    assert response.text == "body"
    [record] = [r for r in caplog.records if r.getMessage() == "mcp.inner_http_failure"]
    assert not hasattr(record, "upstream_request_id")
    assert not hasattr(record, "upstream_correlation_id")


@pytest.mark.asyncio
async def test_missing_route_and_success_add_no_invented_metadata_or_failure(caplog):
    async with delegated_mcp_http_client(FastAPI()) as client:
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

    async with delegated_mcp_http_client(app) as client:
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

    async with delegated_mcp_http_client(app) as client:

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
    transport = DelegatedMCPTransport(app)
    closed = []

    async def close():
        closed.append(True)

    monkeypatch.setattr(transport._transport, "aclose", close)
    async with httpx.AsyncClient(transport=transport, base_url="http://apiserver", event_hooks={"response": []}) as client:
        for exception in (asyncio.CancelledError(), httpx.ConnectError("transport-failed")):

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
    for handler in {h for v in [logging.getLogger(), logging.getLogger("fastapi_mcp")] for h in v.handlers if isinstance(h, logging.StreamHandler)}:
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


def test_real_sql_400_result_and_full_delegated_json_log(tmp_path, metadata_store, logging_sinks, capsys):
    """PR evidence uses the real KF service/controller, auth, MCP and JSON sinks."""
    _configure()
    asyncio.run(_ingest_csv(tmp_path=tmp_path, metadata_store=metadata_store, document_uid="sales", file_name="sales.csv", content="city,amount\nParis,10\n"))

    @asynccontextmanager
    async def lifespan(_app):
        async with inner:
            yield

    app = RequestLoggingFastAPI(lifespan=lifespan)
    register_exception_handlers(app)
    router = APIRouter(dependencies=[Depends(declare_delegation_parameters)])
    controller = TabularController(router)
    controller.service.rebac = _FakeRebac({"sales"})
    app.include_router(router)
    app.dependency_overrides[get_current_user] = get_current_user_without_gcu
    inner, _ = _mount(app)
    context = encode_log_context({"session_id": "session-proof", "team_id": "team-proof", "agent_id": "forged-agent", "user_id": "forged-user", "run_id": "forged-run", "request_id": "forged-request"})
    with TestClient(app) as client:
        response = _call(client, "read_query", {"sql": f"SELECT amount_typo FROM {build_default_query_alias('sales', 'sales.csv')}", "dataset_uids": ["sales"]}, context=context)
    result = response.json()["result"]
    assert result["isError"] is True
    assert "Status code: 400" in result["content"][0]["text"]
    assert "amount_typo" in result["content"][0]["text"]
    store, captured = logging_sinks
    output = captured.getvalue()
    events = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    [event] = [e for e in events if e["message"] == "mcp.inner_http_failure"]
    assert event["tool_name"] == "read_query" and event["upstream_http_status"] == 400
    assert event["session_id"] == "session-proof" and event["team_id"] == "team-proof"
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
    _configure()

    @asynccontextmanager
    async def lifespan(_app):
        async with inner:
            yield

    app = RequestLoggingFastAPI(lifespan=lifespan)

    @app.get("/items/{item}", operation_id="read_item")
    async def endpoint(item: str, query: str):
        return Response("BODY-CANARY", status_code=404, headers={"X-Request-ID": "HEADER-CANARY", "X-Arbitrary": "OTHER-HEADER-CANARY"})

    inner, _ = _mount(app)
    with TestClient(app) as client:
        response = _call(client, "read_item", {"item": "PATH-CANARY", "query": "QUERY-CANARY"})
    assert "BODY-CANARY" in response.json()["result"]["content"][0]["text"]
    dependency = logging.getLogger("fastapi_mcp.server")
    dependency.setLevel(logging.DEBUG)
    dependency.debug("PATH-CANARY")
    dependency.error("BODY-CANARY", extra={"arbitrary": "EXTRA-CANARY"}, exc_info=ValueError("EXCEPTION-CANARY"))
    store, captured = logging_sinks
    output = captured.getvalue()
    assert "CANARY" not in output
    assert "CANARY" not in repr(store.indexed)
    assert "mcp.inner_http_failure" in output
    assert "Dependency diagnostic" in output
    assert not [e for e in store.indexed if e.logger.startswith("fastapi_mcp")]


def test_actual_mcp_body_grant_forgery_is_removed_without_losing_business_fields():
    from fastapi import Body

    _configure()

    @asynccontextmanager
    async def lifespan(_app):
        async with inner:
            yield

    app = FastAPI(lifespan=lifespan)

    @app.post("/body", operation_id="read_body")
    async def body(payload: dict = Body(...), user=Depends(get_current_user_without_gcu)):
        return {"payload": payload, "subject": user.uid}

    inner, _ = _mount(app)
    with TestClient(app) as client:
        response = _call(client, "read_body", {**dict.fromkeys(_GRANT, "FORGED"), "business": {"person": "nested-kept"}})
    result = response.json()["result"]
    assert result["isError"] is False
    assert json.loads(result["content"][0]["text"]) == {"payload": {"business": {"person": "nested-kept"}}, "subject": _GRANT["person"]}


@pytest.mark.asyncio
async def test_authority_wrapper_preserves_unrelated_exceptions_and_cancellation(monkeypatch):
    from fastapi_mcp import FastApiMCP

    app = FastAPI()
    async with delegated_mcp_http_client(app) as client:
        mount = DelegatedFastApiMCP(app, http_client=client)
        for error in (RuntimeError("unrelated"), asyncio.CancelledError()):

            async def fail(*_args, **_kwargs):
                raise error

            monkeypatch.setattr(FastApiMCP, "_execute_api_tool", fail)
            with pytest.raises(type(error)) as caught:
                await mount._execute_api_tool(client, "unknown", {}, {})
            assert caught.value is error
