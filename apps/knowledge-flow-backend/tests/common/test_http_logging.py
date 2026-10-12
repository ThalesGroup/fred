import logging

import pytest
from fastapi import Body, FastAPI
from fastapi.testclient import TestClient
from fred_core.security.delegation import DelegationConfig, initialize_delegation, preserved_delegation
from starlette.responses import RedirectResponse

from knowledge_flow_backend.common.http_logging import RequestResponseLogger


@pytest.mark.parametrize("delegation", [DelegationConfig(), DelegationConfig(accept_delegated_calls=True), DelegationConfig(act_for_people=True)])
def test_request_completion_keeps_only_safe_metadata(caplog: pytest.LogCaptureFixture, delegation: DelegationConfig) -> None:
    app = FastAPI()
    app.add_middleware(RequestResponseLogger)

    @app.post("/probe/{item}")
    async def probe(item: str, payload: dict[str, str] = Body()) -> RedirectResponse:
        return RedirectResponse("https://redirect.invalid/location-canary")

    with preserved_delegation():
        initialize_delegation(delegation)
        caplog.set_level(logging.INFO, logger="http")
        with TestClient(app, follow_redirects=False) as client:
            response = client.post(
                "/probe/path-canary?ordinary=query-canary&person=person-canary", json={"content": "body-canary"}, headers={"Authorization": "Bearer claim-canary", "X-Request-ID": "spoof"}
            )
    assert response.status_code == 307
    assert response.headers["X-Request-ID"] != "spoof"
    records = [record for record in caplog.records if record.name == "http"]
    assert len(records) == 1
    record = records[0]
    assert record.route == "/probe/{item}"
    assert record.http_status == 307
    assert record.duration_ms >= 0
    assert "canary" not in repr(record.__dict__)
