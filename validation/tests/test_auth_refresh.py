# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied.

"""The campaign must not retain the first bearer while waiting for ingestion."""

from pathlib import Path

import httpx
import pytest


@pytest.fixture
def auth_harness(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    harness = request.config.pluginmanager.get_plugin(
        str(Path(__file__).resolve().parents[1] / "conftest.py")
    )
    assert harness is not None
    monkeypatch.setattr(harness, "_LOGIN_MANAGERS", {})
    monkeypatch.setattr(harness, "_LOGIN_DIRECTORIES", [])
    monkeypatch.setattr(harness, "REALM_URL", "http://keycloak:8080/realms/app")
    yield harness
    harness.pytest_sessionfinish()


def test_login_and_refresh_keep_realm_authority_and_cleanup(
    auth_harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from urllib.parse import parse_qs

    seen = []
    clients = []
    real_client = httpx.Client

    def respond(req: httpx.Request) -> httpx.Response:
        seen.append(
            (req.headers["host"], parse_qs(req.content.decode())["grant_type"][0])
        )
        return httpx.Response(
            200,
            json={
                "access_token": "fixture-token",
                "refresh_token": "fixture-refresh",
                "expires_in": 0 if len(seen) == 1 else 3600,
            },
        )

    def client(**kwargs):
        result = real_client(transport=httpx.MockTransport(respond), **kwargs)
        clients.append(result)
        return result

    monkeypatch.setattr(httpx, "Client", client)
    assert auth_harness.login("alice") == "fixture-token"
    assert auth_harness.login("alice") == "fixture-token"
    assert seen == [("keycloak:8080", "password"), ("keycloak:8080", "refresh_token")]
    directories = [Path(d.name) for d in auth_harness._LOGIN_DIRECTORIES]
    auth_harness.pytest_sessionfinish()
    assert clients[0].is_closed
    assert all(not p.exists() for p in directories)


@pytest.mark.parametrize(
    "error,hint",
    [
        ("unauthorized_client", "Enable Direct access grants"),
        ("invalid_grant", "demo credentials"),
        ("unknown", "Check demo provisioning"),
    ],
)
def test_login_failure_is_actionable_without_echoing_secrets(
    auth_harness, monkeypatch: pytest.MonkeyPatch, error: str, hint: str
) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                400,
                json={
                    "error": error,
                    "error_description": "sensitive-response-fixture",
                },
            )
        )
    )
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client)
    with pytest.raises(pytest.fail.Exception) as caught:
        auth_harness.login("alice")
    assert hint in str(caught.value)
    assert "sensitive-response-fixture" not in str(caught.value)
    assert client.is_closed
    assert not auth_harness._LOGIN_MANAGERS


def test_clients_resolve_a_fresh_token_for_each_request(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = request.config.pluginmanager.get_plugin(
        str(Path(__file__).resolve().parents[1] / "conftest.py")
    )
    assert harness is not None
    tokens = iter(["before", "after"])
    monkeypatch.setattr(harness, "login", lambda username: next(tokens))
    headers = []

    def handler(req: httpx.Request) -> httpx.Response:
        headers.append(req.headers["Authorization"])
        return httpx.Response(200)

    with httpx.Client(
        auth=harness.UserSessionAuth("fixture"), transport=httpx.MockTransport(handler)
    ) as client:
        client.get("https://fixture.invalid/first")
        client.get("https://fixture.invalid/second")
    assert headers == ["Bearer before", "Bearer after"]
