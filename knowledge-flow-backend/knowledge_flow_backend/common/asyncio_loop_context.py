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
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_CURRENT_ASYNCIO_LOOP: ContextVar[asyncio.AbstractEventLoop | None] = ContextVar(
    "knowledge_flow_asyncio_loop",
    default=None,
)


def get_current_asyncio_loop() -> asyncio.AbstractEventLoop | None:
    return _CURRENT_ASYNCIO_LOOP.get()


@contextmanager
def asyncio_loop_scope(loop: asyncio.AbstractEventLoop | None) -> Iterator[asyncio.AbstractEventLoop | None]:
    token = _CURRENT_ASYNCIO_LOOP.set(loop)
    try:
        yield loop
    finally:
        _CURRENT_ASYNCIO_LOOP.reset(token)
