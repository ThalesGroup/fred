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


@pytest.fixture(autouse=True)
def _reset_delegation() -> Iterator[None]:
    with preserved_delegation():
        initialize_delegation(DelegationConfig())
        yield


def test_access_log_removes_delegation_query_parameters(caplog) -> None:
    initialize_delegation(DelegationConfig(accept_delegated_calls=True))
    app = FastAPI()
    app.add_middleware(RequestResponseLogger)

    @app.get("/probe")
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    caplog.set_level(logging.DEBUG, logger="http")
    with TestClient(app) as client:
        response = client.get(
            "/probe",
            params={
                "person": "person-canary",
                "run": "run-canary",
                "agent": "agent-canary",
                "ordinary": "visible",
            },
        )

    assert response.status_code == 200
    payload = " ".join(record.getMessage() for record in caplog.records if record.name == "http")
    assert "event=delegated_request outcome=started method=GET" in payload
    assert "event=delegated_request outcome=completed method=GET status=200" in payload
    assert "person=" not in payload
    assert "run=" not in payload
    assert "agent=" not in payload
    assert "canary" not in payload
    assert "127.0.0.1" not in payload


def test_access_log_flag_off_preserves_ordinary_request_details(caplog) -> None:
    app = FastAPI()
    app.add_middleware(RequestResponseLogger)

    @app.get("/probe")
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    caplog.set_level(logging.DEBUG, logger="http")
    with TestClient(app) as client:
        response = client.get("/probe", params={"person": "synthetic-person", "ordinary": "visible"})

    assert response.status_code == 200
    request_log = next(record.getMessage() for record in caplog.records if ">>>" in record.getMessage())
    assert "person=" not in request_log
    assert "ordinary=visible" in request_log


def test_delegation_confines_body_grant_before_request_logging(caplog) -> None:
    initialize_delegation(DelegationConfig(accept_delegated_calls=True))
    app = FastAPI()
    app.add_middleware(RequestResponseLogger)

    @app.post("/probe/path-canary")
    async def probe(payload: dict[str, str] = Body()) -> dict[str, bool]:
        assert payload["person"] == "person-canary"
        return {"ok": True}

    caplog.set_level(logging.DEBUG, logger="http")
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
    payload = " ".join(record.getMessage() for record in caplog.records if record.name == "http")
    assert "event=delegated_request outcome=started method=POST" in payload
    assert "event=delegated_request outcome=completed method=POST status=200" in payload
    for canary in (
        "path-canary",
        "query-canary",
        "person-canary",
        "run-canary",
        "agent-canary",
        "body-canary",
        "claim-canary",
        "testclient",
    ):
        assert canary not in payload


def test_delegation_confines_malformed_request_logging(caplog) -> None:
    initialize_delegation(DelegationConfig(accept_delegated_calls=True))
    app = FastAPI()
    app.add_middleware(RequestResponseLogger)

    @app.post("/malformed-path-canary")
    async def probe(payload: dict[str, str] = Body()) -> dict[str, str]:
        return payload

    caplog.set_level(logging.DEBUG, logger="http")
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
    payload = " ".join(record.getMessage() for record in caplog.records if record.name == "http")
    assert "event=delegated_request outcome=completed method=POST status=422" in payload
    assert "canary" not in payload


def test_delegation_confines_failure_detail_logging(caplog) -> None:
    initialize_delegation(DelegationConfig(accept_delegated_calls=True))
    app = FastAPI()
    app.add_middleware(RequestResponseLogger)

    @app.get("/failure-path-canary")
    async def probe() -> None:
        raise RuntimeError("upstream-detail-canary")

    caplog.set_level(logging.DEBUG, logger="http")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/failure-path-canary",
            headers={"Authorization": "Bearer failure-claim-canary"},
        )

    assert response.status_code == 500
    payload = " ".join(record.getMessage() for record in caplog.records if record.name == "http")
    assert "event=delegated_request outcome=failed method=GET" in payload
    assert "canary" not in payload


def test_delegation_confines_redirect_location_logging(caplog) -> None:
    initialize_delegation(DelegationConfig(accept_delegated_calls=True))
    app = FastAPI()
    app.add_middleware(RequestResponseLogger)

    @app.get("/redirect-path-canary")
    async def probe() -> RedirectResponse:
        return RedirectResponse("https://redirect.invalid/location-canary")

    caplog.set_level(logging.DEBUG, logger="http")
    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/redirect-path-canary")

    assert response.status_code == 307
    payload = " ".join(record.getMessage() for record in caplog.records if record.name == "http")
    assert "event=delegated_request outcome=completed method=GET status=307" in payload
    assert "canary" not in payload
