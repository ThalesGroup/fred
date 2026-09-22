# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Pod-lifetime HTTP client used for control-plane runtime cleanup calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from control_plane_backend.app import context as context_module
from control_plane_backend.app.context import ApplicationContext
from control_plane_backend.config.loader import load_configuration


@pytest.mark.asyncio
async def test_runtime_http_client_is_reused_and_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime calls reuse one client, which application shutdown closes."""

    class _Client:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    created: list[_Client] = []

    def _client_factory(**kwargs: Any) -> _Client:
        client = _Client(**kwargs)
        created.append(client)
        return client

    config_path = Path(__file__).parents[1] / "config" / "configuration_test.yaml"
    monkeypatch.setenv("CONFIG_FILE", str(config_path))
    monkeypatch.setattr(context_module.httpx, "AsyncClient", _client_factory)
    context = ApplicationContext(load_configuration())

    first = context.get_runtime_http_client()
    second = context.get_runtime_http_client()

    assert first is second
    assert created == [first]
    assert first.timeout == 15.0

    await context.shutdown()

    assert first.closed is True
