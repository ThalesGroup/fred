import logging
from collections.abc import Iterator

import pytest
from fastapi import Body, FastAPI
from fastapi.testclient import TestClient
from fred_core.security.delegation import (
    DelegationConfig,
    initialize_delegation,
    preserved_delegation,
)
from starlette.responses import RedirectResponse

from knowledge_flow_backend.common.http_logging import RequestResponseLogger

# The test client logs its own outgoing URL; that is not a server-side record.
_CLIENT_LOGGERS = ("httpx", "httpcore")


@pytest.fixture(autouse=True)
def _reset_delegation() -> Iterator[None]:
    with preserved_delegation():
        initialize_delegation(DelegationConfig())
        yield


@pytest.fixture(
    params=[
        pytest.param(DelegationConfig(accept_delegated_calls=True), id="accept-delegated-calls"),
        pytest.param(DelegationConfig(act_for_people=True), id="act-for-people"),
    ]
)
def delegation_on(request: pytest.FixtureRequest) -> None:
    initialize_delegation(request.param)


def _logged_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestResponseLogger)
    return app


def _middleware_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "http"]


def _server_side_log(caplog: pytest.LogCaptureFixture) -> str:
    formatter = logging.Formatter()
    return "\n".join(formatter.format(record) for record in caplog.records if not record.name.startswith(_CLIENT_LOGGERS))


@pytest.mark.usefixtures("delegation_on")
def test_delegation_writes_no_middleware_line_for_query_grant_and_path_parameter(caplog) -> None:
    app = _logged_app()

    @app.get("/probe/{item}")
    async def probe(item: str) -> dict[str, bool]:
        return {"ok": True}

    caplog.set_level(logging.DEBUG)
    with TestClient(app) as client:
        response = client.get(
            "/probe/path-canary",
            params={
                "person": "person-canary",
                "run": "run-canary",
                "agent": "agent-canary",
                "ordinary": "query-canary",
            },
            headers={"Authorization": "Bearer claim-canary"},
        )

    assert response.status_code == 200
    assert _middleware_records(caplog) == []
    assert "canary" not in _server_side_log(caplog)


@pytest.mark.usefixtures("delegation_on")
def test_delegation_writes_no_middleware_line_for_json_body_grant(caplog) -> None:
    app = _logged_app()

    @app.post("/probe/{item}")
    async def probe(item: str, payload: dict[str, str] = Body()) -> dict[str, bool]:
        assert payload["person"] == "person-canary"
        return {"ok": True}

    caplog.set_level(logging.DEBUG)
    with TestClient(app) as client:
        response = client.post(
            "/probe/path-canary?ordinary=query-canary",
            json={
                "person": "person-canary",
                "run": "run-canary",
                "agent": "agent-canary",
                "content": "body-canary",
            },
            headers={"Authorization": "Bearer claim-canary"},
        )

    assert response.status_code == 200
    assert _middleware_records(caplog) == []
    assert "canary" not in _server_side_log(caplog)


@pytest.mark.usefixtures("delegation_on")
def test_delegation_writes_no_middleware_line_for_malformed_request(caplog) -> None:
    app = _logged_app()

    @app.post("/malformed-path-canary")
    async def probe(payload: dict[str, str] = Body()) -> dict[str, str]:
        return payload

    caplog.set_level(logging.DEBUG)
    with TestClient(app) as client:
        response = client.post(
            "/malformed-path-canary",
            content="malformed-body-canary",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer malformed-claim-canary",
            },
        )

    assert response.status_code == 422
    assert _middleware_records(caplog) == []
    assert "canary" not in _server_side_log(caplog)


@pytest.mark.usefixtures("delegation_on")
def test_delegation_writes_no_middleware_line_for_failure(caplog) -> None:
    app = _logged_app()

    @app.get("/failure-path-canary")
    async def probe() -> None:
        raise RuntimeError("upstream-detail-canary")

    caplog.set_level(logging.DEBUG)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/failure-path-canary",
            headers={"Authorization": "Bearer failure-claim-canary"},
        )

    assert response.status_code == 500
    assert _middleware_records(caplog) == []
    assert "canary" not in _server_side_log(caplog)


@pytest.mark.usefixtures("delegation_on")
def test_delegation_writes_no_middleware_line_for_redirect(caplog) -> None:
    app = _logged_app()

    @app.get("/redirect-path-canary")
    async def probe() -> RedirectResponse:
        return RedirectResponse("https://redirect.invalid/location-canary")

    caplog.set_level(logging.DEBUG)
    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/redirect-path-canary")

    assert response.status_code == 307
    assert _middleware_records(caplog) == []
    assert "canary" not in _server_side_log(caplog)


def test_without_delegation_request_diagnostics_remain(caplog) -> None:
    app = _logged_app()

    @app.get("/probe")
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    caplog.set_level(logging.DEBUG, logger="http")
    with TestClient(app) as client:
        response = client.get("/probe", params={"person": "synthetic-person", "ordinary": "visible"})

    assert response.status_code == 200
    request_line, response_line = _middleware_records(caplog)
    assert request_line.levelno == logging.DEBUG
    assert request_line.getMessage().startswith(">>> GET /probe ")
    assert "ordinary=visible" in request_line.getMessage()
    assert "person=" not in request_line.getMessage()
    assert response_line.levelno == logging.INFO
    assert response_line.getMessage().startswith("<<< GET /probe status=200 ")
