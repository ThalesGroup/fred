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
