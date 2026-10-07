# fred_core/model/factory.py
#
# Copyright Thales 2025
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

"""Test hygiene shared by every fred-core test."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

_DISPOSE_FIXTURE = "_dispose_async_engines"


@pytest_asyncio.fixture
async def _dispose_async_engines(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[None]:
    """
    Dispose every AsyncEngine an async test creates, on the test's own loop.

    An engine left open keeps its aiosqlite connections; the garbage collector
    later closes them from their worker threads onto an already-closed loop
    ("Event loop is closed"), a warning pinned on whichever test runs then.
    """
    created: list[AsyncEngine] = []
    original_init = AsyncEngine.__init__

    def tracking_init(self: AsyncEngine, *args: object, **kwargs: object) -> None:
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]
        created.append(self)

    monkeypatch.setattr(AsyncEngine, "__init__", tracking_init)
    yield
    for engine in created:
        await engine.dispose()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        fixturenames = getattr(item, "fixturenames", None)
        if (
            item.get_closest_marker("asyncio") is not None
            and fixturenames is not None
            and _DISPOSE_FIXTURE not in fixturenames
        ):
            fixturenames.append(_DISPOSE_FIXTURE)


@pytest.fixture(autouse=True)
def _restore_platform_access_globals(monkeypatch):
    from fred_core.security.platform_access import access_control

    monkeypatch.setattr(access_control, "_available", access_control._available)
    monkeypatch.setattr(access_control, "_installed", access_control._installed)
