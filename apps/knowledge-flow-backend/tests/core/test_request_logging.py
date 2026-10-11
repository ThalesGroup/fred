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

import asyncio
import base64
import json
import logging
import os
import socket
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
import uvicorn
from fastapi import APIRouter
from fred_core.logs.log_setup import AUDIT_LOGGER_NAME
from fred_core.security.delegation import DelegationConfig, preserved_delegation

from knowledge_flow_backend import main as main_module
from knowledge_flow_backend.application_context import ApplicationContext

_PATH_CANARY = "SYNTHETIC-PATH-CANARY"
_QUERY_CANARY = "SYNTHETIC-QUERY-CANARY"
_CLAIM_CANARY = "SYNTHETIC-CLAIM-CANARY"
_CLIENT_CANARY = "198.51.100.23"
_GRANT_CANARIES = ("SYNTHETIC-PERSON-CANARY", "SYNTHETIC-RUN-CANARY", "SYNTHETIC-AGENT-CANARY")
_CANARIES = (_PATH_CANARY, _QUERY_CANARY, _CLAIM_CANARY, _CLIENT_CANARY, *_GRANT_CANARIES)


class _Sink(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextmanager
def _restored_logging() -> Iterator[None]:
    """Let `create_app` wire logging as in a fresh process, then put every touched logger back."""
    root = logging.getLogger()
    uvicorn_loggers = [logging.getLogger(name) for name in ("uvicorn", "uvicorn.error", "uvicorn.access")]
    loggers = [root, *uvicorn_loggers, logging.getLogger(AUDIT_LOGGER_NAME)]
    saved = [(lg, list(lg.filters), list(lg.handlers), lg.level, lg.propagate, lg.disabled) for lg in loggers]
    # Filters left by an earlier `create_app` in this process would apply twice.
    for lg in uvicorn_loggers:
        lg.filters.clear()
    try:
        yield
    finally:
        for lg, filters, handlers, level, propagate, disabled in saved:
            lg.filters[:] = filters
            lg.handlers[:] = handlers
            lg.setLevel(level)
            lg.propagate = propagate
            lg.disabled = disabled


def _register_probe(router: APIRouter) -> None:
    async def probe(name: str) -> dict[str, bool]:
        return {"ok": True}

    router.add_api_route("/probe/{name}", probe)


def _request() -> bytes:
    claims = base64.urlsafe_b64encode(json.dumps({"sub": _CLAIM_CANARY, "azp": _CLAIM_CANARY}).encode()).decode().rstrip("=")
    person, run, agent = _GRANT_CANARIES
    target = f"/knowledge-flow/v1/probe/{_PATH_CANARY}?ordinary={_QUERY_CANARY}&person={person}&run={run}&agent={agent}"
    lines = [
        f"GET {target} HTTP/1.1",
        "Host: knowledge-flow.invalid",
        f"Authorization: Bearer e30.{claims}.c2ln",
        f"X-Forwarded-For: {_CLIENT_CANARY}",
        "Connection: close",
    ]
    return ("\r\n".join(lines) + "\r\n\r\n").encode()


async def _serve_one_request(server: uvicorn.Server, sink: _Sink) -> bytes:
    # A Unix socket keeps the offline suite's network block in force.
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "kf.sock")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(path)
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        while not server.started:
            assert not serving.done(), serving.result()
            await asyncio.sleep(0.01)
        sink.records.clear()
        reader, writer = await asyncio.open_unix_connection(path)
        writer.write(_request())
        await writer.drain()
        response = await reader.read()
        writer.close()
        await writer.wait_closed()
        # Graceful shutdown waits for the request task, so every line it logs is captured.
        server.should_exit = True
        await serving
    return response


async def _served_records(app_context: ApplicationContext, monkeypatch: pytest.MonkeyPatch, delegation: DelegationConfig) -> tuple[bytes, list[logging.LogRecord]]:
    """Serve one request through the application `create_app` builds; return the response and every record."""
    config = app_context.configuration.model_copy(deep=True)
    config.security.delegation = delegation
    monkeypatch.setattr(main_module, "load_configuration", lambda: config)
    monkeypatch.setattr(main_module, "start_http_server", lambda *args, **kwargs: None)
    monkeypatch.setattr(ApplicationContext, "_instance", None)
    # Controllers need live stores; one probe route on the application router stands in for them.
    for name in [name for name in vars(main_module) if name.endswith("Controller")]:
        monkeypatch.setattr(main_module, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "TasksController", _register_probe)
    sink = _Sink()
    with preserved_delegation(), _restored_logging():
        # Production order: uvicorn configures its loggers, then the factory runs log_setup.
        # Trusting the forwarded header gives the whole application a client address to leak.
        uvicorn_config = uvicorn.Config("knowledge_flow_backend.main:create_app", factory=True, lifespan="off", forwarded_allow_ips="*")
        uvicorn_config.load()
        logging.getLogger().addHandler(sink)
        response = await _serve_one_request(uvicorn.Server(uvicorn_config), sink)
    return response, sink.records


@pytest.mark.parametrize(
    "delegation",
    [
        pytest.param(DelegationConfig(accept_delegated_calls=True), id="accept-delegated-calls"),
        pytest.param(DelegationConfig(act_for_people=True), id="act-for-people"),
    ],
)
@pytest.mark.asyncio
async def test_under_delegation_a_request_has_one_safe_completion(app_context: ApplicationContext, monkeypatch, delegation: DelegationConfig) -> None:
    response, records = await _served_records(app_context, monkeypatch, delegation)

    assert response.startswith(b"HTTP/1.1 200 ")
    assert [record for record in records if record.name == "uvicorn.access"] == []
    access = [record for record in records if record.name == "http"]
    assert len(access) == 1
    assert access[0].http_status == 200
    assert access[0].route == "/knowledge-flow/v1/probe/{name}"
    for record in records:
        leaked = [canary for canary in _CANARIES if canary in repr(record.__dict__)]
        assert leaked == [], f"{record.name}: {leaked}"


@pytest.mark.asyncio
async def test_without_delegation_the_request_logger_writes_its_response_line(app_context: ApplicationContext, monkeypatch) -> None:
    response, records = await _served_records(app_context, monkeypatch, DelegationConfig())

    assert response.startswith(b"HTTP/1.1 200 ")
    completion = [record for record in records if record.name == "http"]
    assert len(completion) == 1
    assert completion[0].http_status == 200
    assert completion[0].route == "/knowledge-flow/v1/probe/{name}"
    assert all(canary not in repr(record.__dict__) for record in records for canary in _CANARIES)
