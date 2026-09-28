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


"""
Fire-and-forget tasks that cannot vanish mid-flight.

The event loop only keeps weak references to tasks: an unreferenced
`asyncio.create_task(...)` may be garbage-collected before it finishes
(Python docs, asyncio.create_task). `spawn` holds each task until it is done.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

_RUNNING: set[asyncio.Task[Any]] = set()


def spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    task = asyncio.get_running_loop().create_task(coro)
    _RUNNING.add(task)
    task.add_done_callback(_RUNNING.discard)
    return task
